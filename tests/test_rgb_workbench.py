"""Visual + workflow regression for the RGB workbench using only mock API/WMI.

Python tests and all browser operations are safe to run off-device.
"""
from pathlib import Path
import tempfile
from playwright.sync_api import sync_playwright
from test_console_dashboard import SimDevice, SimMetrics, run_view
from metacube_rgb.web import Api
from metacube_rgb.core import Presets

SIZES = [(1920,1080),(1727,863),(1672,941),(1440,900),(1366,768),(1280,720)]

def main():
    with tempfile.TemporaryDirectory() as folder,sync_playwright() as pw:
        dev=SimDevice()
        api=Api(dev,Presets(Path(folder)/'presets.json'),SimMetrics(),demo=True)
        browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage','--no-proxy-server'])
        page=browser.new_page(viewport={'width':1727,'height':863},device_scale_factor=1)
        errors,_=run_view(page,api)
        page.locator('[data-view="lighting"]').click()
        page.locator('#systemTemplateList .system-template-item').first.wait_for()
        assert page.locator('[data-lighting-presets]').count()==2
        assert page.locator('#lighting-preset-user').is_hidden()
        assert page.locator('#lighting-preset-system').is_visible()
        assert page.locator('#view-lighting .mode-tile').count()==4
        assert page.locator('#speedInput').is_enabled()
        assert page.locator('#view-lighting .color-row').count()==4
        assert dev.writes==0
        for width,height in SIZES:
            page.set_viewport_size({'width':width,'height':height})
            page.wait_for_timeout(65)
            layout=page.evaluate('''() => {
                const box=s=>{const r=document.querySelector(s).getBoundingClientRect();return {top:r.top,bottom:r.bottom,left:r.left,right:r.right,w:r.width,h:r.height}};
                const preview=box('.workbench-preview'),stage=box('#previewStage'),apply=box('#applyLightingButton'),
                      palette=box('.workbench-palette'),hub=box('.preset-hub-card'),grid=box('.light-workbench-grid');
                return {vh:innerHeight,scrollY:document.documentElement.scrollHeight-document.documentElement.clientHeight,
                    scrollX:document.documentElement.scrollWidth-document.documentElement.clientWidth,
                    preview,stage,apply,palette,hub,grid};
            }''')
            assert layout['scrollY']<=1,(width,height,'page scroll',layout)
            assert layout['scrollX']<=1,(width,height,'horizontal scroll',layout)
            assert layout['apply']['bottom'] <= layout['preview']['bottom'] - 2,(width,height,'Apply clipped',layout)
            assert layout['apply']['top'] >= layout['preview']['top'],(width,height,'Apply displaced',layout)
            assert layout['apply']['w']>=80,(width,height,'Apply too small',layout)
            assert layout['palette']['bottom']<=height+1,(width,height,'palette overflow',layout)
            assert layout['hub']['bottom']<=height+1,(width,height,'hub overflow',layout)
            assert layout['stage']['h']>=130,(width,height,'ring preview too short',layout)
            if width==1727 and height==863:
                page.evaluate("document.querySelector('#toast').classList.remove('visible')")
                page.screenshot(path='/mnt/data/metacube-rgb-v243-lighting-desktop.png',full_page=True)
            if width==1280 and height==720:
                page.evaluate("document.querySelector('#toast').classList.remove('visible')")
                page.screenshot(path='/mnt/data/metacube-rgb-v243-lighting-compact.png',full_page=True)
        page.set_viewport_size({'width':1727,'height':863})
        # Preview is an editing draft; switching preset tabs never modifies firmware.
        page.locator('[data-lighting-presets="user"]').click()
        assert page.locator('#lighting-preset-user').is_visible()
        assert page.locator('#lighting-preset-system').is_hidden()
        assert page.locator('#presetList .preset-item').count()==5
        assert page.locator('#systemTemplateList .system-template-item').count()==4
        page.locator('[data-lighting-presets="system"]').click()
        assert page.locator('#lighting-preset-system').is_visible()
        page.locator('#colorEditor details').first.click()
        assert page.locator('#colorEditor details').first.get_attribute('open') is not None
        assert page.locator('#colorEditor input[type=number]').count()>=6
        page.locator('#colorEditor input[type=text]').first.fill('55AAFF')
        page.locator('#colorEditor input[type=text]').first.press('Tab')
        assert page.locator('#previewSummaryCount').inner_text()=='4 色'
        assert page.locator('#applyLightingButton').is_enabled()
        assert dev.writes==0,'Editing must never write firmware without explicit Apply'
        # Speed slider updates only the draft; first firmware apply needs confirmation.
        page.locator('#speedInput').evaluate("el => {el.value='3';el.dispatchEvent(new Event('input',{bubbles:true}));}")
        assert dev.writes==0
        assert page.locator('#previewSummarySpeed').inner_text()=='3 / 10'
        page.once('dialog',lambda d:d.dismiss())
        page.locator('#applyLightingButton').click()
        assert dev.writes==0, 'Declining first-use warning must abort WMI write'
        page.once('dialog',lambda d:d.accept())
        page.locator('#applyLightingButton').click()
        page.wait_for_timeout(125)
        assert dev.writes==1, 'Accepting first-use warning must apply exactly once'
        page.locator('#inspectPacketButton').click()
        assert page.locator('#packetCard').is_visible()
        assert page.evaluate('document.documentElement.scrollHeight-document.documentElement.clientHeight')<=1
        assert not errors,errors
        browser.close()
        print('RGB workbench: six desktop sizes, preview Apply, palette edit, preset tabs, WMI inspector, no firmware write OK')

if __name__=='__main__':main()
