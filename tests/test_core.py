import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from metacube_rgb.core import Device, MetaCubeError, Presets, normalize_lighting, read_boot_config, save_boot_config
from metacube_rgb.web import DemoDevice, Api, token_from_file

CURRENT_RAW='0080000f020150dcfa00000030ff00ffbb002266ff000000a002000000000000'

class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.wmi=self.root/'wmi';self.wmi.mkdir()
        self.params=self.root/'params';self.params.mkdir()
        (self.wmi/'ambient_raw').write_text(CURRENT_RAW+'\n')
        (self.params/'allow_writes').write_text('Y\n')
        (self.params/'allow_platform_writes').write_text('N\n')
        self.device=Device(self.wmi,self.params)

    def tearDown(self):self.temp.cleanup()

    def test_original_hardware_response(self):
        state=self.device.state()
        self.assertEqual(state['mode'],'breath')
        self.assertEqual(state['colors'],['50DCFA'])
        self.assertEqual(state['brightness'],160)
        self.assertEqual(state['speed'],2)
        self.assertTrue(state['writable'])

    def test_validate_multicolor_range(self):
        target=normalize_lighting({'colors':['FF0000','00FF00','0000FF'], 'mode':'spin',
                                   'direction':1,'cycle':11,'transition':1, 'speed':240})
        self.assertEqual(target['colors'],['FF0000','00FF00','0000FF'])
        self.assertEqual(target['cycle'],11)
        for payload in ({'colors':[]},{'colors':['FF0000']*7},
                        {'colors':['nothex']},{'mode':'x'},
                        {'direction':2},{'brightness':256},{'cycle':-1},
                        {'unknown':1},{'brightness':True}):
            with self.subTest(payload=payload),self.assertRaises(MetaCubeError):
                normalize_lighting(payload)

    def test_readonly_enforced(self):
        (self.params/'allow_writes').write_text('N')
        with self.assertRaisesRegex(MetaCubeError,'read-only'):
            self.device.lighting({'brightness':10})

    def test_extended_write_packet_and_get_verification(self):
        # Emulate only the sysfs effect of the kernel driver; never call WMI.
        (self.wmi/'ambient_apply').write_text('')
        calls=[]
        def fake_write(attr, value):
            calls.append((attr,value))
            self.assertEqual(attr,'ambient_apply')
            fields=value.split(' ')
            self.assertEqual(len(fields),7)
            data=bytearray.fromhex((self.wmi/'ambient_raw').read_text().strip())
            nums=[int(n) for n in fields[:6]]
            colors=fields[6].split(',')
            data[4]=nums[0]
            data[5]=len(colors)
            data[6:24]=bytes.fromhex(''.join(colors)).ljust(18,b'\0')
            data[24:29]=bytes(nums[1:6])
            (self.wmi/'ambient_raw').write_text(data.hex()+'\n')
        with patch.dict(os.environ, {'METACUBE_EXPERIMENTAL_RGB':'1'}), \
             patch.object(self.device,'_write',side_effect=fake_write):
            result=self.device.lighting({'mode':'spin', 'colors':['FF0000','00FF00'],
                                         'brightness':175,'speed':70,'direction':1,
                                         'cycle':7,'transition':1})
        self.assertEqual(len(calls),1,'Advanced control must issue one atomic SET')
        self.assertEqual(calls[0][1],'4 175 70 1 7 1 FF0000,00FF00')
        self.assertEqual(result['colors'],['FF0000','00FF00'])
        self.assertEqual(result['brightness'],175)
        self.assertEqual(result['direction'],1)

    def test_extended_readback_mismatch_reports_error(self):
        (self.wmi/'ambient_apply').write_text('')
        with patch.object(self.device,'_write',return_value=None) as writer:
            with self.assertRaisesRegex(MetaCubeError,'readback mismatch'):
                self.device.lighting({'brightness':200})
            writer.assert_called_once()

    def test_advanced_effects_blocked_before_sysfs_write(self):
        (self.wmi/'ambient_apply').write_text('')
        with patch.dict(os.environ, {'METACUBE_EXPERIMENTAL_RGB':'0'}), \
             patch.object(self.device,'_write') as writer:
            for change in ({'mode':'spin'}, {'speed':20}, {'direction':1},
                           {'cycle':1}, {'transition':1},
                           {'colors':['FF0000','00FF00']}):
                with self.subTest(change=change), self.assertRaisesRegex(MetaCubeError,'Experimental RGB effect blocked'):
                    self.device.lighting(change)
            writer.assert_not_called()

    def test_verified_breath_brightness_remains_allowed(self):
        (self.wmi/'ambient_apply').write_text('')
        def emulate(attr,value):
            data=bytearray.fromhex((self.wmi/'ambient_raw').read_text().strip())
            parts=value.split()
            data[4]=int(parts[0]);data[24]=int(parts[1])
            data[25:29]=bytes(map(int,parts[2:6]))
            colors=parts[6].split(',')
            data[5]=len(colors)
            data[6:24]=bytes.fromhex(''.join(colors)).ljust(18,b'\x00')
            (self.wmi/'ambient_raw').write_text(data.hex())
        with patch.dict(os.environ, {'METACUBE_EXPERIMENTAL_RGB':'0'}), \
             patch.object(self.device,'_write',side_effect=emulate) as writer:
            result=self.device.lighting({'mode':'steady','colors':['FF0000'],'brightness':255,
                                         'speed':2,'direction':0,'cycle':0,'transition':0})
        self.assertEqual(result['mode'],'steady')
        self.assertEqual(result['brightness'],255)
        writer.assert_called_once()

    def test_oem_keyboard_rgb_probe_suppressed(self):
        with patch.dict(os.environ, {'METACUBE_EXPERIMENTAL_OEM_READS':'0'}), \
             patch.object(self.device,'_read',side_effect=AssertionError('Forbidden WMI probe')):
            results=self.device.read_oem(['keyboard_mode','keyboard_brightness'])
        self.assertTrue(results['keyboard_mode']['unsupported'])
        self.assertTrue(results['keyboard_brightness']['unsupported'])
        self.assertIn('disabled',results['keyboard_mode']['reason'])

    def test_web_real_device_guards_advanced_effects(self):
        api=Api(self.device,Presets(self.root/'presets-real.json'),demo=False)
        state=api.read('/api/status')['lighting']
        self.assertFalse(state['rgb_experimental_enabled'])
        with patch.dict(os.environ, {'METACUBE_EXPERIMENTAL_RGB':'0'}):
            plan=api.write('/api/lighting/plan',{'mode':'spin','speed':55})
            self.assertFalse(plan['can_apply'])
            self.assertGreater(len(plan['experimental_reasons']),0)
            with self.assertRaisesRegex(MetaCubeError,'Experimental RGB effect blocked'):
                api.write('/api/lighting',{'mode':'spin','speed':55})

    def test_oem_platform_requires_two_flags(self):
        (self.wmi/'oem_button_brightness').write_text('2\n')
        (self.params/'allow_platform_writes').write_text('Y\n')
        with patch.object(self.device,'_write',return_value=None) as writer:
            self.assertEqual(self.device.platform('button_brightness',2)['value'],2)
            writer.assert_called_once_with('oem_button_brightness','2')
        with patch.object(self.device,'_write',return_value=None):
            with self.assertRaisesRegex(MetaCubeError,'readback mismatch'):
                self.device.platform('button_brightness',3)

    def test_extended_requires_v2(self):
        with patch.dict(os.environ, {'METACUBE_EXPERIMENTAL_RGB':'1'}):
            with self.assertRaisesRegex(MetaCubeError,'require the v2'):
                self.device.lighting({'colors':['FF0000','00FF00']})

    def test_oem_restrictions(self):
        with self.assertRaisesRegex(MetaCubeError,'locked'):
            self.device.platform('system_mode',1)
        with self.assertRaises(MetaCubeError):
            self.device.platform('gpu_mode',1)

    def test_atomic_presets(self):
        p=Presets(self.root/'presets.json')
        self.assertEqual(len(p.read()),5)
        saved=p.update(1,self.device.state(),'Blue')
        self.assertEqual(saved[0]['name'],'Blue')
        self.assertEqual(p.get(1)['colors'],['50DCFA'])
        self.assertEqual((self.root/'presets.json').stat().st_mode&0o777,0o600)
        p.update(1,None)
        self.assertIsNone(p.read()[0])

    def test_boot_compat(self):
        target=self.root/'boot.conf'
        with patch('os.geteuid',return_value=0):
            save_boot_config(self.device,target)
        self.assertEqual(read_boot_config(target)['brightness'],160)
        old=self.root/'old.conf'
        old.write_text('[lighting]\nmode = breath\ncolor = 50DCFA\nbrightness = 160\n')
        self.assertEqual(read_boot_config(old)['colors'],['50DCFA'])

    def test_demo_api(self):
        api=Api(DemoDevice(),Presets(self.root/'presets.json'),demo=True)
        self.assertEqual(api.read('/api/status')['lighting']['mode'],'breath')
        changed=api.write('/api/lighting',{'mode':'spin','colors':['FF0000','0000FF']})
        self.assertEqual(changed['lighting']['mode'],'spin')
        self.assertEqual(changed['lighting']['color_count'],2)
        api.write('/api/presets/save',{'slot':2,'name':'Spin'})
        api.write('/api/lighting',{'mode':'off'})
        applied=api.write('/api/presets/apply',{'slot':2})
        self.assertEqual(applied['lighting']['mode'],'spin')
        self.assertTrue(api.read('/api/oem-basic')['functions']['system_mode']['unsupported'])

    def test_token_security(self):
        path=self.root/'token'
        token=token_from_file(path)
        self.assertEqual(len(token_from_file(path)),len(token))
        self.assertEqual(path.stat().st_mode & 0o777,0o600)
        path.chmod(0o644)
        with self.assertRaisesRegex(MetaCubeError,'private'):
            token_from_file(path)

if __name__=='__main__':unittest.main()
