import pathlib, threading, time, json
import uvicorn
from playwright.sync_api import sync_playwright
from catalyst_ai.web.app import create_app
root=pathlib.Path.cwd(); out=root/'artifacts/wb14-06-evidence'; db=out/'rehearsal-v2.sqlite'
s=uvicorn.Server(uvicorn.Config(create_app(db,root),host='127.0.0.1',port=18767,log_level='error')); threading.Thread(target=s.run,daemon=True).start()
for _ in range(100):
 if s.started: break
 time.sleep(.1)
results=[]
try:
 with sync_playwright() as p:
  b=p.chromium.launch(channel='msedge',headless=True)
  for w,h in [(1366,768),(1920,1080),(390,844)]:
   page=b.new_page(viewport={'width':w,'height':h}); errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto('http://127.0.0.1:18767/roadmap'); page.wait_for_selector('.roadmap-card',state='attached')
   panel=page.locator('#roadmap-canvas')
   if w == 390:
    assert page.locator('a[href*=\"node=\"]').count() > 0
    page.screenshot(path=str(out/f'edge-{w}.png'),full_page=True)
    results.append({'viewport':[w,h],'tree_links': 'passed','page_errors':errors}); page.close(); continue
   for action in ['collapse','expand','in','out','fit','reset','fullscreen','fullscreen']:
    panel.locator('[data-action="'+action+'"]').click(force=True); page.wait_for_timeout(300)
   page.screenshot(path=str(out/f'edge-{w}.png'),full_page=True)
   assert not errors,errors
   results.append({'viewport':[w,h],'controls':'passed','page_errors':errors})
   page.close()
  b.close()
finally: s.should_exit=True
(out/'browser.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
print(results)
