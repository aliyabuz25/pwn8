"""Read-only device discovery using libimobiledevice command-line tools."""
from dataclasses import asdict, dataclass, field
import os
from pathlib import Path
import plistlib
import shutil
import subprocess

PROJECT = Path(__file__).resolve().parent.parent
MODELS = {
    'iPhone16,1': 'iPhone 15 Pro', 'iPhone16,2': 'iPhone 15 Pro Max',
    'iPhone15,4': 'iPhone 15', 'iPhone15,5': 'iPhone 15 Plus',
    'iPhone2,1': 'iPhone 3GS', 'iPhone3,1': 'iPhone 4 (GSM)',
    'iPhone3,2': 'iPhone 4 (GSM Rev A)', 'iPhone3,3': 'iPhone 4 (CDMA)',
    'iPhone4,1': 'iPhone 4S', 'iPod3,1': 'iPod touch 3', 'iPod4,1': 'iPod touch 4',
    'iPad1,1': 'iPad', 'iPad2,1': 'iPad 2 (Wi-Fi)', 'iPad2,2': 'iPad 2 (GSM)',
    'iPad2,3': 'iPad 2 (CDMA)', 'iPad2,4': 'iPad 2 (Rev A)',
    'iPad3,1': 'iPad 3 (Wi-Fi)', 'iPad3,2': 'iPad 3 (CDMA)', 'iPad3,3': 'iPad 3 (GSM)',
}

LEGACY_511 = {p for p in MODELS if not p.startswith(('iPhone15,', 'iPhone16,'))}

@dataclass
class DeviceState:
    connected: bool = False
    mode: str = 'Disconnected'
    name: str = 'Waiting for iPhone'
    model: str = '—'
    product: str = '—'
    version: str = '—'
    build: str = '—'
    serial: str = '—'
    udid: str = '—'
    ecid: str = '—'
    chip_id: int | None = None
    pwned: str = ''
    activation: str = '—'
    supported: bool = False
    message: str = 'Connect your iPhone via USB and unlock it.'
    tools: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def find_tool(name):
    roots = []
    if os.environ.get('REMED1ST_TOOLS_DIR'):
        roots.append(Path(os.environ['REMED1ST_TOOLS_DIR']))
    roots.extend([PROJECT / 'tools', PROJECT.parent / 'Legacy-iOS-Kit' / 'bin' / 'macos'])
    for root in roots:
        candidate = root / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return shutil.which(name)


def run_tool(tool, *args, timeout=5):
    return subprocess.run([tool, *args], capture_output=True, timeout=timeout, check=False)


def parse_normal(data):
    """Never reuse data from a previous connection or recovery-mode probe."""
    info = plistlib.loads(data)
    if not isinstance(info, dict) or not info.get('ProductType'):
        raise ValueError('Device response has no ProductType')
    product = str(info['ProductType'])
    version = str(info.get('ProductVersion', '—'))
    ecid = info.get('UniqueChipID')
    return DeviceState(
        connected=True, mode='Normal', name=str(info.get('DeviceName', 'iPhone')),
        model=MODELS.get(product, product), product=product, version=version,
        build=str(info.get('BuildVersion', '—')), serial=str(info.get('SerialNumber', '—')),
        udid=str(info.get('UniqueDeviceID', '—')), ecid=str(ecid) if ecid is not None else '—',
        activation=str(info.get('ActivationState', '—')), chip_id=info.get('ChipID'),
        supported=version == '5.1.1' and product in LEGACY_511,
        message='iOS 5.1.1 device information is available.' if version == '5.1.1' and product in LEGACY_511
                else 'Reading device information. Target iOS version: 5.1.1.',
    )


def parse_recovery(data):
    fields = {}
    for line in data.decode(errors='replace').splitlines():
        key, sep, value = line.partition(':')
        if sep:
            fields[key.strip().upper()] = value.strip()
    if not fields.get('MODE'):
        raise ValueError('No recovery device')
    product = fields.get('PRODUCT', '—')
    return DeviceState(
        connected=True, mode=fields['MODE'], name='Device in recovery mode',
        model=MODELS.get(product, fields.get('NAME', product)), product=product,
        ecid=fields.get('ECID', '—'), serial=fields.get('SRNM', '—'),
        chip_id=int(fields['CPID'], 16) if fields.get('CPID') else None,
        pwned=fields.get('PWND', ''),
        message='The installed iOS version is unavailable in this mode. It will be checked after boot.',
    )


def probe(runner=run_tool, resolver=find_tool):
    tools = {name: resolver(name) for name in ('ideviceinfo', 'irecovery')}
    state = DeviceState(tools=tools)
    if not tools['ideviceinfo']:
        state.message = 'ideviceinfo was not found. Run the setup script.'
        return state
    try:
        result = runner(tools['ideviceinfo'], '--xml')
        if result.returncode == 0:
            state = parse_normal(result.stdout)
            state.tools = tools
            return state
        error = result.stderr.decode(errors='replace').lower()
        if any(word in error for word in ('password', 'locked', 'trust', 'pair', 'denied')):
            state.message = 'Unlock your iPhone and accept Trust This Computer if prompted.'
    except subprocess.TimeoutExpired:
        state.message = 'The device timed out. Checking the connection again.'
    except (OSError, ValueError, plistlib.InvalidFileException):
        state.message = 'Could not read device information. Check the cable and pairing.'
    if tools['irecovery']:
        try:
            recovery = runner(tools['irecovery'], '-q', timeout=3)
            if recovery.returncode == 0:
                state = parse_recovery(recovery.stdout)
                state.tools = tools
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    return state

