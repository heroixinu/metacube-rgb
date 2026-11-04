"""Desktop no-document-scroll regression using only simulated WMI/API.
Run: python3 tests/test_single_screen.py
"""
from pathlib import Path
import tempfile
from playwright.sync_api import sync_playwright
from test_console_dashboard import SimDevice, SimMetrics, run_view
from metacube_rgb.web import Api
from metacube_rgb.core import Presets

VIEWPORTS=((1920,1080),(1672,941),(1440,900),(1366,768),(1280,720))
VIEWS=('dashboard','lighting','system','diagnostics')

def main():
    with tempfile.TemporaryDirectory() as temp, sync_playwright() as p:
        backend=SimDevice()
        api=Api(backend,Presets(Path(temp)/'presets.json'),SimMetrics(),demo=True)
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage','--no-proxy-server'])
        page=browser.new_page(viewport={'width':1672,'height':941},device_scale_factor=1)
        run_view(page,api)
        for width,height in VIEWPORTS:
            page.set_viewport_size({'width':width,'height':height})
            for view in VIEWS:
                page.locator(f'[data-view="{view}"]').click()
                page.wait_for_timeout(80)
                state=page.evaluate('''() => {
                  const root=document.documentElement;
                  const active=document.querySelector('.view.active');
                  const rect=active.getBoundingClientRect();
                  return {scrolled:root.scrollHeight-root.clientHeight,
                    horizontal:root.scrollWidth-root.clientWidth,
                    visibleBottom:rect.bottom,viewport:innerHeight};
                }''')
                assert state['scrolled']<=1,(width,height,view,state)
                assert state['horizontal']<=1,(width,height,view,state)
                assert state['visibleBottom']<=height+1,(width,height,view,state)
                if view=='dashboard' and width>=1251:
                    fill=page.evaluate('''() => {
                      const box=s=>document.querySelector(s).getBoundingClientRect();
                      const main=box('.console-primary-grid');
                      const rgb=box('.console-rgb-panel');
                      const apply=box('#dashboardApplyButton');
                      const presets=box('.console-preset-panel');
                      const tiles=[...document.querySelectorAll('.dashboard-preset-tile .system-template-ring')]
                        .map(el=>el.getBoundingClientRect());
                      const aside=box('.console-aside-column');
                      return {bottom:main.bottom,asideBottom:aside.bottom,viewport:innerHeight,
                        applyVisible:apply.bottom<=rgb.bottom+1,
                        presetsVisible:presets.bottom<=innerHeight,
                        ringsCircular:tiles.every(r=>r.width>=25 && r.height>=25 && Math.abs(r.width-r.height)<=1),
                        headingFont:parseFloat(getComputedStyle(document.querySelector('.console-panel-head h2')).fontSize)};
                    }''')
                    assert fill['bottom'] >= height-20 and fill['asideBottom'] >= height-20,(width,height,'unfilled viewport',fill)
                    assert fill['applyVisible'] and fill['presetsVisible'],(width,height,'clipped primary action',fill)
                    assert fill['ringsCircular'],(width,height,'squashed preset ring',fill)
                    assert fill['headingFont']>=12,(width,height,'undersized heading',fill)
        page.set_viewport_size({'width':1366,'height':768})
        page.locator('[data-view="lighting"]').click()
        page.locator('#inspectPacketButton').click()
        assert page.locator('#packetCard').is_visible()
        state=page.evaluate('''() => document.documentElement.scrollHeight-document.documentElement.clientHeight''')
        assert state<=1,('packet inspector should not add page scroll',state)
        assert backend.writes==0, 'Only previews; no real or simulated firmware SET is allowed in this test'
        browser.close()
        print('Single-screen UI: 5 desktop viewports × 4 pages, packet inspector, no page scroll / no hardware write OK')

if __name__=='__main__':main()
