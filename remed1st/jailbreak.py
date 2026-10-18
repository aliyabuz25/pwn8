"""Build-specific Cydia installation, preserving an existing bootstrap."""
import copy
import plistlib
import shlex
from pathlib import PurePosixPath
import tarfile
import tempfile
import time

from .boot_assets import KIT, PRODUCT, BUILD
from .device import PROJECT

BUNDLE_ID = 'com.saurik.Cydia'
JAILBREAK = KIT/'resources/jailbreak'


def cydia_info(data):
    try:
        return plistlib.loads(data).get('CFBundleIdentifier') == BUNDLE_ID
    except (ValueError, TypeError, AttributeError, plistlib.InvalidFileException):
        return False


def application_directory(listing):
    """Map an absolute on-device Applications stash into the mounted root."""
    line = listing.decode(errors='strict').strip()
    if ' -> ' not in line:
        return '/mnt1/Applications'
    target = line.split(' -> ', 1)[1]
    path = PurePosixPath(target)
    if '..' in path.parts:
        raise RuntimeError('Unrecognized Applications link. No application files were changed.')
    for prefix in ('/var/stash/', '/private/var/stash/'):
        if target.startswith(prefix):
            return '/mnt1/private/var/stash/' + target[len(prefix):]
    raise RuntimeError('Unrecognized Applications stash. No application files were changed.')


def install_archive(pipeline, flow, path, destination, cydia_only=False):
    # Decompress on the Mac: the tiny ramdisk lacks gzip and has little space.
    with tempfile.TemporaryFile() as payload:
        with tarfile.open(path, 'r:*') as archive:
            members = archive.getmembers()
            for member in members:
                name = PurePosixPath(member.name)
                if name.is_absolute() or '..' in name.parts:
                    raise RuntimeError('Unsafe bootstrap archive path.')
            with tarfile.open(fileobj=payload, mode='w') as output:
                count = 0
                for member in members:
                    name = member.name.removeprefix('./')
                    if cydia_only:
                        if not name.startswith('Applications/Cydia.app/') and name != 'Applications/Cydia.app':
                            continue
                        member = copy.copy(member)
                        member.name = name.removeprefix('Applications/')
                    output.addfile(member, archive.extractfile(member) if member.isfile() else None)
                    count += 1
                if not count:
                    raise RuntimeError('Cydia archive is empty.')
        payload.seek(0)
        pipeline.ssh(flow, 'set -e; /bin/tar -xpf - -C ' + shlex.quote(destination),
                     stdin=payload, timeout=180)


def ensure_cydia(pipeline, flow):
    # Mount data at its on-disk location before inspecting stashed applications.
    _, mounted = pipeline.ssh(flow, '/sbin/mount')
    if b' on /mnt1/private/var ' not in mounted:
        pipeline.ssh(flow, '/sbin/mount_hfs /dev/disk0s1s2 /mnt1/private/var')
    _, listing = pipeline.ssh(flow, '/bin/ls -ld /mnt1/Applications')
    apps = application_directory(listing)
    bootstrapped, _ = pipeline.ssh(flow,
        'test -x /mnt1/usr/bin/dpkg && test -x /mnt1/bin/bash', required=False)
    if bootstrapped == 0:
        flow.notify('Backing up the current jailbreak and Cydia files…', 0.77)
        backup_existing(pipeline, flow, apps)
        flow.notify('Reapplying the iOS 5.1.1 jailbreak and Cydia…', 0.78)
        pipeline.phone_status(flow,'untether')
        install_archive(pipeline, flow, JAILBREAK/f'g1lbertJB/{PRODUCT}_{BUILD}.tar', '/mnt1')
        pipeline.phone_status(flow,'cydia')
        install_archive(pipeline, flow, JAILBREAK/'freeze.tar.gz', apps, cydia_only=True)
    elif bootstrapped == 1:
        # Never replace a partially existing dpkg database with a fresh one.
        db, _ = pipeline.ssh(flow, 'test -e /mnt1/private/var/lib/dpkg/status', required=False)
        if db != 1:
            raise RuntimeError('An existing or unreadable package database needs manual repair. It was preserved.')
        flow.notify('Installing the iOS 5.1.1 untether and Cydia bootstrap…', 0.78)
        for name in (f'g1lbertJB/{PRODUCT}_{BUILD}.tar', 'freeze.tar.gz',
                     'cydiasubstrate.tar', 'nopatcyh.tar', 'sshdeb.tar',
                     'openssl.tar.gz', 'openssh.tar.gz'):
            if name.startswith('g1lbertJB/'):
                pipeline.phone_status(flow,'untether')
            elif name=='freeze.tar.gz':
                pipeline.phone_status(flow,'cydia')
            install_archive(pipeline, flow, JAILBREAK/name, '/mnt1')
        apps = '/mnt1/Applications'
    else:
        raise RuntimeError('Could not check the existing jailbreak. No bootstrap was installed.')
    _, info = pipeline.ssh(flow, 'cat ' + shlex.quote(apps+'/Cydia.app/Info.plist'))
    pipeline.ssh(flow, 'test -x ' + shlex.quote(apps+'/Cydia.app/Cydia'))
    if not cydia_info(info):
        raise RuntimeError('The Cydia application could not be verified after installation.')
    with tarfile.open(JAILBREAK/f'g1lbertJB/{PRODUCT}_{BUILD}.tar') as archive:
        for member in archive.getmembers():
            if member.isfile():
                path = '/mnt1/' + member.name.removeprefix('./')
                _, installed = pipeline.ssh(flow, 'cat ' + shlex.quote(path))
                if installed != archive.extractfile(member).read():
                    raise RuntimeError('The reinstalled jailbreak file did not verify: ' + member.name)


def backup_existing(pipeline, flow, apps):
    backup_dir = PROJECT/'backups'
    backup_dir.mkdir(exist_ok=True)
    target = backup_dir/('jailbreak-before-'+str(time.time_ns())+'.tar')
    paths = ('private/etc/launchd.conf', 'usr/libexec/dirhelper',
             'private/var/unthreadedjb', apps.removeprefix('/mnt1/')+'/Cydia.app')
    script = 'set -e; cd /mnt1; set --; for item in ' + ' '.join(map(shlex.quote, paths)) + '; do '
    script += 'if [ -e "$item" ]; then set -- "$@" "$item"; fi; done; '
    script += 'if [ "$#" -gt 0 ]; then /bin/tar -cpf - "$@"; fi'
    try:
        with target.open('xb') as output:
            pipeline.command(flow, pipeline.ssh_argv(flow, script), timeout=120, stdout_file=output)
        if target.stat().st_size:
            with tarfile.open(target) as archive:
                # Read the complete payload so truncated file data is detected.
                for member in archive:
                    if member.isfile():
                        stream = archive.extractfile(member)
                        remaining = member.size
                        while remaining:
                            block = stream.read(min(1024*1024, remaining))
                            if not block:
                                raise RuntimeError('The jailbreak backup is incomplete.')
                            remaining -= len(block)
    except Exception:
        if target.exists():
            target.rename(target.with_suffix('.incomplete'))
        raise
