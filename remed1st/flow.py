"""Button-triggered DFU guidance and limera1n pwnDFU, with target checks."""
from pathlib import Path
import platform
import math
import plistlib
import re
import subprocess
import threading
import time
from .device import PROJECT, find_tool, parse_recovery, probe, run_tool

PRODUCTS = {'iPhone2,1': 0x8920, 'iPod3,1': 0x8922, 'iPhone3,1': 0x8930,
            'iPhone3,2': 0x8930, 'iPhone3,3': 0x8930, 'iPod4,1': 0x8930, 'iPad1,1': 0x8930}


def compatible(state):
    if not state.connected or state.product not in PRODUCTS:
        return False
    return state.chip_id is None or state.chip_id == PRODUCTS[state.product]


def ecid_number(value):
    value = str(value).strip()
    return int(value, 16 if value.lower().startswith('0x') or re.search('[a-fA-F]', value) else 10)


def same_target(expected, actual):
    try:
        return ecid_number(expected.ecid) == ecid_number(actual.ecid)
    except ValueError:
        return False


def dfu_count():
    """ipwnder has no ECID selector: require exactly one physical DFU target."""
    if platform.system() == 'Darwin':
        response = subprocess.run(['/usr/sbin/ioreg', '-a', '-l', '-p', 'IOUSB'], capture_output=True, timeout=5, check=True)
        tree = plistlib.loads(response.stdout)
        def count(value):
            if isinstance(value, list):
                return sum(count(x) for x in value)
            if isinstance(value, dict):
                return int(value.get('idVendor') == 0x5ac and value.get('idProduct') == 0x1227) + sum(
                    count(v) for v in value.values() if isinstance(v, (list, dict)))
            return 0
        return count(tree)
    if platform.system() == 'Linux':
        count = 0
        for entry in Path('/sys/bus/usb/devices').iterdir():
            try:
                count += int((entry/'idVendor').read_text().strip() == '05ac' and
                             (entry/'idProduct').read_text().strip() == '1227')
            except OSError:
                pass
        return count
    raise RuntimeError('DFU device counting is unavailable on this platform.')


class Cancelled(Exception):
    pass


class Limera1nFlow:
    def __init__(self, notify, runner=run_tool, resolver=find_tool, counter=dfu_count,
                 preflight=None, after_pwn=None):
        self.notify, self.runner, self.resolver, self.counter = notify, runner, resolver, counter
        self.stop = threading.Event()
        self.process = None
        self.log_path = None
        self.preflight, self.after_pwn = preflight, after_pwn

    def cancel(self):
        self.stop.set()
        process = self.process
        if process and process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass

    def check_cancel(self):
        if self.stop.is_set():
            raise Cancelled()

    def wait(self, seconds):
        if self.stop.wait(seconds):
            raise Cancelled()

    def query(self, expected, timeout=3):
        tool = self.resolver('irecovery')
        try:
            response = self.runner(tool, '-q', timeout=timeout)
        except subprocess.TimeoutExpired:
            return None
        if response.returncode:
            return None
        state = parse_recovery(response.stdout)
        if not same_target(expected, state):
            raise RuntimeError('The connected device has a different ECID. The operation was stopped.')
        if not compatible(state) or state.chip_id != PRODUCTS[expected.product]:
            raise RuntimeError('The DFU device model or chip does not match the limera1n target.')
        return state

    def validate_dfu(self, expected):
        self.check_cancel()
        if self.counter() != 1:
            raise RuntimeError('Connect only the target iPhone in DFU mode.')
        state = self.query(expected)
        if not state or state.mode.upper() != 'DFU':
            raise RuntimeError('DFU mode could not be verified. limera1n was not started.')
        return state

    def run(self, expected):
        try:
            if not compatible(expected):
                raise RuntimeError('This device does not support limera1n.')
            for name in ('irecovery', 'ipwnder'):
                if not self.resolver(name):
                    raise RuntimeError(name + ' tool was not found.')
            ecid_number(expected.ecid)  # Unknown identity must never start a flow.
            self.check_cancel()
            if self.preflight:
                self.preflight(expected, self)
            self.check_cancel()
            if expected.mode == 'Normal':
                current = probe(self.runner, self.resolver)
                if not same_target(expected, current) or not compatible(current):
                    raise RuntimeError('The original device was disconnected or replaced.')
                tool = self.resolver('ideviceenterrecovery')
                if not tool:
                    raise RuntimeError('ideviceenterrecovery was not found.')
                self.notify('Preparing recovery mode…', 0.05)
                response = self.runner(tool, expected.udid, timeout=15)
                if response.returncode:
                    raise RuntimeError('Could not enter recovery mode. Check the USB connection.')
                found = None
                for _ in range(20):
                    self.check_cancel()
                    found = self.query(expected)
                    if found:
                        break
                    self.wait(0.5)
                if not found:
                    raise RuntimeError('Recovery device not found. Check the cable and try again.')
            else:
                found = self.query(expected)
            if not found or found.mode.upper() != 'DFU':
                for remaining in range(3, 0, -1):
                    self.notify(f'Get ready for DFU: {remaining}\nLocate the Power and Home buttons.', 0.1)
                    self.wait(1)
                # Hardware button guidance; Recovery is never treated as DFU.
                hold_seconds = 8 if found and found.mode.upper() == 'RECOVERY' else 10
                for instruction, seconds, base in [
                    ('Hold Power and Home', hold_seconds, 0.15),
                    ('Release Power. Keep holding Home', 15, 0.35),
                ]:
                    deadline = time.monotonic() + seconds
                    while time.monotonic() < deadline:
                        self.check_cancel()
                        remaining = max(1, math.ceil(deadline-time.monotonic()))
                        self.notify(f'{instruction} — {remaining}\nThe screen must remain completely black in DFU mode.', base)
                        found = self.query(expected, timeout=0.4)
                        if found and found.mode.upper() == 'DFU':
                            break
                        self.wait(min(0.25, max(0, deadline-time.monotonic())))
                    if found and found.mode.upper() == 'DFU':
                        break
            before = self.validate_dfu(expected)
            if before.pwned:
                if self.after_pwn:
                    return self.after_pwn(expected, self)
                self.notify('Pwned DFU is already active. No additional exploit was applied.', 1.0)
                return True
            self.notify('DFU detected. Running limera1n…', None)
            exploit_log = self.execute_exploit() or ''
            # ipwnder reports success via "pwned!" in its log output.
            # After gaster reset, PWND disappears from irecovery -q, so we
            # mirror Legacy-iOS-Kit's logic: trust the tool exit if irecovery
            # at least sees the device (irec_pwned OR tool_pwned must succeed).
            tool_pwned = 'pwned!' in exploit_log
            self.wait(2)
            verified = None
            for _ in range(30):
                self.check_cancel()
                verified = self.query(expected)
                if verified and (verified.pwned or tool_pwned):
                    break
                self.wait(0.5)
            if not verified:
                raise RuntimeError('Could not verify pwned DFU. '
                    'Unplug the cable, re-enter DFU mode, and try again.')
            if not verified.pwned and not tool_pwned:
                raise RuntimeError('limera1n exploit did not succeed. '
                    'Re-enter DFU mode and try again.')
            if self.after_pwn:
                return self.after_pwn(expected, self)
            self.notify('limera1n complete. Pwned DFU verified.\nA permanent jailbreak or Cydia was not installed.', 1.0)
            return True
        except Cancelled:
            self.notify('Operation cancelled. The device remains in its current mode.', 0.0)
        except Exception as error:
            self.notify(str(error), 0.0)
        return False

    def execute_exploit(self):
        self.check_cancel()
        logs = PROJECT/'logs'; logs.mkdir(exist_ok=True)
        self.log_path = logs/time.strftime('limera1n-%Y%m%d-%H%M%S.log')
        work = PROJECT/'runtime'; work.mkdir(exist_ok=True)
        with self.log_path.open('w') as stream:
            self.process = subprocess.Popen([self.resolver('ipwnder'), '-pv'], cwd=work,
                                            stdout=stream, stderr=subprocess.STDOUT)
            deadline = time.monotonic()+75
            try:
                while self.process.poll() is None:
                    self.check_cancel()
                    if time.monotonic() > deadline:
                        raise RuntimeError('limera1n timed out. Enter DFU mode and try again.')
                    self.wait(0.15)
            finally:
                if self.process.poll() is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.process.kill(); self.process.wait()
        # ipwnder leaves the device in "pwned iBSS" state (STRG: [none]).
        # Legacy-iOS-Kit calls `gaster reset` after ipwnder to bring the
        # device back to a clean pwned DFU state so that load_bootloaders
        # can send iBSS/iBEC from scratch without hitting a wrong USB state.
        gaster = self.resolver('gaster')
        if gaster:
            self.run_gaster_reset(gaster)
        return self.log_path.read_text(errors='replace')

    def run_gaster_reset(self, gaster):
        """Reset DFU state after ipwnder so load_bootloaders starts clean."""
        self.check_cancel()
        work = PROJECT/'runtime'; work.mkdir(exist_ok=True)
        try:
            proc = subprocess.run([gaster, 'reset'], cwd=work,
                                  capture_output=True, timeout=15)
        except subprocess.TimeoutExpired:
            pass  # gaster reset timed out — continue anyway
