import json, math, statistics
from pathlib import Path
from catalyst_ai.modeling.research_run import load_locked_model
from catalyst_ai.modeling.s5_selection import predict
root=Path('artifacts/reports/s5-03-start-20261124'); snap=json.loads(Path('data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json').read_text(encoding='utf-8')); rows={r['record_id']:r for r in snap['content']['records']}; report={}
def avail(r): return r['status'] in ('ok','caution') and isinstance(r.get('raw_prediction'),(int,float)) and math.isfinite(r['raw_prediction'])
for seed in (45,46,47):
 run=root/f'b-select-{seed}'; cv=json.loads((run/'cross_validation.json').read_text(encoding='utf-8')); arms=json.loads((run/'holdout/all_arms.json').read_text(encoding='utf-8')); base={r['record_id']:r for r in arms[0]['predictions']}; comparisons=[]
 for arm in arms:
  idx=arm['candidate_index']; rr={r['record_id']:r for r in arm['predictions']}; common=[i for i in base if avail(base[i]) and avail(rr[i])]; delta=statistics.mean(abs(rr[i]['observed']-rr[i]['raw_prediction'])-abs(base[i]['observed']-base[i]['raw_prediction']) for i in common) if common else None
  comparisons.append({'feature':cv['results'][idx]['candidate']['feature'],'denominator':len(rr),'available':sum(avail(r) for r in rr.values()),'common_with_base':len(common),'mae_delta_vs_base':delta})
 reloaded={}
 for prefix,index in [('a',0),('b-select',0),('b2',1)]:
  path=root/f'{prefix}-{seed}'; lock,package=load_locked_model(path); arm=package['packages'][index]; old=json.loads((path/'holdout/all_arms.json').read_text(encoding='utf-8'))[index]['predictions']; sample=old[:min(5,len(old))]; predicted=predict(arm['transformer'],arm['model'],[rows[r['record_id']] for r in sample]); assert all(a['status']==b['status'] and a['raw_prediction']==b['raw_prediction'] for a,b in zip(sample,predicted)); reloaded[prefix]=len(sample)
 report[str(seed)]={'selected':cv['results'][cv['selected_index']]['candidate']['feature'],'selection_decision':cv['selection_decision'],'general_holdout_comparisons':comparisons,'reload_verified_counts':reloaded}
(root/'general_ablation_and_reload.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps({s:{'selected':r['selected'],'comparisons':r['general_holdout_comparisons'],'reload':r['reload_verified_counts']} for s,r in report.items()},indent=2))
