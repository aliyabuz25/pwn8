"""Monochrome, stage-driven screens for the temporary iPhone ramdisk."""
import hashlib
import html
from pathlib import Path
import struct
import tarfile
import xml.etree.ElementTree as ET

DISPLAY_VERSION = 3
STAGES = {
    'injecting':'Injecting Payload',
    'preparing':'Preparing Filesystem',
    'untether':'Applying Untether',
    'cydia':'Installing Cydia',
    'reboot':'Rebooting Device',
}


def fingerprint(project):
    digest=hashlib.sha256(str((DISPLAY_VERSION,STAGES)).encode())
    for name in ('assets/remed-mark.svg','assets/remed1st-display'):
        digest.update((project/name).read_bytes())
    return digest.hexdigest()


def screen_svg(mark, message):
    root=ET.fromstring(mark)
    fragments=[]
    for element in root:
        name=element.tag.rsplit('}',1)[-1]
        if name=='defs':fragments.append(ET.tostring(element,encoding='unicode'))
        elif name=='path':
            element.set('fill','#ffffff')
            fragments.append(ET.tostring(element,encoding='unicode'))
    if not fragments:raise RuntimeError('The remed1st logo has no vector paths.')
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="960" viewBox="0 0 640 960">'
        '<rect width="640" height="960" fill="black"/>'
        '<g transform="translate(224 282) scale(2)">'+''.join(fragments)+'</g>'
        '<text x="320" y="525" text-anchor="middle" fill="white" font-family="Helvetica Neue,Helvetica,sans-serif" font-size="34" font-weight="600">remed1st</text>'
        '<text x="320" y="581" text-anchor="middle" fill="#d9d9d9" font-family="Helvetica Neue,Helvetica,sans-serif" font-size="24">'+html.escape(message)+'</text>'
        '<text x="320" y="636" text-anchor="middle" fill="#6e6e6e" font-family="Helvetica Neue,Helvetica,sans-serif" font-size="13" letter-spacing="3">REMED1ST BETA</text></svg>')


def encode_frame(pixels):
    if len(pixels)!=640*960:
        raise ValueError('A status frame must contain exactly 640x960 monochrome pixels.')
    return struct.pack('<4sIII',b'RMD1',640,960,1)+pixels


def patch_startup(original):
    marker=b'\n/sbin/sshd\n'
    if original.count(marker)!=1 or not original.startswith(b'#!/bin/sh\n'):
        raise RuntimeError('The SSH ramdisk startup script is unrecognized.')
    # boot_assets already renamed /sbin/reboot at image-build time via hfsplus;
    # remove the runtime mv so the boot script does not fail on a missing file.
    cleaned=original.replace(b'\nmv /sbin/reboot /sbin/reboot_bak\n',b'\n')
    # Insert the log redirect AFTER mount / so the filesystem is read-write
    # before we try to create the log file.
    if b'\nmount /\n' not in cleaned:
        raise RuntimeError('The SSH ramdisk startup script is missing "mount /".')
    patched=cleaned.replace(b'\nmount /\n',
        b'\nmount /\nexec >/remed1st-screen/boot.log 2>&1\n',1)
    return patched.replace(marker,
        b'\n/remed1st-screen/display >/remed1st-screen/display.log 2>&1 &\n/sbin/sshd\n')


def prepare_display(project, output):
    # Use the same SVG loader already shipped with the GTK application.
    import gi
    gi.require_version('GdkPixbuf','2.0')
    from gi.repository import GdkPixbuf
    mark=(project/'assets/remed-mark.svg').read_text()
    output.mkdir(parents=True,exist_ok=True)
    for key,message in STAGES.items():
        vector=output/f'screen-{key}.svg'
        vector.write_text(screen_svg(mark,message))
        pixbuf=GdkPixbuf.Pixbuf.new_from_file(str(vector))
        if (pixbuf.get_width(),pixbuf.get_height())!=(640,960):
            raise RuntimeError('The on-device screen dimensions are incorrect.')
        pixbuf.savev(str(output/f'screen-{key}.png'),'png',[],[])
        source=pixbuf.get_pixels();stride=pixbuf.get_rowstride();channels=pixbuf.get_n_channels()
        pixels=b''.join(source[y*stride:y*stride+640*channels:channels] for y in range(960))
        (output/f'screen-{key}.rmd').write_bytes(encode_frame(pixels))
    with tarfile.open(project.parent/'Legacy-iOS-Kit/resources/sshrd/ssh.tar.gz') as archive:
        original=archive.extractfile('./private/etc/rc.boot').read()
    (output/'display-startup.sh').write_bytes(patch_startup(original))
