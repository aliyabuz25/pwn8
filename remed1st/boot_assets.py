"""Prepare model/build-specific RAM-only boot assets; never flashes firmware."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import zipfile
from .device import PROJECT
from .boot_display import STAGES, DISPLAY_VERSION, fingerprint, prepare_display

KIT = PROJECT.parent/'Legacy-iOS-Kit'
PRODUCT, VERSION, BUILD = 'iPhone3,1', '5.1.1', '9B208'
ASSETS = PROJECT/'runtime/boot-iPhone3,1-9B208'
REQUIRED_FILES = (
    'boot-iBSS.patched','boot-iBSS.img3','boot-iBEC.img3','boot-DeviceTree.img3','boot-Kernelcache.img3',
    'bootlogo.img3','rd-iBSS.img3','rd-iBEC.img3','rd-DeviceTree.img3','rd-Kernelcache.img3',
    'ramdisk.img3','kloader','lockdownd.original','lockdownd.patched',
    'screen-injecting.png', 'display-helper', 'display-startup.sh',
    *(f'screen-{key}.rmd' for key in STAGES),
)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


class BootAssets:
    def __init__(self, notify=lambda *_:None, check_cancel=lambda:None):
        self.notify=notify
        self.check_cancel=check_cancel
        self.tools=KIT/'bin/macos'
        self.out=ASSETS

    def run(self,name,*args,timeout=180):
        tool=('/usr/bin/'+name) if name in ('bspatch','sips') else str(self.tools/name)
        if name=='iBoot32Patcher':
            Path(args[1]).unlink(missing_ok=True)
        self.check_cancel()
        argv=[tool,*map(str,args)]
        process=subprocess.Popen(argv,cwd=self.out,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        deadline=time.monotonic()+timeout
        try:
            while True:
                try:
                    stdout,stderr=process.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    self.check_cancel()
                    if time.monotonic()>deadline:raise RuntimeError(name+' timed out.')
            result=subprocess.CompletedProcess(argv,process.returncode,stdout,stderr)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
        patch_ok = name=='iBoot32Patcher' and result.returncode==1 and Path(args[1]).is_file() and Path(args[1]).stat().st_size==Path(args[0]).stat().st_size and sha(args[1])!=sha(args[0]) and b'main: Quitting' in result.stdout and b'error' not in result.stdout.lower()
        if result.returncode and not patch_ok:
            raise RuntimeError(name+': '+(result.stdout+result.stderr).decode(errors='replace')[-900:])
        return result

    def keys(self,build):
        data=json.loads((KIT/f'saved/firmware/{PRODUCT}/{build}/index.html').read_text())
        if data['identifier']!=PRODUCT or data['buildid']!=build:raise RuntimeError('Firmware key identity mismatch.')
        return {item['image']:item for item in data['keys']}

    def valid(self):
        try:
            data=json.loads((self.out/'manifest.json').read_text())
            if (data.get('product'),data.get('version'),data.get('build'))!=(PRODUCT,VERSION,BUILD):return False
            if data.get('boot_display_version')!=DISPLAY_VERSION:return False
            if data.get('display_fingerprint')!=fingerprint(PROJECT):return False
            if set(data['files'])!=set(REQUIRED_FILES):return False
            return all(sha(self.out/n)==h for n,h in data['files'].items())
        except (OSError,KeyError,ValueError):return False

    def decrypt(self,build,source,key,out):
        self.run('xpwntool',source,out,'-iv',key['iv'],'-k',key['key'],'-decrypt')

    def prepare(self):
        self.check_cancel()
        if self.valid():return self.out
        self.out.mkdir(parents=True,exist_ok=True)
        ipsw=KIT/f'{PRODUCT}_{VERSION}_{BUILD}_Restore.ipsw'
        keys5,keys6=self.keys(BUILD),self.keys('10B329')
        if not ipsw.is_file():
            raise RuntimeError('The iOS 5.1.1 IPSW is missing.')
        self.notify('Preparing boot and activation files…',0.01)
        for name in ('xpwntool','iBoot32Patcher','ibootim','img3maker','hfsplus','dmg'):
            if not (self.tools/name).is_file():raise RuntimeError(name+' tool is missing.')
        with zipfile.ZipFile(ipsw) as archive:
            import plistlib
            meta=plistlib.loads(archive.read('Restore.plist'))
            if (meta.get('ProductType'),meta.get('ProductVersion'),meta.get('ProductBuildVersion'))!=(PRODUCT,VERSION,BUILD):
                raise RuntimeError('IPSW model or version mismatch.')
            for image in ('iBSS','iBEC','DeviceTree','Kernelcache'):
                key=keys5[image];name=key['filename']
                member=next(n for n in archive.namelist() if n.endswith('/'+name) or n==name)
                source=self.out/f'boot-{image}.original'
                with archive.open(member) as src,source.open('wb') as dst:shutil.copyfileobj(src,dst)
                self.decrypt(BUILD,source,key,self.out/f'boot-{image}.img3')
            self.notify('Verifying the iOS 5.1.1 activation patch…',0.02)
            key=keys5['RootFS'];source=self.out/'rootfs-encrypted.dmg';raw=self.out/'rootfs-dec.hfs'
            try:
                if shutil.disk_usage(self.out).free < 3_000_000_000:raise RuntimeError('At least 3 GB of free disk space is required for preparation.')
                with archive.open(key['filename']) as src,source.open('wb') as dst:shutil.copyfileobj(src,dst)
                self.run('dmg','extract',source,raw,'-k',key['key'],timeout=300)
                self.run('hfsplus',raw,'extract','usr/libexec/lockdownd',self.out/'lockdownd.original')
            finally:
                for path in (source,raw):
                    if path.exists():path.unlink()
        patch=KIT/'resources/firmware/FirmwareBundles/Down_iPhone2,1_5.1.1_9B206.bundle/lockdownd.patch'
        self.run('bspatch',self.out/'lockdownd.original',self.out/'lockdownd.patched',patch)
        for image in ('iBSS','iBEC'):
            dec=self.out/f'boot-{image}.img3';raw=self.out/f'boot-{image}.raw';patched=self.out/f'boot-{image}.patched'
            self.run('xpwntool',dec,raw)
            self.run('iBoot32Patcher',raw,patched,*(['--rsa'] if image=='iBSS' else ['--rsa','-b','rd=disk0s1s1']))
            self.run('xpwntool',patched,self.out/f'boot-{image}.ready','-t',dec)
            (self.out/f'boot-{image}.ready').replace(dec)
        prepare_display(PROJECT,self.out)
        shutil.copy2(PROJECT/'assets/remed1st-display',self.out/'display-helper')
        self.run('ibootim',self.out/'screen-injecting.png',self.out/'bootlogo.ibootim')
        self.run('img3maker','-f',self.out/'bootlogo.ibootim','-o',self.out/'bootlogo.img3','-t','logo')
        self.notify('Preparing the temporary SSH ramdisk…',0.03)
        source_dir=KIT/f'saved/{PRODUCT}/ramdisk_10B329'
        for image in ('iBSS','iBEC','DeviceTree','Kernelcache','RestoreRamdisk'):
            key=keys6[image];source=source_dir/key['filename']
            if not source.is_file():raise RuntimeError('Missing ramdisk component: '+source.name)
            self.decrypt('10B329',source,key,self.out/f'rd-{image}.img3')
        for image in ('iBSS','iBEC'):
            dec=self.out/f'rd-{image}.img3';raw=self.out/f'rd-{image}.raw';patched=self.out/f'rd-{image}.patched'
            self.run('xpwntool',dec,raw)
            self.run('iBoot32Patcher',raw,patched,*(['--rsa'] if image=='iBSS' else ['--rsa','--debug','-b','rd=md0 -v amfi=0xff cs_enforcement_disable=1 pio-error=0']))
            self.run('xpwntool',patched,self.out/f'rd-{image}.ready','-t',dec)
            (self.out/f'rd-{image}.ready').replace(dec)
        raw=self.out/'ramdisk.hfs'
        self.run('xpwntool',self.out/'rd-RestoreRamdisk.img3',raw)
        self.run('hfsplus',raw,'grow','32000000')
        self.run('hfsplus',raw,'untar',KIT/'resources/sshrd/sbplist.tar')
        ssh_tar=self.out/'ssh.tar'
        with gzip.open(KIT/'resources/sshrd/ssh.tar.gz','rb') as src,ssh_tar.open('wb') as dst:shutil.copyfileobj(src,dst)
        self.run('hfsplus',raw,'untar',ssh_tar)
        self.run('hfsplus',raw,'mv','sbin/reboot','sbin/reboot_bak')
        self.run('hfsplus',raw,'mv','sbin/halt','sbin/halt_bak')
        self.run('hfsplus',raw,'mkdir','remed1st-screen')
        self.run('hfsplus',raw,'add',self.out/'display-helper','remed1st-screen/display')
        self.run('hfsplus',raw,'chmod','755','remed1st-screen/display')
        self.run('hfsplus',raw,'add',self.out/'screen-injecting.rmd','remed1st-screen/frame.rmd')
        self.run('hfsplus',raw,'add',self.out/'display-startup.sh','private/etc/rc.boot')
        self.run('hfsplus',raw,'chmod','755','private/etc/rc.boot')
        self.run('hfsplus',raw,'chown','0:0','private/etc/rc.boot')
        self.run('xpwntool',raw,self.out/'ramdisk.img3','-t',self.out/'rd-RestoreRamdisk.img3')
        shutil.copy2(KIT/'resources/kloader/kloader',self.out/'kloader')
        data={'product':PRODUCT,'version':VERSION,'build':BUILD,'boot_display_version':DISPLAY_VERSION,
              'display_fingerprint':fingerprint(PROJECT),
              'files':{name:sha(self.out/name) for name in REQUIRED_FILES}}
        (self.out/'manifest.json').write_text(json.dumps(data,indent=2)+'\n')
        return self.out
