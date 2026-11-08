"""Chromium-only regression for original Windows Turbo NeverTips preference.

Everything runs with an in-process fake WMI API; no hardware writes.
Run: python3 tests/test_turbo_prompt.py
"""
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_console_dashboard import SimDevice, SimMetrics
from metacube_rgb.web import Api
from metacube_rgb.core import Presets, MetaCubeError

ROOT = Path(__file__).resolve().parents[1]

class TurboDemo(SimDevice):
    def __init__(self):
        super().__init__()
        self.current_profile = 1
        self.ac_online = True
        self.platform_changes = []

    def profile_status(self):
        return {'profile': {'value': self.current_profile, 'label': {0:'turbo',1:'balanced',2:'quiet'}[self.current_profile]},
                'power': {'ac_online': self.ac_online, 'source': 'mock'},
                'write_enabled': True, 'available_modes': {'turbo':0,'balanced':1,'quiet':2},
                'turbo_available': self.ac_online, 'manual_fan_speed_supported': False}

    def state(self):
        state = super().state()
        state['platform_writable'] = True
        return state

    def platform(self, control, value):
        if control != 'system_mode' or value not in (0,1,2):
            raise MetaCubeError('Unsupported mock mode')
        if value == 0 and not self.ac_online:
            raise MetaCubeError('AC required')
        self.platform_changes.append(value)
        self.current_profile = value
        return {'value': value}

    def read_oem(self, selected=None):
        return {'system_mode': {'value': self.current_profile, 'label': {0:'turbo',1:'balanced',2:'quiet'}[self.current_profile]},
                'button_brightness': {'value':2}}


def main():
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as pw:
        device = TurboDemo()
        api = Api(device, Presets(Path(tmp)/'presets.json'), SimMetrics(), demo=True)
        browser = pw.chromium.launch(headless=True, executable_path='/usr/bin/chromium',
            args=['--no-sandbox','--disable-dev-shm-usage','--no-proxy-server'])
        page = browser.new_page(viewport={'width':1727,'height':863})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        def backend(path, method, payload):
            try:
                result = api.read(path) if method=='GET' else api.write(path,payload)
                return {'status':200,'body':result}
            except (MetaCubeError, KeyError) as error:
                return {'status':400,'body':{'error':str(error)}}
        page.goto('about:blank')
        page.expose_function('mockTurboBackend',backend)
        html = (ROOT/'web/index.html').read_text(encoding='utf-8').replace('<script src="/app.js" defer></script>', '')
        page.set_content(html,wait_until='domcontentloaded')
        page.add_style_tag(content=(ROOT/'web/styles.css').read_text(encoding='utf-8'))
        page.evaluate('''() => {
            const session={}, prefs={};
            Object.defineProperty(window,'sessionStorage',{configurable:true,value:{
              getItem:k=>session[k]||null,setItem:(k,v)=>{session[k]=String(v)}
            }});
            Object.defineProperty(window,'localStorage',{configurable:true,value:{
              getItem:k=>prefs[k]||null,setItem:(k,v)=>{prefs[k]=String(v)},removeItem:k=>{delete prefs[k]}
            }});
            window.fetch=async (path,opts={})=>{
              const d=await window.mockTurboBackend(path,opts.method||'GET',JSON.parse(opts.body||'{}'));
              return {ok:d.status>=200&&d.status<300,status:d.status,json:async()=>d.body};
            };
        }''')
        page.add_script_tag(content=(ROOT/'web/app.js').read_text(encoding='utf-8'))
        page.locator('#tokenInput').fill('x'*48)
        page.locator('#loginForm button[type=submit]').click()
        page.locator('[data-view="system"]').click()
        turbo = page.locator('#view-system [data-profile="0"]')
        quiet = page.locator('#view-system [data-profile="2"]')
        dialog = page.locator('#turboConfirmDialog')
        assert not page.locator('#turboSkipConfirm').is_checked()
        assert turbo.is_enabled()

        turbo.click()
        assert dialog.is_visible()
        page.locator('#turboDialogNeverTips').check()
        page.locator('#turboConfirmCancel').click()
        assert not dialog.is_visible()
        assert not device.platform_changes, 'Cancel must not change firmware'
        assert page.evaluate("localStorage.getItem('metacube-turbo-never-tips')") is None

        turbo.click()
        assert dialog.is_visible()
        page.locator('#turboDialogNeverTips').check()
        page.locator('#turboConfirmAccept').click()
        page.wait_for_function('() => document.querySelector("#turboSkipConfirm").checked')
        page.wait_for_function('(value) => [...document.querySelectorAll("#view-system [data-profile]")].some(el=>el.dataset.profile===value&&el.classList.contains("active"))', arg='0')
        assert device.platform_changes==[0],device.platform_changes
        assert page.evaluate("localStorage.getItem('metacube-turbo-never-tips')")=='1'

        quiet.click()
        page.wait_for_function('(value) => [...document.querySelectorAll("#view-system [data-profile]")].some(el=>el.dataset.profile===value&&el.classList.contains("active"))', arg='2')
        turbo.click()
        page.wait_for_function('(value) => [...document.querySelectorAll("#view-system [data-profile]")].some(el=>el.dataset.profile===value&&el.classList.contains("active"))', arg='0')
        assert device.platform_changes==[0,2,0],device.platform_changes
        assert not dialog.is_visible(), 'Suppressed Turbo prompt must not appear'

        page.locator('#turboSkipConfirm').uncheck()
        assert page.evaluate("localStorage.getItem('metacube-turbo-never-tips')") is None
        quiet.click()
        page.wait_for_function('(value) => [...document.querySelectorAll("#view-system [data-profile]")].some(el=>el.dataset.profile===value&&el.classList.contains("active"))', arg='2')
        turbo.click()
        assert dialog.is_visible(), 'Re-enabling prompt from the performance page must work'
        page.keyboard.press('Escape')
        assert not dialog.is_visible()
        assert device.platform_changes==[0,2,0,2], device.platform_changes

        device.ac_online=False
        page.evaluate('loadProfileStatus()')
        page.wait_for_function('() => [...document.querySelectorAll("#view-system [data-profile]")].some(el=>el.dataset.profile==="0"&&el.disabled)')
        assert turbo.is_disabled(), 'AC offline must still prevent Turbo even if the user chooses NeverTips'
        assert not errors,errors
        print('Turbo OEM NeverTips mock-browser checks passed (no firmware calls)')
        browser.close()

if __name__=='__main__':
    main()
