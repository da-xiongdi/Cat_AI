import json, math, hashlib, statistics, collections
from pathlib import Path
import numpy as np
from catalyst_ai.modeling.research_run import load_locked_model
from catalyst_ai.modeling.s5_selection import predict, _available
from catalyst_ai.features.pipeline import project, CONDITIONS
R=Path(__file__).resolve().parents[1];O=R/'artifacts/reports/s5-05-e05-20261124-v1'
def rd(p):return json.loads(p.read_text(encoding='utf-8-sig'))
snap=rd(R/'data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json'); records={r['record_id']:r for r in snap['content']['records']}; out={}
for seed in (45,46,47):
 p=O/f'run-{seed}';lock,pkg=load_locked_model(p); arms=rd(p/'holdout/all_arms.json'); checks=[]
 for item in arms:
  i=item['candidate_index']; z=pkg['packages'][i]; rows=item['predictions']; new=predict(z['transformer'],z['model'],[records[r['record_id']] for r in rows])
  for a,b in zip(rows,new,strict=True): assert {k:v for k,v in a.items() if k not in ('record_id','doi','observed')}==json.loads(json.dumps(b))
  checks.append(len(rows))
 idx=lock['selected_index']; z=pkg['packages'][idx]; t=z['transformer']; model=z['model']; assert t.feature_set=='F_base'; rows=arms[idx]['predictions']; valid=[r for r in rows if _available(r)]; X=np.array([t.transform_one(records[r['record_id']]['payload'],diagnostic=True)['values'] for r in valid]); y=np.array([r['observed'] for r in valid]); base=float(np.mean(np.abs(model.predict(X)-y))); rng=np.random.default_rng(20261124); block={}
 for name,cols in {'conditions':list(range(4)),'composition':list(range(4,X.shape[1]))}.items():
  vals=[]
  for _ in range(10):
   xp=X.copy();xp[:,cols]=X[rng.permutation(len(X))][:,cols];vals.append(float(np.mean(np.abs(model.predict(xp)-y)-np.abs(model.predict(X)-y))))
  block[name]={'mean_increase_mae':statistics.mean(vals),'sd':statistics.pstdev(vals),'repeats':vals,'columns':len(cols)}
 cfg=rd(p/'config.json');split=rd(p/'split.json');tr=[project(records[i]['payload']) for i in split['train']];species=collections.Counter()
 for r in tr:
  for (role,name),amount in r['amounts'].items():
   if amount>0:species[f'{role}:{name}']+=1
 out[str(seed)]={'replay_arm_record_counts':checks,'train_n':len(tr),'train_conditions':{k:{'min':min(r['conditions'][k] for r in tr),'max':max(r['conditions'][k] for r in tr)} for k in CONDITIONS},'train_species_roles':dict(sorted(species.items())),'holdout_statuses':dict(collections.Counter(r['status'] for r in rows)),'holdout_out_of_range_n':sum(bool(r.get('out_of_range')) for r in rows),'holdout_unseen_species_role_n':sum(bool(r.get('unseen_species_roles')) for r in rows),'permutation':{'members':'available selected-arm holdout; fixed full-training model, post-hoc exploratory','n':len(valid),'baseline_mae':base,'seed':20261124,'block':block},'model_lock':lock['artifacts']['model.pkl']}
(O/'applicability-and-permutation.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8');print('replayed all arms and generated applicability, block permutation')


