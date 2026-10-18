import plistlib
import json
import subprocess
import tempfile
import itertools
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from remed1st.boot_assets import BootAssets, BUILD, PRODUCT, VERSION, sha, REQUIRED_FILES
from remed1st.boot_display import DISPLAY_VERSION, fingerprint
from remed1st.flow import Limera1nFlow
from remed1st.pipeline import IOS511Pipeline, RAM_WORK, RAM_KLOADER, RAM_IBSS, firmware_supported, patch_required, validate_system
from test_flow import target, response


class PipelineTests(unittest.TestCase):
    def test_software_reconnect_is_bounded_and_requires_device_verification(self):
        pipeline = IOS511Pipeline()
        pipeline.soft_reconnect = Mock(return_value=True)
        flow = Mock()
        flow.query.return_value = None
        with patch('remed1st.pipeline.time.monotonic',side_effect=itertools.count()):
            self.assertFalse(pipeline.wait_recovery(target(),flow,seconds=40,required=False))
        self.assertEqual(pipeline.soft_reconnect.call_count,2)

    def test_visible_wrong_mode_does_not_trigger_usb_reset(self):
        pipeline = IOS511Pipeline()
        pipeline.soft_reconnect = Mock()
        flow = Mock()
        flow.query.return_value = target(mode='DFU')
        with patch('remed1st.pipeline.time.monotonic',side_effect=itertools.count()):
            self.assertFalse(pipeline.wait_recovery(target(),flow,seconds=20,required=False,mode='Recovery'))
        pipeline.soft_reconnect.assert_not_called()

    def test_reconnect_only_selects_the_original_ecid(self):
        pipeline = IOS511Pipeline()
        pipeline.command = Mock(return_value=(0,b''))
        flow = Mock()
        flow.resolver.return_value = '/tool/usb-reconnect'
        expected = target(ecid='123')
        self.assertTrue(pipeline.soft_reconnect(expected,flow))
        self.assertEqual(pipeline.command.call_args.args[1],
                         ['/tool/usb-reconnect','--reenumerate','0x7b'])


    def test_asset_cache_rejects_missing_kloader_or_empty_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'bootlogo.png').write_bytes(b'logo')
            (root/'assets').mkdir()
            (root/'assets/remed-mark.svg').write_bytes(b'logo')
            (root/'assets/remed1st-display').write_bytes(b'display')
            builder = BootAssets()
            builder.out = root
            hashes = {}
            for name in REQUIRED_FILES:
                (root/name).write_bytes(name.encode())
                hashes[name] = sha(root/name)
            data = {'product':PRODUCT,'version':VERSION,'build':BUILD,
                'boot_display_version':DISPLAY_VERSION,'display_fingerprint':fingerprint(root),'files':hashes}
            manifest = root/'manifest.json'
            manifest.write_text(json.dumps(data))
            with patch('remed1st.boot_assets.PROJECT',root):
                self.assertTrue(builder.valid())
                (root/'kloader').unlink()
                self.assertFalse(builder.valid())
                data['files'] = {}
                manifest.write_text(json.dumps(data))
                self.assertFalse(builder.valid())

    def test_wrong_firmware_blocked_before_device_changes(self):
        pipeline = IOS511Pipeline()
        runner = Mock()
        flow = Limera1nFlow(Mock(), runner=runner, resolver=lambda n: n,
            preflight=pipeline.preflight, after_pwn=pipeline)
        flow.execute_exploit = Mock()
        self.assertFalse(flow.run(target(mode='Normal', version='6.1.3', build='10B329')))
        runner.assert_not_called()
        flow.execute_exploit.assert_not_called()

    def test_disk_version_checked_independently_of_initial_state(self):
        validate_system(plistlib.dumps({'ProductVersion': '5.1.1', 'ProductBuildVersion': '9B208'}))
        for version, build in [('5.1.1', '9B206'), ('6.1.3', '10B329')]:
            with self.assertRaises(RuntimeError):
                validate_system(plistlib.dumps({'ProductVersion': version, 'ProductBuildVersion': build}))

    def test_unknown_lockdownd_rejected_and_known_patch_idempotent(self):
        self.assertTrue(patch_required('original', 'original', 'patched'))
        self.assertFalse(patch_required('patched', 'original', 'patched'))
        with self.assertRaises(RuntimeError):
            patch_required('unknown', 'original', 'patched')

    def test_already_pwned_continues_pipeline(self):
        after = Mock(return_value=True)
        flow = Limera1nFlow(Mock(), runner=Mock(return_value=response(pwned='limera1n')),
            resolver=lambda n: n, counter=lambda: 1, after_pwn=after)
        flow.execute_exploit = Mock()
        expected = target()
        self.assertTrue(flow.run(expected))
        after.assert_called_once_with(expected, flow)
        flow.execute_exploit.assert_not_called()

    def test_asset_preparation_failure_prevents_recovery_and_exploit(self):
        preflight = Mock(side_effect=RuntimeError('IPSW eksik'))
        runner = Mock()
        flow = Limera1nFlow(Mock(), runner=runner, resolver=lambda n: n, preflight=preflight)
        flow.execute_exploit = Mock()
        self.assertFalse(flow.run(target()))
        runner.assert_not_called()
        flow.execute_exploit.assert_not_called()

    def test_corrupted_upload_never_replaces_lockdownd(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'lockdownd.original').write_bytes(b'original')
            (root/'lockdownd.patched').write_bytes(b'patched')
            pipeline = IOS511Pipeline()
            pipeline.assets = root
            flow = Mock()
            pipeline.mount_system = Mock()
            pipeline.ssh = Mock(side_effect=[(0, plistlib.dumps({
                'ProductVersion':'5.1.1', 'ProductBuildVersion':'9B208'})), (1, b'')])
            def copy(_flow, source, destination):
                if isinstance(destination, Path):
                    destination.write_bytes(b'original' if destination.name == 'lockdownd.before' else b'corrupt')
            pipeline.copy = Mock(side_effect=copy)
            with patch('remed1st.pipeline.PROJECT', root):
                with self.assertRaisesRegex(RuntimeError, 'checksum does not match'):
                    pipeline.hacktivate(flow)
            self.assertFalse(any('mv -f' in str(call) for call in pipeline.ssh.call_args_list))

    def test_dfu_version_unknown_is_checked_later(self):
        self.assertTrue(firmware_supported(target()))
        self.assertFalse(firmware_supported(target(product='iPhone3,3')))




    def test_optional_timeout_returns_status_and_reaps_process(self):
        pipeline = IOS511Pipeline()
        process = Mock()
        process.communicate.side_effect = [subprocess.TimeoutExpired('ssh',0.2),(b'',b'')]
        process.poll.return_value = None
        flow = Mock()
        with patch('remed1st.pipeline.subprocess.Popen',return_value=process), patch(
                'remed1st.pipeline.time.monotonic',side_effect=[0,2]):
            self.assertEqual(pipeline.command(flow,['ssh'],timeout=1,required=False)[0],124)
        process.kill.assert_called_once()
        self.assertIsNone(flow.process)


if __name__ == '__main__':
    unittest.main()
