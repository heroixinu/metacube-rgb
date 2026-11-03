"""Behavioral OEM profile & AC tests, isolated temporary files; no real WMI writes."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from metacube_rgb.core import Device, MetaCubeError, Presets
from metacube_rgb.web import Api, DemoDevice


class PerformanceParityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.power = self.root/'power'
        self.power.mkdir()
        self.wmi = self.root/'wmi'
        self.wmi.mkdir()
        self.flags = self.root/'flags'
        self.flags.mkdir()
        (self.flags/'allow_writes').write_text('Y\n')
        (self.flags/'allow_platform_writes').write_text('Y\n')
        (self.wmi/'oem_system_mode').write_text('1\n')
        self.dev = Device(self.wmi, self.flags, self.power)

    def tearDown(self):
        self.tmp.cleanup()

    def supply(self, name, kind, online):
        root=self.power/name
        root.mkdir()
        (root/'type').write_text(kind+'\n')
        (root/'online').write_text(str(online)+'\n')
        return root

    def test_oem_performance_mode_numbers(self):
        from metacube_rgb.core import PERFORMANCE_MODES
        self.assertEqual(PERFORMANCE_MODES, {'turbo':0,'balanced':1,'quiet':2})

    def test_unknown_ac_fails_closed_without_wmi_write(self):
        state = self.dev.profile_status()
        self.assertIsNone(state['power']['ac_online'])
        self.assertFalse(state['turbo_available'])
        with patch.object(self.dev,'_write') as writer:
            with self.assertRaisesRegex(MetaCubeError,'AC online'):
                self.dev.platform('system_mode',0)
            writer.assert_not_called()

    def test_power_class_battery_is_not_equivalent_to_ac(self):
        self.supply('BAT0','Battery',1)
        self.assertIsNone(self.dev.ac_status()['ac_online'])
        self.supply('ADP1','Mains',0)
        self.assertFalse(self.dev.ac_status()['ac_online'])

    def test_ac_online_explicit_and_mode_readback(self):
        self.supply('ADP1','Mains',1)
        data=self.dev.profile_status()
        self.assertTrue(data['turbo_available'])
        self.assertEqual(data['profile']['value'],1)
        with patch.object(self.dev, '_write', side_effect=lambda attr,val:(self.wmi/attr).write_text(val+'\n')) as writer:
            self.assertEqual(self.dev.platform('system_mode',0)['value'],0)
            writer.assert_called_once_with('oem_system_mode','0')
            self.assertEqual(self.dev.platform('system_mode',2)['value'],2)

    def test_power_off_blocks_turbo_but_quiet_and_balance_allowed(self):
        self.supply('ADP1','Mains',0)
        with patch.object(self.dev,'_write',side_effect=lambda attr,val:(self.wmi/attr).write_text(val+'\n')) as writer:
            with self.assertRaisesRegex(MetaCubeError,'AC online'):
                self.dev.platform('system_mode',0)
            writer.assert_not_called()
            self.assertEqual(self.dev.platform('system_mode',2)['value'],2)
            self.assertEqual(self.dev.platform('system_mode',1)['value'],1)
            self.assertEqual(writer.call_count,2)

    def test_unknown_profile_is_reported_not_assumed(self):
        (self.wmi/'oem_system_mode').unlink()
        result=self.dev.profile_status()
        self.assertTrue(result['profile']['unsupported'])
        self.assertEqual(result['power']['source'],'linux_power_supply')

    def test_api_profile_is_readonly_and_fans_have_no_writer(self):
        api=Api(self.dev,Presets(self.root/'presets.json'))
        with patch.object(self.dev,'_write',side_effect=AssertionError('No SET allowed')):
            status=api.read('/api/profile')
            self.assertEqual(status['available_modes']['quiet'],2)
            self.assertFalse(status['manual_fan_speed_supported'])
            with self.assertRaises(KeyError):
                api.write('/api/fans',{'rpm':5000})
            with self.assertRaises(KeyError):
                api.write('/api/profile',{'mode':'turbo'})

    def test_demo_profile_response_no_real_power_reads(self):
        api=Api(DemoDevice(), Presets(self.root/'demo.json'),demo=True)
        p=api.read('/api/profile')
        self.assertEqual(p['profile']['label'],'balanced')
        self.assertFalse(p['manual_fan_speed_supported'])
        self.assertEqual(p['power']['source'],'demo')

if __name__=='__main__':
    unittest.main()
