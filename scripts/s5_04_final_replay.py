import hashlib,json,subprocess,zipfile,datetime
from pathlib import Path
from catalyst_ai.modeling.research_run import load_locked_model,code_hash,environment
from catalyst_ai.modeling.s5_selection import predict
root=Path(__file__).resolve().parents[1];out=root/'artifacts/reports/s5-04-final-acceptance-v1';out.mkdir(parents=True,exist_ok=False); archive=out/'original-source';archive.mkdir()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf8'))
old=root/'artifacts/reports/s5-04-e02-20261124-v1'; manifest=read(old/'evidence-sha256-final.json')['files'];wheel=old/'release-wheel/catalyst_ai-0.1.0-py3-none-any.whl'; restored={}
with zipfile.ZipFile(wheel) as z:
 for n in z.namelist():
  if n.startswith('catalyst_ai/') and n.endswith('.py'):
   key='src/'+n; content=z.read(n); assert hashlib.sha256(content).hexdigest()==manifest[key],key;p=archive/key;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(content);restored[key]={'sha256':sha(p),'source':'original locked wheel','archive':p.relative_to(root).as_posix()}
for n in ('pyproject.toml','uv.lock'):
 p=subprocess.run(['git','show','7fb1228:'+n],cwd=root,capture_output=True,check=True);assert hashlib.sha256(p.stdout).hexdigest()==manifest[n],n;dest=archive/n;dest.write_bytes(p.stdout);restored[n]={'sha256':sha(dest),'source':'git commit 7fb1228, verified against original manifest','archive':dest.relative_to(root).as_posix()}
assert len(restored)>=5
snap=read(root/'data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json');rows={r['record_id']:r for r in snap['content']['records']};runs={}
for phase in ('fixed','search'):
 for seed in (45,46,47):
  name=f'{phase}-{seed}';run=old/name;lock,pkg=load_locked_model(run);arms=read(run/'holdout/all_arms.json');assert code_hash()==lock['environment']['code_sha256'];assert len(pkg['packages'])==len(arms)
  for a,b in zip(pkg['packages'],arms,strict=True):
   ps=predict(a['transformer'],a['model'],[rows[r['record_id']] for r in b['predictions']]);assert all({k:v for k,v in x.items() if k not in ('record_id','doi','observed')}==json.loads(json.dumps(y)) for x,y in zip(b['predictions'],ps,strict=True))
  runs[name]={'formal_loader':'pass','arms':len(arms),'records':sum(len(a['predictions']) for a in arms),'lock_sha256':sha(run/'lock.json')}
assert sum(x['arms'] for x in runs.values())==48 and sum(x['records'] for x in runs.values())==5184
result={'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'purpose':'read-only original model reload and prediction reproduction, not new experiment','original_manifest_sha256':sha(old/'evidence-sha256-final.json'),'original_wheel_sha256':sha(wheel),'code_sha256':code_hash(),'environment':environment(),'restored':restored,'runs':runs}
(out/'original-replay.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print('restored original files',len(restored),'formal replay 48 arms and 5184 predictions pass')
