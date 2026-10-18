import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from remed1st.untether_package import prepare_package, PACKAGE, VERSION, PAYLOAD_FILES, NOTIFY_PATH
from remed1st.pipeline import IOS511Pipeline
from test_flow import target


def ar_members(data):
    assert data[:8] == b'!<arch>\n'
    entries={};offset=8
    while offset<len(data):
        header=data[offset:offset+60]
        assert header[-2:]==b'`\n'
        size=int(header[48:58]);name=header[:16].decode().strip().rstrip('/')
        entries[name]=data[offset+60:offset+60+size]
        offset+=60+size+(size%2)
    return entries


class UntetherPackageTests(unittest.TestCase):
    def test_real_package_contains_correct_control_and_untether_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            result=prepare_package(output=Path(folder)/'untether.deb')
            members=ar_members(result.read_bytes())
            self.assertEqual(members['debian-binary'],b'2.0\n')
            with tarfile.open(fileobj=io.BytesIO(members['control.tar.gz'])) as archive:
                control=archive.extractfile('./control').read().decode()
                self.assertIn('Package: '+PACKAGE+'\n',control)
                self.assertIn('Name: '+PACKAGE+'\n',control)
                self.assertIn('Depends: firmware (= 5.1.1)',control)
                self.assertIn('g1lbertJB',control)
                script=archive.extractfile('./preinst').read()
                self.assertIn(b'iPhone3,1',script);self.assertIn(b'9B208',script)
            with tarfile.open(fileobj=io.BytesIO(members['data.tar.gz'])) as archive:
                self.assertEqual({x.name.removeprefix('./') for x in archive.getmembers()},PAYLOAD_FILES|{NOTIFY_PATH})
                self.assertTrue(all(x.uid==0 and x.gid==0 for x in archive.getmembers()))
                helper=archive.extractfile('./'+NOTIFY_PATH).read()
                self.assertIn(b'Thanks for using remed1st-beta @aliyabuz25',helper)
                self.assertIn(b'CFUserNotificationDisplayNotice',helper)

    def test_corrupt_upload_never_runs_dpkg(self):
        with tempfile.TemporaryDirectory() as folder:
            pipeline=IOS511Pipeline()
            pipeline.untether_deb=prepare_package(output=Path(folder)/'untether.deb')
            pipeline.start_ssh=Mock();pipeline.copy=Mock()
            pipeline.ssh=Mock(side_effect=[(0,b''),(0,b'corrupt')])
            with self.assertRaisesRegex(RuntimeError,'did not verify'):
                pipeline.install_untether_package(target(),Mock())
            self.assertFalse(any('/usr/bin/dpkg ' in str(call) for call in pipeline.ssh.call_args_list))

    def test_dpkg_registration_must_be_installed_with_the_display_name(self):
        with tempfile.TemporaryDirectory() as folder:
            pipeline=IOS511Pipeline()
            pipeline.untether_deb=prepare_package(output=Path(folder)/'untether.deb')
            pipeline.start_ssh=Mock();pipeline.copy=Mock()
            pipeline.ssh=Mock(side_effect=[(0,b''),(0,pipeline.untether_deb.read_bytes()),
                (0,b''),(0,('install ok installed\n'+VERSION+'\nwrong-name\n').encode())])
            with self.assertRaisesRegex(RuntimeError,'registration'):
                pipeline.install_untether_package(target(),Mock())
