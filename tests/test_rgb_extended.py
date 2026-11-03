"""Protocol, preset, concurrency and undo tests. Never talks to real firmware."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from metacube_rgb.core import (MetaCubeError, MetaCubeConflict, Presets,
                               build_ambient_set_packet, normalize_lighting)
from metacube_rgb.web import Api, DemoDevice

CURRENT = '0080000f020150dcfa00000030ff00ffbb002266ff000000a002000000000000'

class FirmwarePacketTests(unittest.TestCase):
    def test_oem_32_byte_layout_six_colors_and_reserved_bytes(self):
        original=bytearray.fromhex(CURRENT)
        original[29:32]=bytes.fromhex('ab12cd')
        lighting=normalize_lighting({'mode':'spin','colors':['FF0000','00FF00','0000FF','FFFFFF','FEDCBA','123456'],
                                     'brightness':173,'speed':61,'direction':1,'cycle':11,'transition':1})
        frame=bytes.fromhex(build_ambient_set_packet(original.hex(),lighting))
        self.assertEqual(len(frame),32)
        self.assertEqual(frame[0:4].hex(),'00fb000f')
        self.assertEqual(frame[4],4)
        self.assertEqual(frame[5],6)
        self.assertEqual(frame[6:24].hex(),'ff000000ff000000fffffffffedcba123456')
        self.assertEqual(list(frame[24:29]),[173,61,1,11,1])
        self.assertEqual(frame[29:32].hex(),'ab12cd')

    def test_single_color_zeroes_unused_slots(self):
        state=normalize_lighting({'colors':['A0B1C2'],'mode':'steady'})
        packet=bytes.fromhex(build_ambient_set_packet(CURRENT,state))
        self.assertEqual(packet[5],1)
        self.assertEqual(packet[6:9].hex(),'a0b1c2')
        self.assertEqual(packet[9:24],bytes(15))

    def test_invalid_wmi_header_cannot_plan(self):
        with self.assertRaises(MetaCubeError):
            build_ambient_set_packet('00'*32,normalize_lighting({'mode':'off'}))

class RGBWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.device=DemoDevice()
        self.presets=Presets(Path(self.tmp.name)/'presets.json')
        self.api=Api(self.device,self.presets,demo=True)
    def tearDown(self):self.tmp.cleanup()

    def test_plan_makes_zero_writes_and_matches_oem_protocol(self):
        current=self.device.state()
        with patch.object(self.device,'lighting',side_effect=AssertionError('No hardware writes!')):
            p=self.api.write('/api/lighting/plan',{'expected_raw':current['raw'],
                           'mode':'spin','colors':['FF0000','00FF00'],'speed':220,'direction':1})
        self.assertEqual(len(p['set_packet']),64)
        self.assertEqual(p['set_packet'][:8],'00fb000f')
        self.assertEqual(p['changes']['mode']['to'],'spin')
        self.assertEqual(self.device.state(),current)

    def test_optimistic_concurrency_and_one_step_undo(self):
        original=self.device.state()
        changed=self.api.write('/api/lighting',{'expected_raw':original['raw'],
                          'mode':'spin','colors':['FF0000','00FF00'],'speed':133})
        self.assertEqual(changed['lighting']['mode'],'spin')
        self.assertTrue(changed['undo_available'])
        with self.assertRaises(MetaCubeConflict):
            self.api.write('/api/lighting',{'expected_raw':original['raw'],'brightness':77})
        undone=self.api.write('/api/lighting/undo',{})
        self.assertEqual(undone['lighting']['raw'],original['raw'])
        self.assertFalse(undone['undo_available'])
        with self.assertRaises(MetaCubeError):
            self.api.write('/api/lighting/undo',{})

    def test_undo_blocked_if_changed_outside_web(self):
        original=self.device.state()
        self.api.write('/api/lighting',{'brightness':128,'expected_raw':original['raw']})
        self.device.lighting({'brightness':17})
        with self.assertRaises(MetaCubeConflict):
            self.api.write('/api/lighting/undo',{})
        self.assertEqual(self.device.state()['brightness'],17)

    def test_save_draft_and_import_do_not_call_firmware_write(self):
        original=self.device.state()
        draft=normalize_lighting({'colors':['123456','abcdef'],'mode':'spin','cycle':11})
        with patch.object(self.device,'lighting',side_effect=AssertionError('No hardware writes!')):
            saved=self.api.write('/api/presets/save',{'slot':1,'name':'RGB Demo','lighting':draft})
            self.assertEqual(saved['slots'][0]['lighting']['colors'],['123456','ABCDEF'])
            document=self.api.read('/api/presets/export')
            assert document['version']==1
            imported=self.api.write('/api/presets/import',document)
            self.assertEqual(imported['slots'][0]['name'],'RGB Demo')
        self.assertEqual(self.device.state(),original)
        self.assertEqual(self.presets.path.stat().st_mode & 0o777,0o600)

    def test_reject_import_invalid_slots_no_data_loss(self):
        self.presets.update(1,self.device.state(),'Original')
        before=self.presets.path.read_bytes()
        payload=self.presets.export()
        for bad in (
            {'version':2,'slots':payload['slots']},
            {'version':1,'slots':[]},
            {'version':1,'slots':[{'name':'x','lighting':{}}]+[None]*4},
            {'version':1,'slots':[{'name':'evil\n','lighting':normalize_lighting({})}]+[None]*4},
            {'version':1,'slots':[{'name':'hack','lighting':{**normalize_lighting({}), 'unknown':1}}]+[None]*4},
        ):
            with self.subTest(bad=bad),self.assertRaises(MetaCubeError):
                self.api.write('/api/presets/import',bad)
            self.assertEqual(self.presets.path.read_bytes(),before)

if __name__=='__main__':unittest.main()
