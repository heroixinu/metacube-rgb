"""Mock-only dashboard responsiveness and control behavior. Never accesses real WMI."""
from pathlib import Path
import sys, tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from metacube_rgb.core import Presets, MetaCubeError
from metacube_rgb.web import Api, DemoDevice

ROOT=Path(__file__).resolve().parents[1]
class SimDevice(DemoDevice):
    def __init__(self):
        super().__init__()
        self._current.update(mode='spin',colors=['0033AA','0088FF','00E5D4','8844FF'],brightness=197,speed=2,direction=0,cycle=0,transition=0)
        self.writes=0
    def lighting(self, changes, expected_raw=None):
        self.writes+=1
        return super().lighting(changes,expected_raw)
    def state(self):
        d=super().state();d['speed_customization_enabled']=True;d['rgb_experimental_enabled']=True;return d
    def profile_status(self):
        return {'profile':{'value':1,'label':'balanced'}, 'power':{'ac_online':True,'source':'demo'},
            'write_enabled':False,'available_modes':{'turbo':0,'balanced':1,'quiet':2},'turbo_available':True,'manual_fan_speed_supported':False}
    def fans(self):
        return {'available':True,'main_rpm':4045,'small_rpm':1838,'source':'metacube_oem_0x14','poll_seconds':2,'manual_control':False,'note':'模拟 GET 0x14'}
class SimMetrics:
    def snapshot(self):
        return {'cpu':{'percent':22.7,'count':16,'frequency_ghz':3.8,'load':[0.48,0.55,0.6],'model':'AMD Ryzen 7 8845HS'},
            'memory':{'percent':34.4,'used':23622320128,'total':68719476736},
            'disk':{'percent':41.0,'used':440234147840,'total':1073741824000},
            'kernel':'7.0.14-26-pve','host':'pve','uptime_seconds':388800,
            'dmi':{'product_name':'MetaCube','board_name':'M11 Series-HPT','bios_version':'M11HPTXPV1313'},
            'temperatures':[{'name':'Tctl','celsius':47.2}], 'fans':[],
            'gpu':{'devices':[],'percent':None}, 'network':{'rx_bytes_per_second':0,'tx_bytes_per_second':0,'interfaces':[]}}

def run_view(page, api):
    errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
    async_errors=[]
    page.on('console',lambda m:async_errors.append(m.text) if m.type=='error' else None)
    def backend(path,method,payload):
        try:return {'status':200,'body':api.read(path) if method=='GET' else api.write(path,payload)}
        except (MetaCubeError,KeyError) as e:return {'status':400,'body':{'error':str(e)}}
    page.goto('about:blank')
    page.expose_function('mockBackend',backend)
    html=(ROOT/'web/index.html').read_text().replace('<script src="/app.js" defer></script>','')
    page.set_content(html,wait_until='domcontentloaded')
    page.add_style_tag(content=(ROOT/'web/styles.css').read_text())
    page.evaluate('''() => {
       const d={}; Object.defineProperty(window,'sessionStorage',{configurable:true,value:{getItem(k){return d[k]||null},setItem(k,v){d[k]=String(v)}}});
       window.fetch=async(path,opts={})=>{const p=JSON.parse(opts.body||'{}');const data=await window.mockBackend(path,opts.method||'GET',p);return {ok:data.status>=200&&data.status<300,status:data.status,json:async()=>data.body}};
    }''')
    page.add_script_tag(content=(ROOT/'web/app.js').read_text())
    page.locator('#tokenInput').fill('x'*48)
    page.locator('#loginForm button[type=submit]').click()
    page.locator('#dashMainFan').get_by_text('4,045').wait_for(timeout=4000)
    assert page.locator('#dashboardRing').get_attribute('style').find('conic-gradient')>=0
    assert page.locator('#dashPerf').inner_text()=='均衡'
    assert page.locator('#dashAcState').inner_text()=='已接入 AC'
    assert page.locator('#dashboardHostInfo .dashboard-host-row').count()==6
    assert page.locator('#dashboardPresetCards .dashboard-preset-tile').count()==4
    assert not errors,(errors,async_errors)
    return errors,async_errors

def main():
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory() as tmp,sync_playwright() as p:
        backend=SimDevice();api=Api(backend,Presets(Path(tmp)/'presets.json'),SimMetrics(),demo=True)
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage','--no-proxy-server'])
        page=browser.new_page(viewport={'width':1672,'height':941},device_scale_factor=1)
        errors,async_errors=run_view(page,api)
        page.evaluate("document.querySelector('#toast').classList.remove('visible')")
        page.screenshot(path='/mnt/data/metacube-control-dashboard-desktop.png',full_page=True)
        # Editing is always a preview until explicitly applied.
        page.locator('#view-dashboard [data-mode="breath"]').click()
        assert backend.writes==0
        assert page.locator('#dashboardApplyButton').is_enabled()
        page.locator('#dashboardApplyButton').click()
        page.wait_for_timeout(200)
        assert backend.writes==1
        assert page.locator('#dashboardEvents li').count()>=1
        page.locator('#view-dashboard [data-dashboard-presets="user"]').click()
        assert page.get_by_text('暂无已保存的用户预设').count()==1
        page.locator('#view-dashboard [data-dashboard-presets="system"]').click()
        assert page.locator('#dashboardPresetCards .dashboard-preset-tile').count()==4
        assert page.locator('#view-dashboard [data-profile="0"]').is_disabled()
        assert page.locator('#dashSpeedLabel').inner_text().find('可调整')>=0
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_timeout(150)
        page.evaluate("document.querySelector('#toast').classList.remove('visible')")
        page.screenshot(path='/mnt/data/metacube-control-dashboard-mobile.png',full_page=True)
        overflow=page.evaluate('''() => ({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth})''')
        assert overflow['scroll']<=overflow['client']+1,overflow
        assert not errors,(errors,async_errors)
        print('Console dashboard Chromium desktop + mobile, draft/apply, cards, fans, permissions and screenshots OK')
        browser.close()
if __name__=='__main__':main()
