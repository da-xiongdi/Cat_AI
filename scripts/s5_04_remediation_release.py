import json
from pathlib import Path
import catalyst_ai
from catalyst_ai.modeling.research_run import load_locked_model,environment
from catalyst_ai.modeling.s5_selection import predict
root=Path(__file__).resolve().parents[1]; old=root/'artifacts/reports/s5-04-e02-20261124-v1'; out=root/'artifacts/reports/s5-04-remediation-20261124-v1'
assert 'site-packages' in str(Path(catalyst_ai.__file__).resolve())
snapshot=json.loads((root/'data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json').read_text(encoding='utf8'))
records={r['record_id']:r for r in snapshot['content']['records']}; result={}
for phase in ('fixed','search'):
 for seed in (45,46,47):
  name=f'{phase}-{seed}'; run=old/name
  lock,package=load_locked_model(run)
  held=json.loads((run/'holdout/all_arms.json').read_text(encoding='utf8'))
  for p,s in zip(package['packages'],held,strict=True):
   values=predict(p['transformer'],p['model'],[records[r['record_id']] for r in s['predictions']])
   for a,b in zip(s['predictions'],values,strict=True): assert {k:v for k,v in a.items() if k not in ('record_id','doi','observed')}==json.loads(json.dumps(b))
  result[name]={'arms':len(held),'records':sum(len(x['predictions']) for x in held),'formal_loader':'pass'}
(out/'formal-release-verification.json').write_text(json.dumps({'module':str(catalyst_ai.__file__),'environment':environment(),'runs':result},indent=2)+'\n',encoding='utf8')
print(result)
