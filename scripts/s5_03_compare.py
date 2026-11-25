import csv, json, math, statistics, hashlib
from collections import defaultdict, Counter
from pathlib import Path
root=Path('artifacts/reports/s5-03-start-20261124')
def available(r): return r['status'] in ('ok','caution') and isinstance(r.get('raw_prediction'),(float,int)) and math.isfinite(r['raw_prediction'])
def metric(rows):
 if not rows: return None
 e=[abs(r['raw_prediction']-r['observed']) for r in rows]; by=defaultdict(list)
 for r,v in zip(rows,e): by[r['doi']].append(v)
 return {'n':len(rows),'doi_n':len(by),'mae':statistics.mean(e),'rmse':math.sqrt(statistics.mean(x*x for x in e)),'doi_equal_mae':statistics.mean(statistics.mean(v) for v in by.values())}
results={}; records=[]
for seed in (45,46,47):
 def arm(prefix,idx):
  v=json.loads((root/f'{prefix}-{seed}/holdout/all_arms.json').read_text(encoding='utf-8'))[idx]['predictions']; return {r['record_id']:r for r in v}
 b=arm('b-select',0); a=arm('a',0); c=arm('b2',1); ids=set(b); assert ids<=set(a) and ids==set(c)
 for i in ids:
  assert a[i]['observed']==b[i]['observed']==c[i]['observed']
  records.append({'seed':seed,'record_id':i,'doi':b[i]['doi'],'observed':b[i]['observed'],**{f'{k}_{col}':v[i].get(col) for k,v in [('A',a),('B1',b),('B2',c)] for col in ('status','raw_prediction')}})
 supports={k:{i for i in ids if available(v[i])} for k,v in [('A',a),('B1',b),('B2',c)]}; triple=set.intersection(*supports.values()); pairs={}
 for x,y in [('A','B1'),('B1','B2')]:
  maps={'A':a,'B1':b,'B2':c}; shared=supports[x]&supports[y]; mx=metric([maps[x][i] for i in shared]); my=metric([maps[y][i] for i in shared]); pairs[f'{x}_to_{y}']={'common':len(shared),'first':mx,'second':my,'mae_delta':my['mae']-mx['mae'] if mx else None,'doi_equal_mae_delta':my['doi_equal_mae']-mx['doi_equal_mae'] if mx else None}
 results[str(seed)]={'denominator':len(ids),'available':{k:len(v) for k,v in supports.items()},'triple':len(triple),'individual':{k:metric([v[i] for i in supports[k]]) for k,v in [('A',a),('B1',b),('B2',c)]},'pairs':pairs,'status':{k:dict(Counter(v[i]['status'] for i in ids)) for k,v in [('A',a),('B1',b),('B2',c)]}}
with (root/'paired_predictions.csv').open('w',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(records[0])); w.writeheader(); w.writerows(sorted(records,key=lambda x:(x['seed'],x['record_id'])))
(root/'paired_metrics.json').write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(results,indent=2,ensure_ascii=False))
