"""Optional Chromium smoke test with an in-process API mock; zero real firmware access.
Run: python3 tests/test_browser_rgb.py
"""
from pathlib import Path
import json
import sys
import tempfile
from urllib.parse import urlsplit

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from metacube_rgb.core import Presets, MetaCubeError
from metacube_rgb.web import Api, DemoDevice

ROOT=Path(__file__).resolve().parents[1]
TOKEN='q'*48


class OpenSpeedDemo(DemoDevice):
    """Mirror the default OEM-range UI with only simulated backend calls."""
    def __init__(self):
        super().__init__()
        self._current['speed']=2

    def state(self):
        state=super().state()
        state['speed_customization_enabled']=True
        state['rgb_experimental_enabled']=True
        return state


def main():
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory() as tmp:
        api=Api(OpenSpeedDemo(), Presets(Path(tmp)/'presets.json'),demo=True)
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage','--no-proxy-server'])
            page=browser.new_page(viewport={'width':1380,'height':950},device_scale_factor=1)
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            def mock_api(path,method,payload):
                try:
                    result=api.read(path) if method=='GET' else api.write(path,payload)
                    return {'status':200,'body':result}
                except (MetaCubeError,KeyError) as exc:
                    return {'status':400,'body':{'error':str(exc)}}
            page.goto('about:blank')
            page.expose_function('mockPythonApi',mock_api)
            html=(ROOT/'web/index.html').read_text(encoding='utf-8')
            html=html.replace('<script defer src="/app.js"></script>','')
            page.set_content(html,wait_until='domcontentloaded')
            page.add_style_tag(content=(ROOT/'web/styles.css').read_text(encoding='utf-8'))
            page.evaluate('''() => {
              const d = {};
              Object.defineProperty(window,'sessionStorage',{configurable:true,value:{
                getItem(key){return d[key]||null;},setItem(key,value){d[key]=String(value);}
              }});
              window.fetch = async (path,options={}) => {
                const p = JSON.parse(options.body||'{}');
                const result=await window.mockPythonApi(path,options.method||'GET',p);
                return {ok:result.status>=200&&result.status<300,status:result.status,
                        json:async()=>result.body};
              };
            }''')
            page.add_script_tag(content=(ROOT/'web/app.js').read_text(encoding='utf-8'))
            page.locator('#tokenInput').fill(TOKEN)
            page.locator('#loginForm button[type=submit]').click()
            page.get_by_text('成功连接至 MetaCube').wait_for(timeout=3000) if False else None
            page.wait_for_timeout(250)
            page.locator('[data-view="lighting"]').click()
            page.locator('#systemTemplateList .system-template-item').first.wait_for(timeout=3000)
            assert page.locator('#systemTemplateList .system-template-item').count()==4
            assert page.locator('#speedInput').is_enabled(), 'OEM speed 0..10 must be open by default'
            assert page.locator('#view-lighting button.mode-tile[data-mode="spin"]').is_enabled(), 'Spin mode must remain enabled'
            assert page.locator('#addColorButton').is_enabled(), 'Multicolor must remain available'
            assert 'conic-gradient' in page.locator('#previewRing').evaluate('(el) => el.style.getPropertyValue("--ring-palette")')
            # Loading a built-in theme must not consume or overwrite any user slots.
            first=page.locator('#systemTemplateList .system-template-item').first
            first.get_by_text('载入编辑器').click()
            assert page.locator('#colorEditor .color-row').count()==4
            assert page.locator('#view-lighting button.mode-tile[data-mode="spin"]').get_attribute('class').find('active')>=0
            assert page.locator('#systemTemplateList .system-template-item').count()==4
            # The rest of the test uses a fresh 3-color draft.
            page.once('dialog',lambda dialog:dialog.accept())
            page.locator('#discardDraftButton').click()
            page.locator('#addColorButton').click()
            assert page.locator('#colorEditor .color-row').count()==4
            page.locator('#view-lighting button.mode-tile[data-mode="spin"]').click()
            page.locator('#nextCycleButton').click()
            page.locator('#colorEditor details').first.click()
            assert page.locator('#colorEditor input[type=number]').count()>=6
            page.locator('#colorEditor input[type=number]').first.fill('200')
            page.locator('#colorEditor input[type=number]').first.press('Tab')
            page.locator('#inspectPacketButton').click()
            page.get_by_text('WMI SET / 32 字节 / 仅预检').wait_for(timeout=3000)
            page.screenshot(path=str(Path(tempfile.gettempdir())/'metacube-rgb-lighting-qa.png'),full_page=True)
            page.locator('#applyLightingButton').click()
            page.wait_for_timeout(250)
            assert page.locator('#heroMode').inner_text()=='旋转',page.locator('#heroMode').inner_text()
            page.once('dialog',lambda dialog:dialog.accept())
            page.locator('#undoLightingButton').click()
            # need click after dialog handler registration, otherwise confirm may remain
            page.wait_for_timeout(100)
            # The system information must render even when optional GPU/net
            # gauge cards do not exist in the dashboard template.
            page.locator('[data-view="system"]').click()
            page.locator('#systemInfo .info-item').first.wait_for(timeout=4000)
            assert page.locator('#systemInfo .info-item').count() >= 6
            page.locator('[data-view="system"]').click()
            page.locator('#mainFanRpm').get_by_text('2380').wait_for(timeout=5000)
            assert page.locator('#smallFanRpm').inner_text()=='1740'
            assert page.locator('#speedInput').get_attribute('max')=='10'
            assert page.locator('#brightnessInput').get_attribute('max')=='10'
            assert page.locator('#acPowerStatus').inner_text().find('在线')>=0
            assert page.locator('#profileCurrent').inner_text().find('均衡')>=0
            assert page.locator('#view-system [data-profile="0"]').is_disabled() # OEM profile writes disabled in demo
            assert page.locator('#mainFanSpark').count()==1
            assert page.locator('#smallFanSpark').count()==1
            page.locator('[data-view="lighting"]').click()
            # Pixel-accurate OEM 0..10 brightness conversion while editing in memory.
            page.locator('#brightnessInput').fill('10')
            page.locator('#brightnessInput').dispatch_event('input')
            assert '255/255' in page.locator('#brightnessValue').inner_text()
            page.locator('#brightnessInput').fill('0')
            page.locator('#brightnessInput').dispatch_event('input')
            assert '0/255' in page.locator('#brightnessValue').inner_text()
            assert not errors,errors
            print('Chrome RGB mock-browser smoke tests passed; screenshot created')
            browser.close()

if __name__=='__main__':main()
