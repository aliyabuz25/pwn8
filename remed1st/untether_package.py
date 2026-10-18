"""Package the verified, build-specific upstream untether under the tool's name."""
import gzip
import hashlib
import io
import tarfile
import struct
from .boot_assets import KIT, PRODUCT, BUILD
from .device import PROJECT

PACKAGE = 'remed1st-untether5'
VERSION = '1.0.1'
PAYLOAD_FILES = {
    'private/etc/launchd.conf',
    'private/var/unthreadedjb/amfi.dylib',
    'private/var/unthreadedjb/jb',
    'usr/libexec/dirhelper',
}
NOTIFY_PATH = 'usr/libexec/remed1st-notify'

PREINST = b'''#!/bin/sh
set -e
if [ "$(/usr/sbin/sysctl -n hw.machine)" != "iPhone3,1" ]; then
    echo 'remed1st-untether5 requires iPhone3,1.' >&2
    exit 1
fi
if ! /bin/grep -q '<string>9B208</string>' /System/Library/CoreServices/SystemVersion.plist; then
    echo 'remed1st-untether5 requires iOS 5.1.1 build 9B208.' >&2
    exit 1
fi
'''


def tar_gz(entries):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name, data, mode in entries:
            item = tarfile.TarInfo('./' + name)
            item.size, item.mode, item.uid, item.gid = len(data), mode, 0, 0
            item.uname = item.gname = 'root'
            archive.addfile(item, io.BytesIO(data))
    return gzip.compress(output.getvalue(), mtime=0)


def prepare_package(source=None, output=None):
    source = source or KIT/f'resources/jailbreak/g1lbertJB/{PRODUCT}_{BUILD}.tar'
    output = output or PROJECT/'packages'/f'{PACKAGE}_{VERSION}_iphoneos-arm.deb'
    entries = []
    with tarfile.open(source) as archive:
        for member in archive.getmembers():
            if member.isfile():
                name = member.name.removeprefix('./')
                if name not in PAYLOAD_FILES:
                    raise RuntimeError('Unexpected untether package file: ' + name)
                entries.append((name, archive.extractfile(member).read(),
                                0o644 if name.endswith('launchd.conf') else 0o755))
    if {name for name, _, _ in entries} != PAYLOAD_FILES or len(entries) != len(PAYLOAD_FILES):
        raise RuntimeError('The untether package payload is incomplete.')
    helper = (PROJECT/'assets/remed1st-notify').read_bytes()
    if len(helper)<28 or struct.unpack_from('<II',helper)!=(0xfeedface,12):
        raise RuntimeError('The notification helper must be a legacy ARM Mach-O executable.')
    entries.append((NOTIFY_PATH,helper,0o755))
    size = (sum(len(data) for _, data, _ in entries) + 1023)//1024
    control = f'''Package: {PACKAGE}
Name: {PACKAGE}
Version: {VERSION}
Architecture: iphoneos-arm
Maintainer: aliyabuz25
Section: System
Priority: required
Essential: yes
Depends: firmware (= 5.1.1)
Installed-Size: {size}
Description: remed1st untether package for iPhone 4 on iOS 5.1.1
 Build-specific g1lbertJB untether distributed through Legacy-iOS-Kit,
 packaged by aliyabuz25 for remed1st. Upstream exploit authors retain credit.
 This package provides the installed jailbreak boot files.
Tag: purpose::console, cydia::essential, role::enduser
'''.encode()
    md5sums = ''.join(hashlib.md5(data).hexdigest()+'  '+name+'\n'
                      for name,data,_ in entries).encode()
    members = [('debian-binary', b'2.0\n'),
        ('control.tar.gz', tar_gz([('control',control,0o644),('preinst',PREINST,0o755),
                                  ('md5sums',md5sums,0o644),
                                  ('conffiles',b'/private/etc/launchd.conf\n',0o644)])),
        ('data.tar.gz', tar_gz(entries))]
    package = io.BytesIO(); package.write(b'!<arch>\n')
    for name, data in members:
        header = f'{name+"/":<16}{0:<12}{0:<6}{0:<6}{"100644":<8}{len(data):<10}`\n'.encode('ascii')
        package.write(header); package.write(data)
        if len(data)%2: package.write(b'\n')
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary = output.with_suffix('.tmp')
    temporary.write_bytes(package.getvalue())
    temporary.replace(output)
    return output
