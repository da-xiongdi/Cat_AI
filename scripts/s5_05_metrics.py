import json, math, hashlib, statistics, collections
from pathlib import Path
from catalyst_ai.modeling.s5_metrics import compare
from catalyst_ai.modeling.s5_selection import _available
from catalyst_ai.modeling.baseline import metrics
from catalyst_ai.modeling.research_run import load_locked_model
R=Path(__file__).resolve().parents[1]; O=R/'artifacts/reports/s5-05-e05-20261124-v1'
def rd(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def sm(rows):
 valid=[r for r in rows if isinstance(r.get('raw_prediction'),(int,float)) and math.isfinite(r['raw_prediction'])]; available=[r for r in rows if _available(r)]; doi=collections.defaultdict(list)
 for r in available:doi[r['doi']].append(abs(r['observed']-r['raw_prediction']))
 def calc(rs):return metrics([r['observed'] for r in rs],[r['raw_prediction'] for r in rs]) if rs else {'mae':None,'rmse':None,'r2':None,'r2_unavailable_reason':'no valid predictions'}
 err=sorted(r['raw_prediction']-r['observed'] for r in available)
 return {'total':len(rows),'diagnostic_n':len(valid),'diagnostic':calc(valid),'available_n':len(available),'coverage':len(available)/len(rows) if rows else None,'available':calc(available),'doi_n':len(doi),'doi_equal_mae':statistics.mean(statistics.mean(x) for x in doi.values()) if doi else None,'bias':statistics.mean(err) if err else None,'residual_min_median_max':[err[0],statistics.median(err),err[-1]] if err else None,'statuses':dict(collections.Counter(r.get('status') for r in rows)),'doi_strata':{k:{'n':len(v),'mae':statistics.mean(v)} for k,v in sorted(doi.items())}}
def run_report(p):
 cv=rd(p/'cross_validation.json'); held=rd(p/'holdout/all_arms.json'); a={str(i):x['predictions'] for i,x in enumerate(cv['results'])}; b={str(x['candidate_index']):x['predictions'] for x in held}; assert set(a)==set(b)
 return {'config_sha256':sha(p/'config.json'),'lock_sha256':sha(p/'lock.json'),'selected_index':cv['selected_index'],'candidates':[x['candidate'] for x in cv['results']],'oof_common':compare(a),'holdout_common':compare(b),'oof':{k:sm(v) for k,v in a.items()},'holdout':{k:sm(v) for k,v in b.items()},'folds':{k:{str(f):sm([r for r in v if r['fold']==f]) for f in sorted({r['fold'] for r in v})} for k,v in a.items()}}
out={}
for s in (45,46,47):
 p=O/f'run-{s}'; lock,pkg=load_locked_model(p); x=run_report(p); assert lock['selected_index']==x['selected_index']; out[str(s)]=x
(O/'metrics.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
hist={}; gaps=[]
for pattern in ('s5-02-e01-*/run','s5-03-start-20261124/*','s5-04-e02-20261124-v1/fixed-*','s5-04-e02-20261124-v1/search-*','s4-04-runs-20261120-v1/EXP-*'):
 for p in sorted((R/'artifacts/reports').glob(pattern)):
  if not p.is_dir() or not (p/'cross_validation.json').exists():continue
  key=p.relative_to(R).as_posix()
  try:
   cv=rd(p/'cross_validation.json'); results=cv['results']; res={'cross_validation_sha256':sha(p/'cross_validation.json'),'oof':{str(i):sm(x['predictions']) for i,x in enumerate(results)}}
   h=p/'holdout/all_arms.json'
   if h.exists(): res['holdout_sha256']=sha(h);res['holdout']={str(x['candidate_index']):sm(x['predictions']) for x in rd(h)}
   elif (p/'holdout/predictions.json').exists():
    h=p/'holdout/predictions.json';res['holdout_sha256']=sha(h);res['holdout_selected']=sm(rd(h))
   else:res['holdout_gap']='no prediction file'
   hist[key]=res
  except Exception as e:gaps.append({'run':key,'reason':str(e)})
(O/'historical-r2.json').write_text(json.dumps({'runs':hist,'gaps':gaps},ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
print('E05 metrics',len(out),'historical',len(hist),'gaps',len(gaps)); print(json.dumps({s:{'chosen':v['candidates'][v['selected_index']],'holdout':v['holdout'][str(v['selected_index'])]['available'],'coverage':v['holdout'][str(v['selected_index'])]['coverage'],'doi_mae':v['holdout'][str(v['selected_index'])]['doi_equal_mae']} for s,v in out.items()},ensure_ascii=False))
