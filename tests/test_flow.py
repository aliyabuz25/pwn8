"""Flow safety tests; hardware-changing commands are never executed here."""
import plistlib
import subprocess
import unittest
from unittest.mock import Mock, patch
from remed1st.device import DeviceState, parse_normal, probe
from remed1st.flow import Limera1nFlow, compatible, ecid_number, dfu_count


def target(**values):
    defaults=dict(connected=True, product='iPhone3,1', mode='DFU', ecid='123', chip_id=0x8930)
    defaults.update(values)
    return DeviceState(**defaults)


def response(mode='DFU', ecid='123', pwned=''):
    body=f'MODE: {mode}\nPRODUCT: iPhone3,1\nCPID: 0x8930\nECID: {ecid}\nPWND: {pwned}\n'
    return subprocess.CompletedProcess([], 0, body.encode(), b'')


class FlowTests(unittest.TestCase):
    def test_macos_counter_requests_usb_properties(self):
        tree=[{'IORegistryEntryChildren':[{'idVendor':0x5ac,'idProduct':0x1227}]}]
        with patch('remed1st.flow.platform.system', return_value='Darwin'), patch(
                'remed1st.flow.subprocess.run', return_value=subprocess.CompletedProcess(
                    [],0,plistlib.dumps(tree),b'')) as run:
            self.assertEqual(dfu_count(),1)
            self.assertIn('-l',run.call_args.args[0])

    def flow(self, runner=None, count=1):
        return Limera1nFlow(Mock(), runner=runner or Mock(return_value=response()),
            resolver=lambda name: '/tool/'+name, counter=lambda: count)

    def test_a5_and_modern_devices_blocked(self):
        for product in ('iPhone4,1', 'iPhone16,1', 'iPad2,1'):
            self.assertFalse(compatible(DeviceState(connected=True, product=product)))
        self.assertTrue(compatible(target()))
        self.assertFalse(compatible(target(chip_id=0x8940)))

    def test_wrong_ecid_never_exploited(self):
        f=self.flow(Mock(return_value=response(ecid='124')))
        f.execute_exploit=Mock()
        self.assertFalse(f.run(target()))
        f.execute_exploit.assert_not_called()

    def test_recovery_is_not_dfu(self):
        f=self.flow(Mock(return_value=response(mode='Recovery')))
        with self.assertRaisesRegex(RuntimeError,'DFU'):
            f.validate_dfu(target())

    def test_multiple_dfu_targets_blocked(self):
        f=self.flow(count=2);f.execute_exploit=Mock()
        self.assertFalse(f.run(target()))
        f.execute_exploit.assert_not_called()

    def test_cancel_never_runs_tool(self):
        f=self.flow();f.execute_exploit=Mock();f.cancel()
        self.assertFalse(f.run(target()))
        f.execute_exploit.assert_not_called()

    def test_success_requires_pwnd_verification(self):
        # query() calls: 1=found(DFU), 2=validate_dfu(DFU unpwned),
        # then verification loop sees pwned.
        unpwned=response(); pwned=response(pwned='limera1n')
        run=Mock(side_effect=[unpwned, unpwned] + [pwned]*30)
        f=self.flow(run)
        f.execute_exploit=Mock(return_value='[limera1n] pwned!')
        self.assertTrue(f.run(target()))
        f.execute_exploit.assert_called_once()

    def test_already_pwned_does_not_repeat_exploit(self):
        f=self.flow(Mock(return_value=response(pwned='limera1n')));f.execute_exploit=Mock()
        self.assertTrue(f.run(target()))
        f.execute_exploit.assert_not_called()

    def test_ecid_formats(self):
        self.assertEqual(ecid_number('0x7b'), ecid_number('123'))

    def test_no_battery_query(self):
        info=plistlib.dumps({'ProductType':'iPhone3,1','ProductVersion':'5.1.1','ChipID':0x8930})
        run=Mock(return_value=subprocess.CompletedProcess([],0,info,b''))
        state=probe(run,lambda name:'/tool/'+name)
        self.assertTrue(compatible(state))
        self.assertEqual(run.call_count,1)
        self.assertNotIn('battery',state.to_dict())


if __name__=='__main__':unittest.main()
