"""UI-driven, build-specific hacktivation and temporary custom-logo boot.

No restore, NOR or baseband flashing. Hardware transitions are verified rather
than inferred from a command's exit status. Only the known lockdownd is replaced.
"""
import hashlib
import plistlib
import socket
import subprocess
import time
import shutil

from .boot_assets import BootAssets, BUILD, KIT, PRODUCT, VERSION, sha
from .device import PROJECT, parse_normal
from .flow import Limera1nFlow, same_target
from .jailbreak import ensure_cydia, cydia_info, JAILBREAK
from .untether_package import prepare_package, PACKAGE, VERSION as PACKAGE_VERSION
from .boot_display import STAGES

RAM_WORK = '/remed1st-work'
RAM_KLOADER = RAM_WORK + '/kloader'
RAM_IBSS = RAM_WORK + '/iBSS'


def firmware_supported(state):
    return state.product == PRODUCT and (state.mode != 'Normal' or
        (state.version, state.build) == (VERSION, BUILD))


def validate_system(data):
    info = plistlib.loads(data)
    if (info.get('ProductVersion'), info.get('ProductBuildVersion')) != (VERSION, BUILD):
        raise RuntimeError('The installed system is not iOS 5.1.1 / 9B208. The activation file was not changed.')


def patch_required(current, original, patched):
    if current == patched:
        return False
    if current != original:
        raise RuntimeError('Unrecognized lockdownd. The existing file was not changed.')
    return True


class IOS511Pipeline:
    def __init__(self):
        self.assets = None
        self.proxy = None
        self.port = None
        self.untether_deb = None

    def preflight(self, expected, flow):
        if not firmware_supported(expected):
            raise RuntimeError('Activation and custom boot require iPhone3,1 / iOS 5.1.1 (9B208).')
        for name in ('iproxy', 'sshpass', 'idevice_id', 'ideviceinfo', 'usb-reconnect'):
            if not flow.resolver(name):
                raise RuntimeError(name + ' was not found. Preparation could not finish.')
        if not (KIT/'resources/ssh_config').is_file():
            raise RuntimeError('SSH configuration was not found.')
        devices = self.usb_devices(flow)
        if devices and devices != [expected.udid]:
            raise RuntimeError('Disconnect other Apple USB devices and try again.')
        self.assets = BootAssets(flow.notify, flow.check_cancel).prepare()
        self.untether_deb = prepare_package()
        for name in (f'g1lbertJB/{PRODUCT}_{BUILD}.tar', 'freeze.tar.gz', 'cydiasubstrate.tar',
                     'nopatcyh.tar', 'sshdeb.tar', 'openssl.tar.gz', 'openssh.tar.gz'):
            if not (JAILBREAK/name).is_file():
                raise RuntimeError('Missing Cydia installation asset: ' + name)
        flow.check_cancel()

    def command(self, flow, argv, timeout=25, required=True, stdin=None, stdout_file=None):
        flow.check_cancel()
        flow.process = subprocess.Popen(list(map(str, argv)), stdin=stdin, cwd=PROJECT,
            stdout=stdout_file if stdout_file is not None else subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + timeout
        try:
            while True:
                try:
                    out, err = flow.process.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    flow.check_cancel()
                    if stdout_file is not None and stdout_file.tell() > 1_500_000_000:
                        raise RuntimeError('System-volume backup exceeded its size limit. Repair was not started.')
                    if time.monotonic() > deadline:
                        if not required:
                            return 124, b'Command timed out.'
                        raise RuntimeError('The operation timed out. Check the USB connection.')
            code = flow.process.returncode
            out = out or b''
            if required and code:
                raise RuntimeError((out + err).decode(errors='replace')[-450:] or 'The command failed.')
            return code, out + err if code else out
        finally:
            if flow.process.poll() is None:
                flow.process.kill()
                flow.process.communicate()
            flow.process = None

    def usb_devices(self, flow):
        result = flow.runner(flow.resolver('idevice_id'), '-l', timeout=5)
        if result.returncode:
            raise RuntimeError('Could not read the USB device list.')
        return result.stdout.decode().split()

    def recovery(self, expected, flow, *args, ecid=True):
        # The ECID selector (-i) guards against a swapped device in DFU mode.
        # However, irecovery -i ECID drops the USB connection mid-transfer when
        # the device is already in Recovery mode (iBEC running), so file uploads
        # after the device leaves DFU must NOT use the ECID selector.
        from .flow import ecid_number
        if ecid:
            return self.command(flow, [flow.resolver('irecovery'), '-i',
                hex(ecid_number(expected.ecid)), *args])
        return self.command(flow, [flow.resolver('irecovery'), *args])

    def soft_reconnect(self, expected, flow):
        """Request a target-only host re-enumeration; never reset a hub."""
        from .flow import ecid_number
        tool = flow.resolver('usb-reconnect')
        if not tool:
            return False
        flow.notify('Attempting automatic USB reconnection…', None)
        code, output = self.command(flow, [tool, '--reenumerate',
            hex(ecid_number(expected.ecid))], timeout=8, required=False)
        if code:
            detail = output.decode(errors='replace').strip()
            if detail:
                flow.notify('USB reconnect: ' + detail[-250:], None)
        return code == 0

    def wait_recovery(self, expected, flow, seconds=60, required=True, mode=None):
        started = time.monotonic()
        deadline = time.monotonic() + seconds
        attempts = 0
        while time.monotonic() < deadline:
            flow.check_cancel()
            state = flow.query(expected)
            if state and (mode is None or state.mode.upper() == mode.upper()):
                return True
            # Only retry transport recovery while the target cannot be opened.
            # A visible device in a different mode must not be reset blindly.
            if not state and attempts < 2 and time.monotonic() - started >= (4, 14)[attempts]:
                self.soft_reconnect(expected, flow)
                attempts += 1
            # After 12 seconds with no device, prompt the user to replug.
            elapsed = time.monotonic() - started
            if elapsed >= 12:
                flow.notify('Unplug and replug your iPhone USB cable…', None)
            else:
                flow.notify('Waiting for the iPhone to reconnect automatically…', None)
            flow.wait(0.5)
        if required:
            raise RuntimeError('Automatic USB recovery could not reach the expected device mode. '
                'Unplug and replug the USB cable, then try again.')
        return False

    def load_bootloaders(self, expected, flow, prefix, skip_ibss=False):
        if not skip_ibss:
            # iBSS is sent while the device is in DFU mode — use ECID selector.
            self.recovery(expected, flow, '-f', self.assets/f'{prefix}-iBSS.img3')
            # After iBSS, the device stays in DFU (irecovery still reports
            # MODE: DFU on A4).  Wait briefly then send iBEC directly.
            flow.wait(2)
        # iBEC is also sent while still in DFU/pwned-iBSS — use ECID here too.
        # After upload the device re-enumerates in Recovery mode.
        self.recovery(expected, flow, '-f', self.assets/f'{prefix}-iBEC.img3')
        flow.wait(1)
        self.wait_recovery(expected, flow, mode='Recovery')

    def boot_kernel(self, expected, flow, prefix):
        # Device is in Recovery mode (iBEC running) — do NOT use ECID selector.
        self.recovery(expected, flow, '-f', self.assets/f'{prefix}-DeviceTree.img3', ecid=False)
        self.recovery(expected, flow, '-c', 'devicetree', ecid=False)
        self.recovery(expected, flow, '-f', self.assets/f'{prefix}-Kernelcache.img3', ecid=False)
        self.recovery(expected, flow, '-c', 'bootx', ecid=False)

    def start_ssh(self, expected, flow):
        # The device re-enumerates as the SSH ramdisk boots: waiting for
        # idevice_id to report a matching UDID would latch onto the stale
        # recovery-mode entry (ECID-form serial) and lock iproxy onto a
        # USB identity that disappears when the ramdisk comes up.  Instead,
        # mirror Legacy-iOS-Kit: start iproxy immediately without a UDID
        # selector so it binds to whatever single Apple device appears, and
        # poll SSH until the ramdisk responds.  ECID-guarded irecovery calls
        # throughout the boot chain already guarantee we booted the right
        # device; the multi-device check below enforces it at SSH-ready time.
        # When called post-reboot (install_untether / verify_cydia) the normal-
        # mode UDID is known and supplied to iproxy for an extra identity lock.
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        udid = expected.udid if expected.udid not in ('', '—') else None
        iproxy_argv = [flow.resolver('iproxy'), '-s', '127.0.0.1', f'{self.port}:22']
        if udid:
            iproxy_argv += ['-u', udid]
        self.proxy = subprocess.Popen(iproxy_argv,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        started = time.monotonic()
        deadline = time.monotonic() + 150
        attempts = 0
        while time.monotonic() < deadline:
            flow.check_cancel()
            if self.proxy.poll() is not None:
                raise RuntimeError('Could not start the USB SSH tunnel.')
            code, _ = self.ssh(flow, 'echo remed1st-ready', required=False)
            if not code:
                devices = self.usb_devices(flow)
                if len(devices) > 1:
                    raise RuntimeError('Connect only the target iPhone via USB for SSH.')
                return
            if attempts < 2 and time.monotonic() - started >= (20, 50)[attempts]:
                self.soft_reconnect(expected, flow)
                attempts += 1
            flow.notify('Waiting for the SSH system to connect automatically…', None)
            flow.wait(2)
        raise RuntimeError('The SSH ramdisk did not respond. '
            'The adapter or cable may require physical attention.')

    def ssh_argv(self, flow, script, user='root'):
        return [flow.resolver('sshpass'), '-p', 'alpine', '/usr/bin/ssh',
            '-F', KIT/'resources/ssh_config', '-o', 'PreferredAuthentications=password',
            '-o', 'PubkeyAuthentication=no', '-o', 'ConnectTimeout=3', '-p', str(self.port),
            user+'@127.0.0.1', 'PATH=/bin:/sbin:/usr/bin:/usr/sbin; export PATH; ' + script]

    def ssh(self, flow, script, required=True, stdin=None, timeout=15, user='root'):
        return self.command(flow, self.ssh_argv(flow, script, user),
            timeout=timeout, required=required, stdin=stdin)

    def check_ramdisk(self, flow):
        """Check every external utility used before changing the system disk."""
        paths = ('/bin/cat', '/bin/mkdir', '/bin/ln', '/bin/chmod', '/bin/chown',
                 '/bin/cp', '/bin/mv', '/bin/tar', '/sbin/mount', '/sbin/mount_hfs',
                 '/sbin/fsck_hfs', '/sbin/reboot_bak', '/usr/bin/scp')
        self.ssh(flow, 'set -e; for tool in ' + ' '.join(paths) + '; do '
            'if [ ! -x "$tool" ]; then printf "Missing ramdisk utility: %s\\n" "$tool"; '
            'exit 1; fi; done')

    def phone_status(self, flow, stage):
        if stage not in STAGES:
            raise ValueError('Unknown on-device display stage.')
        self.copy(flow,self.assets/f'screen-{stage}.rmd',
                  'root@127.0.0.1:/remed1st-screen/next.rmd')
        code,response=self.ssh(flow,'set -e; /bin/mv /remed1st-screen/next.rmd '
            '/remed1st-screen/frame.rmd; /remed1st-screen/display',required=False)
        if code or response.strip()!=b'remed1st screen updated':
            flow.notify('On-device display unavailable: '+response.decode(errors='replace')[-200:],None)
            return False
        return True

    def copy(self, flow, source, destination):
        return self.command(flow, [flow.resolver('sshpass'), '-p', 'alpine', '/usr/bin/scp',
            '-O', '-F', KIT/'resources/ssh_config', '-o', 'PreferredAuthentications=password',
            '-o', 'PubkeyAuthentication=no', '-o', 'ConnectTimeout=3', '-P', str(self.port),
            source, destination])

    def hacktivate(self, flow):
        self.mount_system(flow)
        _, system = self.ssh(flow, 'cat /mnt1/System/Library/CoreServices/SystemVersion.plist')
        validate_system(system)
        session = PROJECT/'backups'/time.strftime('%Y%m%d-%H%M%S')
        session.mkdir(parents=True, exist_ok=True)
        current = session/'lockdownd.before'
        self.copy(flow, 'root@127.0.0.1:/mnt1/usr/libexec/lockdownd', current)
        original, patched = sha(self.assets/'lockdownd.original'), sha(self.assets/'lockdownd.patched')
        if patch_required(sha(current), original, patched):
            exists, _ = self.ssh(flow, 'test -e /mnt1/usr/libexec/lockdownd.orig', required=False)
            if exists == 0:
                backup = session/'lockdownd.orig'
                self.copy(flow, 'root@127.0.0.1:/mnt1/usr/libexec/lockdownd.orig', backup)
                if sha(backup) != original:
                    raise RuntimeError('The existing lockdownd backup is unrecognized. The operation was stopped.')
            elif exists != 1:
                raise RuntimeError('Could not verify the existing backup.')
            self.copy(flow, self.assets/'lockdownd.patched', 'root@127.0.0.1:/mnt1/usr/libexec/lockdownd.remed1st')
            staged = session/'lockdownd.staged'
            self.copy(flow, 'root@127.0.0.1:/mnt1/usr/libexec/lockdownd.remed1st', staged)
            if sha(staged) != patched:
                raise RuntimeError('The uploaded patch checksum does not match. The original file was not changed.')
            self.ssh(flow, 'set -e; cd /mnt1/usr/libexec; '
                'if [ ! -e lockdownd.orig ]; then cp -p lockdownd lockdownd.orig; fi; '
                'chmod 755 lockdownd.remed1st; chown 0:0 lockdownd.remed1st; '
                'mv -f lockdownd.remed1st lockdownd')
        self.copy(flow, 'root@127.0.0.1:/mnt1/usr/libexec/lockdownd', session/'lockdownd.after')
        if sha(session/'lockdownd.after') != patched:
            raise RuntimeError('Could not verify the activation patch. A backup is available in the backups folder.')

    def mount_system(self, flow):
        _, mounted = self.ssh(flow, '/sbin/mount')
        if b' on /mnt1 ' in mounted:
            return
        code, message = self.ssh(flow, '/sbin/mount_hfs /dev/disk0s1s1 /mnt1', required=False)
        if code == 0:
            return
        flow.notify('Checking the system volume before repair…', 0.61)
        _, diagnostic = self.ssh(flow, '/sbin/fsck_hfs -fn /dev/rdisk0s1s1',
                                 required=False, timeout=180)
        if b'needs to be repaired' not in diagnostic:
            raise RuntimeError('The system volume could not be mounted: ' +
                               (message+diagnostic).decode(errors='replace')[-500:])
        backup_dir = PROJECT/'backups'
        backup_dir.mkdir(exist_ok=True)
        if shutil.disk_usage(backup_dir).free < 2_000_000_000:
            raise RuntimeError('At least 2 GB of free space is needed to back up the system volume before repair.')
        backup = backup_dir/('system-'+str(time.time_ns())+'.hfs')
        flow.notify('Backing up the system volume before HFS repair…', 0.62)
        try:
            with backup.open('xb') as stream:
                self.command(flow, self.ssh_argv(flow, '/bin/dd if=/dev/rdisk0s1s1 bs=1048576'),
                             timeout=240, stdout_file=stream)
            if backup.stat().st_size < 32_000_000:
                raise RuntimeError('The system-volume backup is incomplete. Repair was not started.')
        except Exception:
            if backup.exists():
                backup.rename(backup.with_suffix('.incomplete'))
            raise
        # Keep the complete raw snapshot, including the pending journal.
        flow.notify('Repairing the backed-up HFS system volume…', 0.63)
        code, diagnostic = self.ssh(flow, '/sbin/fsck_hfs -fy /dev/rdisk0s1s1',
                                    required=False, timeout=180)
        (backup.with_suffix('.repair.txt')).write_bytes(diagnostic)
        if code not in (0,1):
            raise RuntimeError('HFS repair did not finish successfully. The raw backup was preserved.')
        self.ssh(flow, '/sbin/mount_hfs /dev/disk0s1s1 /mnt1')

    def stop_proxy(self):
        if self.proxy and self.proxy.poll() is None:
            self.proxy.terminate()
            try:
                self.proxy.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proxy.kill()
                self.proxy.wait()
        self.proxy = None

    def verify_cydia(self, state, flow):
        import sys
        flow.notify('Checking Cydia on the Home screen…', 0.95)
        code, _ = self.command(flow, [sys.executable, '-m', 'remed1st.icons', state.udid],
                               timeout=12, required=False)
        if code == 0:
            return
        self.stop_proxy()
        self.start_ssh(state, flow)
        _, info = self.ssh(flow, 'cat /Applications/Cydia.app/Info.plist')
        self.ssh(flow, 'test -x /Applications/Cydia.app/Cydia')
        if not cydia_info(info):
            raise RuntimeError('The running system does not contain a verified Cydia installation.')
        flow.notify('Refreshing the Cydia icon on the Home screen…', 0.96)
        self.ssh(flow, '/usr/bin/uicache', timeout=60, user='mobile')
        for _ in range(10):
            flow.check_cancel()
            code, _ = self.command(flow, [sys.executable, '-m', 'remed1st.icons', state.udid],
                                   timeout=10, required=False)
            if code == 0:
                return
            flow.wait(1)
        raise RuntimeError('Cydia files are installed, but its Home screen icon could not be verified. '
                           'Unlock the iPhone and open Cydia once.')

    def install_untether_package(self, state, flow):
        flow.notify('Installing remed1st-untether5 in Cydia…', 0.93)
        self.start_ssh(state, flow)
        self.ssh(flow, 'mkdir -p /var/root/Media/remed1st')
        remote = '/var/root/Media/remed1st/' + self.untether_deb.name
        self.copy(flow, self.untether_deb, 'root@127.0.0.1:' + remote)
        _, uploaded = self.ssh(flow, 'cat ' + remote)
        if hashlib.sha256(uploaded).hexdigest() != sha(self.untether_deb):
            raise RuntimeError('The untether DEB upload did not verify. It was not installed.')
        # No force-overwrite: dpkg must report ownership or dependency conflicts.
        self.ssh(flow, '/usr/bin/dpkg --force-confold -i ' + remote, timeout=60)
        _, status = self.ssh(flow, "/usr/bin/dpkg-query -W -f='${Status}\\n${Version}\\n${Name}\\n' " + PACKAGE)
        if status.decode().splitlines() != ['install ok installed', PACKAGE_VERSION, PACKAGE]:
            raise RuntimeError('The Cydia untether package registration could not be verified.')

    def wait_normal(self, expected, flow):
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            flow.check_cancel()
            devices = self.usb_devices(flow)
            if len(devices) == 1:
                try:
                    result = flow.runner(flow.resolver('ideviceinfo'), '-u', devices[0], '--xml', timeout=5)
                except subprocess.TimeoutExpired:
                    flow.wait(1)
                    continue
                if result.returncode == 0:
                    state = parse_normal(result.stdout)
                    if not same_target(expected, state) or not firmware_supported(state):
                        raise RuntimeError('The device that booted does not match the target.')
                    if state.activation not in ('Activated', 'FactoryActivated', 'WildcardActivated'):
                        # lockdownd takes a few seconds after first USB pairing to
                        # report a valid activation state; keep polling rather than
                        # aborting the pipeline on the first unverified response.
                        flow.wait(2)
                        continue
                    return state
            flow.wait(1)
        raise RuntimeError('The iPhone did not return to normal mode. Startup was not confirmed.')

    def notify_completion(self, flow):
        flow.notify('Sending the completion notification to your iPhone…', 0.99)
        code, response = self.ssh(flow, '/usr/libexec/remed1st-notify',
                                  user='mobile', required=False)
        if code != 0 or response.strip() != b'remed1st notification submitted':
            detail = response.decode(errors='replace').strip()
            raise RuntimeError('Jailbreak and Cydia are verified, but the iPhone notification '
                               'could not be submitted. ' + detail[-200:])

    def __call__(self, expected, flow):
        try:
            flow.notify('Starting the temporary SSH system…', 0.5)
            self.load_bootloaders(expected, flow, 'rd')
            # Device is now in Recovery mode (iBEC running) — no ECID selector.
            self.recovery(expected, flow, '-f', self.assets/'bootlogo.img3', ecid=False)
            self.recovery(expected, flow, '-c', 'setpicture 0x1', ecid=False)
            self.recovery(expected, flow, '-f', self.assets/'ramdisk.img3', ecid=False)
            self.recovery(expected, flow, '-c', 'ramdisk', ecid=False)
            self.boot_kernel(expected, flow, 'rd')
            self.start_ssh(expected, flow)
            self.check_ramdisk(flow)
            self.phone_status(flow,'preparing')
            flow.notify('Verifying the iOS version and activation file…', 0.65)
            self.hacktivate(flow)
            ensure_cydia(self, flow)
            self.phone_status(flow,'reboot')
            flow.notify('Cydia is installed. Restarting your iPhone…', 0.88)
            # Stock reboot performs kernel shutdown/sync/unmount itself. No
            # external sync, mount-update or kloader handoff is required.
            self.ssh(flow, '/sbin/reboot_bak', required=False)
            self.stop_proxy()
            state = self.wait_normal(expected, flow)
            self.install_untether_package(state, flow)
            self.verify_cydia(state, flow)
            self.notify_completion(flow)
            flow.notify('Done. Your iPhone is activated and Cydia is on the Home screen.', 1.0)
            return True
        finally:
            self.stop_proxy()
