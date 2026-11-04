"""Demo-only browser check of source-aware sensor labels; no WMI writes."""
from pathlib import Path
import tempfile
from playwright.sync_api import sync_playwright
from test_console_dashboard import SimDevice, SimMetrics, run_view
from metacube_rgb.web import Api
from metacube_rgb.core import Presets

class LabeledMetrics(SimMetrics):
    def snapshot(self):
        data=super().snapshot()
        data['temperatures']=[
            {'name':'Tctl','label':'CPU 控制温度','detail':'AMD k10temp · Tctl · PCI 00:18.3','source':'k10temp','category':'core','sensor_key':'temp1','celsius':47.5},
            {'name':'edge','label':'核显边缘温度','detail':'AMD amdgpu · edge · PCI c5:00.0','source':'amdgpu','category':'core','sensor_key':'temp1','celsius':43.0},
            {'name':'temp1','label':'平台热区温度','detail':'ACPI 热区 · 非独立主板测温点','source':'acpitz','category':'core','sensor_key':'temp1','celsius':47.0},
            {'name':'temp1','label':'内存温度 · 0x50','detail':'DDR5 SPD Hub · SMBus 0-0050 · 物理插槽未确认','source':'spd5118','category':'memory','sensor_key':'temp1','celsius':45.0},
            {'name':'temp1','label':'内存温度 · 0x51','detail':'DDR5 SPD Hub · SMBus 0-0051 · 物理插槽未确认','source':'spd5118','category':'memory','sensor_key':'temp1','celsius':46.0},
            {'name':'Composite','label':'KIOXIA 硬盘温度','detail':'KIOXIA NVMe SSD · NVMe 复合温度 · PCI 02:00.0','source':'nvme','category':'storage','sensor_key':'temp1','celsius':44.8},
            {'name':'Composite','label':'Solidigm 硬盘温度','detail':'Solidigm P44 Pro · NVMe 复合温度 · PCI 06:00.0','source':'nvme','category':'storage','sensor_key':'temp1','celsius':48.8},
            {'name':'Sensor 1','label':'Solidigm 内部温度 1','detail':'Solidigm P44 Pro · NVMe Sensor 1 · PCI 06:00.0','source':'nvme','category':'storage','sensor_key':'temp2','celsius':42.8},
            {'name':'Sensor 2','label':'Solidigm 内部温度 2','detail':'Solidigm P44 Pro · NVMe Sensor 2 · PCI 06:00.0','source':'nvme','category':'storage','sensor_key':'temp3','celsius':45.8},
            {'name':'temp1','label':'有线网卡温度 · 03:00.0','detail':'Realtek 网卡 PHY · PCI 03:00.0','source':'r8169_0_300:00','category':'network','sensor_key':'temp1','celsius':50.5},
            {'name':'temp1','label':'有线网卡温度 · 05:00.0','detail':'Realtek 网卡 PHY · PCI 05:00.0','source':'r8169_0_500:00','category':'network','sensor_key':'temp1','celsius':49.5},
        ]
        return data

def main():
    with tempfile.TemporaryDirectory() as temp, sync_playwright() as p:
        device=SimDevice();api=Api(device,Presets(Path(temp)/'presets.json'),LabeledMetrics(),demo=True)
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage','--no-proxy-server'])
        page=browser.new_page(viewport={'width':1727,'height':863},device_scale_factor=1)
        errors,logs=run_view(page,api)
        page.locator('[data-view="system"]').click()
        page.locator('#sensorList .sensor').first.wait_for()
        labels=page.locator('#sensorList .sensor-label').all_inner_texts()
        assert len(labels)==11,labels
        assert 'CPU 控制温度' in labels and '核显边缘温度' in labels
        assert 'Solidigm 内部温度 2' in labels and '有线网卡温度 · 03:00.0' in labels
        assert page.locator('#sensorList .sensor-group-title').all_inner_texts()==['核心与平台','内存、硬盘与网络设备']
        assert '原厂 WMI' in page.locator('#fanSourceNote').inner_text()
        for title in ['OEM FAN TELEMETRY','PERFORMANCE PROFILE','BUTTON BACKLIGHT','PVE HOST','HARDWARE SENSOR']:
            assert title not in page.locator('#view-system').inner_text(),title
        dimensions=page.evaluate('''() => {
            let view=document.querySelector('#view-system').getBoundingClientRect();
            let list=document.querySelector('#sensorList').getBoundingClientRect();
            return {scroll:document.documentElement.scrollHeight-document.documentElement.clientHeight,
                    viewBottom:view.bottom, listBottom:list.bottom, height:window.innerHeight};
        }''')
        assert dimensions['scroll']<=1,dimensions
        assert dimensions['viewBottom']<=dimensions['height']+1,dimensions
        assert dimensions['listBottom']<=dimensions['height']+1,dimensions
        assert not errors,(errors,logs)
        page.evaluate("document.querySelector('#toast').classList.remove('visible')")
        page.screenshot(path='/mnt/data/metacube-v245-system-desktop.png',full_page=True)
        print('Sensor browser verification OK:',dimensions)
        browser.close()

if __name__=='__main__': main()
