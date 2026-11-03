"""Bundled system templates are read-only and isolated from user slots.

No call to real sysfs/WMI is made by these tests.
"""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from metacube_rgb.core import Device, MetaCubeError, Presets
from metacube_rgb.templates import system_templates, system_template, CATALOG
from metacube_rgb.web import Api, DemoDevice


class SystemTemplateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Presets(Path(self.tmp.name)/'user-presets.json')
        self.device=DemoDevice()
        self.api=Api(self.device,self.store,demo=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_original_uploaded_catalog_all_values(self):
        templates=system_templates()
        self.assertEqual([p['name'] for p in templates],
                         ['我的预设 1','落日熔岩','深海幻境','霓虹幻夜'])
        self.assertEqual([len(p['lighting']['colors']) for p in templates], [4,6,6,6])
        self.assertEqual([p['lighting']['speed'] for p in templates],[2]*4)
        self.assertEqual(templates[0]['lighting']['colors'],['0033AA','0088FF','00E5D4','8844FF'])
        self.assertEqual(templates[1]['lighting']['colors'],['FF3300','FF6600','FF9900','FFCC33','FF6688','DD2255'])
        self.assertEqual(templates[2]['lighting']['colors'],['001A66','0033CC','0066FF','00AAFF','00DDBB','007788'])
        self.assertEqual(templates[3]['lighting']['colors'],['5500FF','8833FF','CC22FF','FF22AA','FF4477','9944FF'])
        self.assertTrue(all(p['lighting']['mode']=='spin' for p in templates))
        self.assertIsNone(json.loads(CATALOG.read_text())['slots'][4])

    def test_system_catalog_never_uses_user_slots(self):
        before=self.store.export()
        remote=self.api.read('/api/templates')['templates']
        self.assertEqual(len(remote),4)
        with patch.object(self.device,'lighting',side_effect=AssertionError('Unexpected write')):
            self.api.read('/api/templates')
        self.assertEqual(self.store.export(),before)
        with self.assertRaises(KeyError):
            self.api.write('/api/templates/save',{'id':1,'name':'Oops'})
        self.assertEqual(self.store.export(),before)

    def test_preview_can_read_and_apply_without_mutating_user_presets(self):
        self.store.update(1,self.device.state(),'User original')
        original=self.store.export()
        with patch.dict(os.environ,{'METACUBE_EXPERIMENTAL_RGB':'0',
                                    'METACUBE_ALLOW_SPEED_CUSTOMIZATION':'0'}):
            previous=self.device.state()['raw']
            payload=self.api.write('/api/templates/apply',{'id':2,'expected_raw':previous})
        self.assertEqual(payload['lighting']['colors'],system_template(2)['colors'])
        self.assertEqual(payload['lighting']['mode'],'spin')
        self.assertEqual(payload['lighting']['speed'],2)
        self.assertEqual(self.store.export(),original)
        self.assertTrue(payload['undo_available'])
        self.assertEqual(self.api.write('/api/lighting/undo',{})['lighting']['raw'],previous)

    def test_bad_template_id_is_rejected(self):
        for bad in (0,5,6,'bad',True):
            with self.subTest(bad=bad),self.assertRaises(MetaCubeError):
                system_template(bad)

    def test_custom_speed_blocked_even_when_applying_user_preset(self):
        self.store.update(1,{**self.device.state(), 'speed':250},'unsafe stored preset')
        with patch.dict(os.environ,{'METACUBE_EXPERIMENTAL_RGB':'0',
                                    'METACUBE_ALLOW_SPEED_CUSTOMIZATION':'0'}):
            # Actual policy is in Device.lighting. Use a fake sysfs state to check gate.
            wmi=Path(self.tmp.name)/'wmi';wmi.mkdir()
            param=Path(self.tmp.name)/'param';param.mkdir()
            (wmi/'ambient_raw').write_text(self.device.state()['raw']+'\n')
            (wmi/'ambient_apply').write_text('')
            (param/'allow_writes').write_text('Y\n')
            real=Device(wmi,param)
            api=Api(real,self.store,demo=False)
            with patch.object(real,'_write',side_effect=AssertionError('No WMI write expected')):
                with self.assertRaisesRegex(MetaCubeError,'speed is locked'):
                    api.write('/api/presets/apply',{'slot':1})
