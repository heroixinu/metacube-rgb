import tempfile,sys,subprocess,time,os
from pathlib import Path
from playwright.sync_api import sync_playwright
base=Path(__file__).parents[1]
tokenfile=Path(tempfile.gettempdir())/'metacube_demo_token_qa'
tokenfile.write_text('q'*48+'\n');tokenfile.chmod(0o600)
env=os.environ.copy();env['PYTHONPATH']=str(base)
p=subprocess.Popen([sys.executable,'-m','metacube_rgb.cli','web','--demo','--port','18676','--token-file',str(tokenfile)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
try:
    time.sleep(.6)
    with sync_playwright() as pl:
        browser=pl.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage','--no-proxy-server','--proxy-bypass-list=*'])
        page=browser.new_page(viewport={'width':1440,'height':960},device_scale_factor=1)
        errs=[];page.on('pageerror',lambda error:errs.append(str(error)))
        page.goto('http://127.0.0.1:18676',wait_until='networkidle')
        page.locator('#tokenInput').fill('q'*48)
        page.get_by_text('解锁控制台').click()
        page.wait_for_timeout(900)
        page.screenshot(path='/mnt/data/metacube-web-dashboard-preview.png',full_page=True)
        page.locator('[data-view="lighting"]').click()
        page.wait_for_timeout(500)
        page.screenshot(path='/mnt/data/metacube-web-lighting-preview.png',full_page=True)
        page.locator('[data-view="system"]').click()
        page.wait_for_timeout(500)
        page.screenshot(path='/mnt/data/metacube-web-system-preview.png',full_page=True)
        # Interaction smoke tests
        page.locator('[data-view="lighting"]').click()
        page.locator('#addColorButton').click()
        count=page.locator('#colorEditor .color-row').count()
        page.locator('[data-mode="steady"]').click()
        page.locator('#applyLightingButton').click()
        page.wait_for_timeout(500)
        print('visual check dashboard/light/system captured')
        print('color count after click:',count)
        print('mode after apply:',page.locator('#heroMode').inner_text())
        print('errors',errs)
        browser.close()
finally:
    p.terminate()
    try:p.wait(timeout=5)
    except subprocess.TimeoutExpired:p.kill()
