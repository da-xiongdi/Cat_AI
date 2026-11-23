import json, pathlib, threading, time, sqlite3
import uvicorn
from playwright.sync_api import sync_playwright
from catalyst_ai.workbench import backup
from catalyst_ai.web.app import create_app
root=pathlib.Path.cwd(); out=root/'artifacts/wb14-06-evidence'; db=out/'browser-concurrency-v2.sqlite'
backup.backup_database(root/'data/workbench.sqlite',db)
with sqlite3.connect(db) as c:
 node=c.execute("select id from research_node where parent_id is not null and active=1 limit 1").fetchone()[0]
s=uvicorn.Server(uvicorn.Config(create_app(db,root),host='127.0.0.1',port=18768,log_level='error')); threading.Thread(target=s.run,daemon=True).start()
for _ in range(100):
 if s.started: break
 time.sleep(.1)
assert s.started
base='http://127.0.0.1:18768'; results={}
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(channel='msedge',headless=True)
  page=browser.new_page(viewport={'width':1366,'height':768}); errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(base+'/roadmap'); content=page.locator('.roadmap-content'); page.wait_for_selector('.roadmap-card')
  panel=page.locator('#roadmap-canvas'); act=lambda a: panel.locator('[data-action="'+a+'"]').click()
  initial=content.locator('.roadmap-card').count(); act('collapse'); assert content.locator('.roadmap-card').count() < initial
  act('expand'); page.get_by_text('加载完成',exact=False).first.wait_for(); assert content.locator('.roadmap-card').count()>=initial
  act('in'); assert float(content.evaluate('(e)=>parseFloat(e.style.zoom)'))>1
  act('out'); assert abs(float(content.evaluate('(e)=>parseFloat(e.style.zoom)'))-1)<0.01
  act('fit'); assert float(content.evaluate('(e)=>parseFloat(e.style.zoom)'))<=1
  act('reset'); assert float(content.evaluate('(e)=>parseFloat(e.style.zoom)'))==1
  act('fullscreen'); assert page.evaluate('!!document.fullscreenElement'); act('fullscreen'); assert not page.evaluate('!!document.fullscreenElement')
  link=content.locator('.roadmap-card a').first; link.focus(); page.keyboard.press('Enter'); page.wait_for_url('**/roadmap?node=*'); assert 'node=' in page.url; page.go_back(); assert page.url.endswith('/roadmap')
  assert not errors, errors; results['desktop']='collapse expand zoom fit reset fullscreen keyboard link and history passed'
  a=browser.new_page(); b=browser.new_page(); a.goto(base+'/roadmap?node='+node); b.goto(base+'/roadmap?node='+node)
  for tab,num in [(a,'901'),(b,'902')]:
   form=tab.locator('form[action="/actions/roadmap-node"]'); form.locator('[name=sort_order]').fill(num); form.locator('[name=reason]').fill('并发验收'); form.locator('[name=actor]').fill('验收')
  with a.expect_response(lambda r:'/actions/roadmap-node' in r.url and r.request.method=='POST') as ra: a.locator('form[action="/actions/roadmap-node"] button').click()
  with b.expect_response(lambda r:'/actions/roadmap-node' in r.url and r.request.method=='POST') as rb: b.locator('form[action="/actions/roadmap-node"] button').click()
  assert ra.value.status==303 and rb.value.status==409,(ra.value.status,rb.value.status)
  assert '修订' in b.locator('body').inner_text(); results['two_tabs']=[ra.value.status,rb.value.status]
  nojs=browser.new_page(java_script_enabled=False); nojs.goto(base+'/roadmap?view=tree'); assert nojs.locator('a[href*="node="]').count()>0; results['no_javascript']='tree links available'
  browser.close()
finally: s.should_exit=True
(out/'browser-functional.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8'); print(results)
