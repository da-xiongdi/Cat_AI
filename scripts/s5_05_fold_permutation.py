import json, numpy as np, statistics
from pathlib import Path
from sklearn.ensemble import ExtraTreesRegressor
from catalyst_ai.features.pipeline import R1Features
from catalyst_ai.modeling.baseline import target_value
from catalyst_ai.modeling.s5_selection import predict,_available
R=Path(__file__).resolve().parents[1]; O=R/'artifacts/reports/s5-05-e05-20261124-v1'
def rd(p):return json.loads(p.read_text(encoding='utf-8-sig'))
snap=rd(R/'data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json')['content']; rows={r['record_id']:r for r in snap['records']}; out={}
for seed in (45,46,47):
 p=O/f'run-{seed}';split=rd(p/'split.json');cv=rd(p/'cross_validation.json');target={r['record_id']:r for r in cv['results'][0]['predictions']};params=cv['results'][0]['candidate']['params'];out[str(seed)]=[]
 for n,fold in enumerate(split['validation_folds']):
  ids=sorted(set(split['train'])-set(fold)); validation=[rows[i] for i in sorted(fold)]; trans=R1Features.fit([rows[i]['payload'] for i in ids],'F_base');X=[trans.transform_one(rows[i]['payload'])['values'] for i in ids]; y=[target_value(rows[i],snap) for i in ids];model=ExtraTreesRegressor(random_state=42,**params).fit(X,y); predicted=predict(trans,model,validation)
  for row,pred in zip(validation,predicted,strict=True):
   original=target[row['record_id']];assert {k:v for k,v in original.items() if k not in ('record_id','doi','observed','fold')}==json.loads(json.dumps(pred))
  val=[r for r,pred in zip(validation,predicted,strict=True) if _available(pred)]; x=np.array([trans.transform_one(r['payload'],diagnostic=True)['values'] for r in val]); y=np.array([target[r['record_id']]['observed'] for r in val]);base=np.abs(model.predict(x)-y); rng=np.random.default_rng(20261124+seed*10+n);res={}
  for name,cols in {'conditions':list(range(4)),'composition':list(range(4,x.shape[1]))}.items():
   vals=[]
   for _ in range(10):
    xp=x.copy();xp[:,cols]=x[rng.permutation(len(x))][:,cols];vals.append(float(np.mean(np.abs(model.predict(xp)-y)-base)))
   res[name]={'mean':statistics.mean(vals),'sd':statistics.pstdev(vals),'repeats':vals}
  out[str(seed)].append({'fold':n,'validation_total':len(fold),'available':len(val),'baseline_mae':float(np.mean(base)),'verified_against_locked_oof':True,'blocks':res})
(O/'fold-permutation.json').write_text(json.dumps(out,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8');print('15 training folds reproduced and diagnosed')
