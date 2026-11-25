"""Freeze S5 M0 split using the accepted S4 ledger; no model fitting."""
import json,hashlib
from pathlib import Path
from collections import Counter
from catalyst_ai.datasets.research_prepare import prepare
from catalyst_ai.modeling.research_preflight import preflight,sha
from catalyst_ai.reporting.evidence import digest,write_json
ROOT=Path(__file__).resolve().parents[1]; BASE=ROOT/'artifacts/reports/s4-02-20261120-v1'; OUT=ROOT/'artifacts/reports/s5-01-m0-20261123-v1'; OUT.mkdir(parents=True,exist_ok=False)
view='artifacts/reports/s4-02-20261120-v1/all-view.json'; snapshot='data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json'
a=json.loads((BASE/'all-view.json').read_text(encoding='utf-8')); cu=json.loads((BASE/'cu-view.json').read_text(encoding='utf-8')); ledger=json.loads((BASE/'ledger.json').read_text(encoding='utf-8'))['records']; ids=set(a['content']['common_record_ids']); cids=set(cu['content']['common_record_ids']); rows=[r for r in ledger if r['record_id'] in ids]
assert len(ids)==len(rows)==542 and len(cids)==211 and cids<=ids
status=Counter(r['repeat_identity_status'] for r in rows); assert set(status)<= {'no_confirmed_repeat','confirmed_repeat'}
p=prepare(view,snapshot,root=ROOT,seed=45); p.pop('content_sha256'); p.pop('split_id'); p['status']='frozen'; p['content_sha256']=digest(p); p['split_id']='research-split-'+p['content_sha256']; write_json(OUT/'split.json',p)
q=dict(p,dataset_view_id=cu['view_id'],strategy='random_projection'); q.update({k:sorted(set(p[k])&cids) for k in ('train','test')}); q['validation_folds']=[sorted(set(f)&cids) for f in p['validation_folds']]; q['groups']=[sorted(set(g)&cids) for g in p['groups'] if set(g)&cids]; q.pop('content_sha256'); q.pop('split_id'); q['content_sha256']=digest(q); q['split_id']='research-split-'+q['content_sha256']; write_json(OUT/'copper_projection.json',q)
train,test=set(p['train']),set(p['test']); folds=[set(f) for f in p['validation_folds']]; assert train|test==ids and not train&test and set.union(*folds)==train and sum(map(len,folds))==len(train)
for group in p['groups']:
 g=set(group); assert not (g&train and g&test); assert sum(bool(g&f) for f in folds)<=1
assert len(q['train'])>=100 and len(q['test'])>=20 and len([g for g in q['groups'] if set(g)&set(q['train'])])>=5 and len([g for g in q['groups'] if set(g)&set(q['test'])])>=20 and all(q['validation_folds'])
# Read only membership of historical S4 test sets; no historical scores are consumed.
history={}
for file in sorted((ROOT/'artifacts/reports/s4-03-frozen-20261120-v2').glob('*.json')):
 old=json.loads(file.read_text(encoding='utf-8')); h=set(old['test']); history[file.stem]={'historical_test':len(h),'now_train':len(h&train),'now_test':len(h&test)}
config={'schema_version':1,'view':view,'snapshot':snapshot,'split':str((OUT/'split.json').relative_to(ROOT)).replace('\\','/'),'split_sha256':sha(OUT/'split.json'),'target':'co2_conversion','candidates':[{'feature':'F_base','model':'extra_trees','params':{'n_estimators':100,'min_samples_leaf':2,'max_features':1.0,'n_jobs':1}}],'model_seed':42,'metrics':['mae','rmse','availability'],'outputs':['predictions']}; write_json(OUT/'baseline-preflight-config.json',config); checked=preflight(OUT/'baseline-preflight-config.json',root=ROOT)
p2=prepare(view,snapshot,root=ROOT,seed=45); assert all(p[k]==p2[k] for k in ('train','test','validation_folds','groups'))
audit={'identity_status':dict(status),'confirmed_groups':len({r.get('confirmed_repeat_group') for r in rows if r['repeat_identity_status']=='confirmed_repeat'}),'excluded_unresolved':sum(r['repeat_identity_status'] not in ('no_confirmed_repeat','confirmed_repeat') for r in ledger),'counts':{'all_train':len(train),'all_test':len(test),'folds':[len(f) for f in folds],'cu_train':len(q['train']),'cu_test':len(q['test']),'cu_folds':[len(f) for f in q['validation_folds']]},'history_overlap':history,'preflight_counts':checked['counts'],'rebuild_and_identity_isolation':'passed','input_sha256':{view:sha(ROOT/view),snapshot:sha(ROOT/snapshot),'ledger':sha(BASE/'ledger.json')}}
write_json(OUT/'split_audit.json',audit); print(json.dumps(audit,ensure_ascii=False,indent=2))

