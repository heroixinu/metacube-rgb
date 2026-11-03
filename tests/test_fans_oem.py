"""MetaCube original fan telemetry parity; all fake sysfs; never touches hardware."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from metacube_rgb.core import Device, MetaCubeError, normalize_lighting
from metacube_rgb.web import Api, DemoDevice
from metacube_rgb.core import Presets


class FanReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.base=Path(self.tmp.name)
        self.wmi=self.base/'wmi'
        self.wmi.mkdir()
        self.dev=Device(self.wmi,self.base/'mod')

    def tearDown(self):
        self.tmp.cleanup()

    def test_original_oem_preferred(self):
        (self.wmi/'oem_fan_rpm_oem').write_text('2460 1740\n')
        (self.wmi/'oem_fan_rpm').write_text('2500 1800\n')
        with patch.object(self.dev,'_write',side_effect=AssertionError('No WMI writes')):
            r=self.dev.fans()
        self.assertEqual((r['main_rpm'],r['small_rpm']),(2460,1740))
        self.assertEqual(r['source'],'metacube_oem_0x14')
        self.assertEqual(r['poll_seconds'],2)
        self.assertFalse(r['manual_control'])

    def test_older_driver_falls_back_generic(self):
        (self.wmi/'oem_fan_rpm').write_text('3100 2850\n')
        r=self.dev.fans()
        self.assertEqual(r['source'],'bitland_0x0d_fallback')
        self.assertIn('DKMS 2.2.0',r['note'])
        self.assertEqual(r['main_rpm'],3100)

    def test_ambiguous_oem_response_does_not_masquerade_as_rpm(self):
        (self.wmi/'oem_fan_rpm_oem').write_text('0 1\n')
        (self.wmi/'oem_fan_rpm').write_text('2960 1500\n')
        r=self.dev.fans()
        self.assertEqual(r['source'],'bitland_0x0d_fallback')
        self.assertIn('Invalid/ambiguous',r['note'])

    def test_no_repeat_of_failed_oem_wmi_probe(self):
        (self.wmi/'oem_fan_rpm_oem').write_text('0 1\n')
        (self.wmi/'oem_fan_rpm').write_text('2450 1400\n')
        orig=self.dev._read
        calls=[]
        def tracked(attr):
            calls.append(attr)
            return orig(attr)
        with patch.object(self.dev,'_read',side_effect=tracked):
            self.dev.fans()
            self.dev.fans()
        self.assertEqual(calls.count('oem_fan_rpm_oem'),1)
        self.assertEqual(calls.count('oem_fan_rpm'),2)

    def test_no_fan_reader_reports_unavailable(self):
        r=self.dev.fans()
        self.assertFalse(r['available'])
        self.assertIsNone(r['main_rpm'])
        self.assertEqual(r['source'],'unavailable')

    def test_mock_api_is_readonly(self):
        api=Api(DemoDevice(),Presets(self.base/'presets.json'),demo=True)
        response=api.read('/api/fans')
        self.assertTrue(response['available'])
        self.assertEqual(response['main_rpm'],2380)
        self.assertFalse(response['manual_control'])
        with self.assertRaises(KeyError):
            api.write('/api/fans',{'main_rpm':0})

    def test_prior_legacy_presets_remain_readable_without_rewriting_disk(self):
        store=Presets(self.base/'old-presets.json')
        legacy=normalize_lighting({'mode':'spin','colors':['123456'],'speed':2})
        legacy['speed']=77
        data={'version':1,'slots':[{'name':'legacy', 'lighting':legacy}]+[None]*4}
        store.path.write_text(__import__('json').dumps(data),encoding='utf-8')
        original=store.path.read_bytes()
        self.assertEqual(store.read()[0]['lighting']['speed'],2)
        self.assertEqual(store.path.read_bytes(),original)
        with self.assertRaises(MetaCubeError):
            store.replace(data)

    def test_multiple_browser_fan_requests_are_throttled(self):
        device=DemoDevice()
        api=Api(device,Presets(self.base/'presets2.json'),demo=True)
        with patch.object(device,'fans',wraps=device.fans) as spy:
            self.assertEqual(api.read('/api/fans')['main_rpm'],2380)
            self.assertEqual(api.read('/api/fans')['main_rpm'],2380)
            spy.assert_called_once()

    def test_oem_speed_bounds(self):
        self.assertEqual(normalize_lighting({'speed':0})['speed'],0)
        self.assertEqual(normalize_lighting({'speed':10})['speed'],10)
        for invalid in (-1,11,12,45,255):
            with self.subTest(value=invalid), self.assertRaises(MetaCubeError):
                normalize_lighting({'speed':invalid})

if __name__=='__main__':
    unittest.main()
