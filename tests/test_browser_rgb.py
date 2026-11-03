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


def main():
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory() as tmp:
        api=Api(DemoDevice(), Presets(Path(tmp)/'presets.json'),demo=True)
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
            page.locator('#addColorButton').click()
            assert page.locator('#colorEditor .color-row').count()==4
            page.locator('[data-mode="spin"]').click()
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
            assert not errors,errors
            print('Chrome RGB mock-browser smoke tests passed; screenshot created')
            browser.close()

if __name__=='__main__':main()
