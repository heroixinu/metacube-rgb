"""Identity tests: paths are synthetic; no access to physical firmware."""
from pathlib import Path
import tempfile
import unittest

from metacube_rgb.metrics import sensor_info


class SensorIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.hwmon = self.root / 'class/hwmon'
        self.hwmon.mkdir(parents=True)
        self.number = 0

    def add(self, name, device_path, temperature, raw_label=None, model=None, sensor_no=1):
        chip = self.hwmon / f'hwmon{self.number}'
        self.number += 1
        chip.mkdir()
        (chip / 'name').write_text(name)
        (chip / f'temp{sensor_no}_input').write_text(str(round(temperature * 1000)))
        if raw_label:
            (chip / f'temp{sensor_no}_label').write_text(raw_label)
        device = self.root / 'devices' / device_path
        device.mkdir(parents=True, exist_ok=True)
        if model:
            (device / 'model').write_text(model)
        (chip / 'device').symlink_to(device, target_is_directory=True)

    def test_all_m11_hpt_sensor_sources(self):
        self.add('k10temp', 'pci0000:00/0000:00:18.3', 47.5, 'Tctl')
        self.add('amdgpu', 'pci0000:00/0000:c5:00.0', 43, 'edge')
        self.add('acpitz', 'virtual/thermal/thermal_zone0', 47)
        self.add('spd5118', 'pci0000:00/0000:00:14.0/i2c-0/0-0050', 45)
        self.add('spd5118', 'pci0000:00/0000:00:14.0/i2c-0/0-0051', 46)
        self.add('nvme', 'pci0000:00/0000:02:00.0/nvme/nvme0', 44.8, 'Composite', 'KIOXIA NVMe SSD')
        self.add('nvme', 'pci0000:00/0000:06:00.0/nvme/nvme1', 48.8, 'Composite', 'Solidigm P44 Pro')
        self.add('nvme', 'pci0000:00/0000:06:00.0/nvme/nvme1', 42.8, 'Sensor 1', 'Solidigm P44 Pro', 2)
        self.add('nvme', 'pci0000:00/0000:06:00.0/nvme/nvme1', 45.8, 'Sensor 2', 'Solidigm P44 Pro', 3)
        self.add('r8169_0_300:00', 'pci0000:00/0000:03:00.0/mdio_bus/r8169-0-300/r8169-0-300:00', 50.5)
        self.add('r8169_0_500:00', 'pci0000:00/0000:05:00.0/mdio_bus/r8169-0-500/r8169-0-500:00', 49.5)
        temps, fans = sensor_info(self.hwmon)
        self.assertEqual(len(temps), 11)
        self.assertEqual(fans, [])
        labels = [x['label'] for x in temps]
        for expected in ('CPU 控制温度', '核显边缘温度', '平台热区温度',
                         '内存温度 · 0x50', '内存温度 · 0x51',
                         'KIOXIA 硬盘温度', 'Solidigm 硬盘温度',
                         'Solidigm 内部温度 1', 'Solidigm 内部温度 2',
                         '有线网卡温度 · 03:00.0', '有线网卡温度 · 05:00.0'):
            self.assertIn(expected, labels)
        p44 = [x for x in temps if x['pci'] == '06:00.0']
        self.assertEqual(len(p44), 3)
        self.assertTrue(all('P44 Pro' in x['detail'] for x in p44))
        self.assertTrue(all(x['category'] == 'storage' for x in p44))
        self.assertTrue(all('主控' not in x['label'] and '闪存' not in x['label'] for x in p44))
        self.assertTrue(all('物理插槽未确认' in x['detail'] for x in temps if x['category'] == 'memory'))
        self.assertEqual({x['category'] for x in temps}, {'core', 'memory', 'storage', 'network'})

    def test_unknown_sensor_keeps_origin_without_guess(self):
        self.add('mysterychip', 'virtual/unknown', 51.2)
        temps, _ = sensor_info(self.hwmon)
        self.assertEqual(temps[0]['label'], '其他硬件温度')
        self.assertIn('mysterychip', temps[0]['detail'])
        self.assertEqual(temps[0]['confidence'], 'unclassified')


if __name__ == '__main__':
    unittest.main()
