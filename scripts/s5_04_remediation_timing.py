"""Supplemental timing only, frozen inputs and candidates; no selection."""
import hashlib,json,os,time,platform
from pathlib import Path
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import ExtraTreesRegressor,RandomForestRegressor,GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from catalyst_ai.features.pipeline import R1Features
from catalyst_ai.modeling.baseline import target_value
from catalyst_ai.modeling.config import Model
from catalyst_ai.modeling.research_run import environment
from catalyst_ai.modeling.s5_selection import predict
root=Path(__file__).resolve().parents[1]; old=root/'artifacts/reports/s5-04-e02-20261124-v1'; out=root/'artifacts/reports/s5-04-remediation-20261124-v1/timing-v1';out.mkdir(exist_ok=False)
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
snap=root/'data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json'; content=read(snap)['content']; byid={r['record_id']:r for r in content['records']}
inputs={str(p.relative_to(root)):sha(p) for p in [snap,*[old/f'{phase}-{seed}'/f for phase in ('fixed','search') for seed in (45,46,47) for f in ('lock.json','config.json','split.json','holdout/all_arms.json')]]}
lock={'purpose':'post-review supplemental cost measurement; no selection or new blind evaluation','environment':environment(),'thread_environment':{k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')},'inputs_sha256':inputs,'script_sha256':sha(Path(__file__)),'started_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()};write(out/'run-lock.json',lock)
results={}
for phase in ('fixed','search'):
 for seed in (45,46,47):
  name=f'{phase}-{seed}'; run=old/name; config=read(run/'config.json'); split=read(run/'split.json'); oldheld=read(run/'holdout/all_arms.json'); rows=[byid[i] for i in sorted(split['train'])]; target=[target_value(r,content) for r in rows]; results[name]=[]
  for i,c in enumerate(config['candidates']):
   m=Model.model_validate({'name':c['model'],'params':c.get('params',{})}); p=m.params
   model={'extra_trees':lambda:ExtraTreesRegressor(random_state=42,**p),'random_forest':lambda:RandomForestRegressor(random_state=42,**p),'gradient_boosting':lambda:GradientBoostingRegressor(random_state=42,**p),'dummy':lambda:DummyRegressor(strategy='mean'),'ridge':lambda:make_pipeline(StandardScaler(),Ridge(**p))}[m.name]()
   start=time.perf_counter(); trans=R1Features.fit([r['payload'] for r in rows],c['feature']); X=[trans.transform_one(r['payload'])['values'] for r in rows]; model.fit(X,target); fit=time.perf_counter()-start
   hold=oldheld[i]['predictions']; hrows=[byid[r['record_id']] for r in hold];start=time.perf_counter();pred=predict(trans,model,hrows);elapsed=time.perf_counter()-start
   same=all({k:v for k,v in a.items() if k not in ('record_id','doi','observed')}==json.loads(json.dumps(b)) for a,b in zip(hold,pred,strict=True))
   results[name].append({'candidate_index':i,'candidate':c,'train_records':len(rows),'predict_records':len(hrows),'refit_seconds_including_feature_fit_and_encoding':fit,'predict_seconds_including_encoding':elapsed,'reproduces_saved_predictions':same});write(out/'timings.json',results)
   assert same,(name,i)
  print(name,'completed',flush=True)
write(out/'completion.json',{'runs':len(results),'arms':sum(map(len,results.values())),'completed_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'run_lock_sha256':sha(out/'run-lock.json'),'timings_sha256':sha(out/'timings.json')})
