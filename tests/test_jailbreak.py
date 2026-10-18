import plistlib
from pathlib import Path
import unittest
import tempfile
import tarfile
import io
from unittest.mock import Mock, patch
from remed1st.jailbreak import application_directory, cydia_info, ensure_cydia
from remed1st.icons import contains_cydia
from remed1st.pipeline import IOS511Pipeline
from test_flow import target


class JailbreakTests(unittest.TestCase):
    def test_stashed_apps_map_to_data_volume(self):
        self.assertEqual(application_directory(b'Applications -> /var/stash/Applications.abc'),
            '/mnt1/private/var/stash/Applications.abc')
        with self.assertRaises(RuntimeError):
            application_directory(b'Applications -> /var/stash/../../etc')

    def test_existing_cydia_reapplies_jailbreak_and_preserves_package_database(self):
        pipeline=Mock()
        info=plistlib.dumps({'CFBundleIdentifier':'com.saurik.Cydia'})
        pipeline.ssh.side_effect=[(0,b'disk on /mnt1/private/var (hfs)'),
            (0,b'drwxr-xr-x Applications'),(0,b''),(0,info),(0,b''),(0,b'untether')]
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'g1lbertJB').mkdir()
            payload=root/'g1lbertJB/iPhone3,1_9B208.tar'
            with tarfile.open(payload,'w') as archive:
                item=tarfile.TarInfo('./private/var/unthreadedjb/jb');item.size=8
                archive.addfile(item,io.BytesIO(b'untether'))
            with patch('remed1st.jailbreak.JAILBREAK',root), patch(
                    'remed1st.jailbreak.backup_existing') as backup, patch(
                    'remed1st.jailbreak.install_archive') as install:
                ensure_cydia(pipeline,Mock())
                backup.assert_called_once()
                self.assertEqual(install.call_count,2)
                self.assertEqual(install.call_args_list[0].args[2],payload)
                self.assertTrue(install.call_args_list[1].kwargs['cydia_only'])
                self.assertFalse(any('nopatcyh' in str(call) for call in install.call_args_list))

    def test_backup_failure_prevents_reapplying_jailbreak(self):
        pipeline=Mock()
        pipeline.ssh.side_effect=[(0,b'disk on /mnt1/private/var (hfs)'),
            (0,b'drwxr-xr-x Applications'),(0,b'')]
        with patch('remed1st.jailbreak.backup_existing',side_effect=RuntimeError('Backup failed')), patch(
                'remed1st.jailbreak.install_archive') as install:
            with self.assertRaisesRegex(RuntimeError,'Backup failed'):
                ensure_cydia(pipeline,Mock())
            install.assert_not_called()

    def test_success_requires_real_cydia_identifier_and_icon(self):
        self.assertFalse(cydia_info(plistlib.dumps({'CFBundleIdentifier':'other'})))
        self.assertTrue(contains_cydia([[{'iconLists':[[{'displayIdentifier':'com.saurik.Cydia'}]]}]]))
        self.assertFalse(contains_cydia([[{'displayIdentifier':'com.apple.Preferences'}]]))

    def pipeline(self):
        pipeline=IOS511Pipeline();pipeline.assets=Path('/assets')
        for name in ('load_bootloaders','recovery','boot_kernel','start_ssh',
                     'check_ramdisk','hacktivate','verify_cydia','stop_proxy','install_untether_package',
                     'notify_completion','phone_status'):
            setattr(pipeline,name,Mock())
        pipeline.ssh=Mock(return_value=(0,b''))
        pipeline.wait_normal=Mock(return_value=target(mode='Normal'))
        return pipeline

    def test_main_flow_reboots_without_kloader_or_remount(self):
        pipeline=self.pipeline()
        with patch('remed1st.pipeline.ensure_cydia') as install:
            self.assertTrue(pipeline(target(),Mock()))
            install.assert_called_once()
        self.assertEqual(pipeline.ssh.call_args.args[1],'/sbin/reboot_bak')
        pipeline.verify_cydia.assert_called_once()

    def test_failed_icon_verification_never_reports_success(self):
        pipeline=self.pipeline()
        pipeline.verify_cydia=Mock(side_effect=RuntimeError('No Cydia icon'))
        flow=Mock()
        with patch('remed1st.pipeline.ensure_cydia'), self.assertRaises(RuntimeError):
            pipeline(target(),flow)
        self.assertFalse(any(args.args[1] == 1.0 for args in flow.notify.call_args_list))
        pipeline.notify_completion.assert_not_called()

    def test_notification_occurs_only_after_package_and_cydia_verification(self):
        pipeline=self.pipeline()
        order=[]
        pipeline.install_untether_package.side_effect=lambda *args:order.append('package')
        pipeline.verify_cydia.side_effect=lambda *args:order.append('cydia')
        pipeline.notify_completion.side_effect=lambda *args:order.append('notification')
        with patch('remed1st.pipeline.ensure_cydia'):
            self.assertTrue(pipeline(target(),Mock()))
        self.assertEqual(order,['package','cydia','notification'])

    def test_notification_failure_is_reported(self):
        pipeline=IOS511Pipeline()
        pipeline.ssh=Mock(return_value=(1,b'notification unavailable'))
        with self.assertRaisesRegex(RuntimeError,'could not be submitted'):
            pipeline.notify_completion(Mock())
