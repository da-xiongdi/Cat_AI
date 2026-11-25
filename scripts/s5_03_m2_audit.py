import json, collections, math
from pathlib import Path
from catalyst_ai.features.pipeline import project
from catalyst_ai.features.copper import descriptors
from catalyst_ai.storage.feature_catalog import get_catalog
from catalyst_ai.modeling.research_run import load_locked_model
from catalyst_ai.modeling.s5_selection import predict
P=Path('artifacts/reports/s5-03-start-20261124'); out=Path('artifacts/reports/s5-03-m2-audit-20261124'); out.mkdir(parents=True,exist_ok=False)
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
view=read('artifacts/reports/s4-02-20261120-v1/cu-view.json'); ids=set(view['content']['common_record_ids']); ledger={r['record_id']:r for r in read('artifacts/reports/s4-02-20261120-v1/ledger.json')['records']}; snap=read('data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json'); records={r['record_id']:r for r in snap['content']['records']}; binding=read('artifacts/reports/s1-b-20261113-v4/selection.json')['content']['binding']; cat=get_catalog(Path('data/catalog.sqlite'),'species',binding['mapping_version']); assert cat['sha256']==binding['mapping_sha256']; mapping={r['species']:r for r in cat['catalog']['entries']}
rowdata={}
for i in sorted(ids):
 r=records[i]; p=r['payload']; z=project(p); d=descriptors(p,cat); comp=[]; cent={role:collections.Counter() for role in ('compound','support')}
 for (role,name),amount in z['amounts'].items():
  if amount<=0: continue
  ent=mapping[name]; assert ent['state']=='supported'; assert ent.get('evidence') and ent.get('formula_unit_basis'); comp.append({'role':role,'species':name,'material_mol_pct':amount,'centers':ent['centers'],'mapping_evidence':ent['evidence'],'formula_unit_basis':ent['formula_unit_basis']})
  for element,n in ent['centers'].items(): cent[role][element]+=amount*n
 reasons={}
 for role,label in [('compound','reported_active'),('support','reported_support')]:
  for el in ('Zn','Zr','Al'):
   key=label+'_cu_'+el.lower()+'_ratio'; cu=cent[role]['Cu']; denom=cent[role][el]; v=d[key]; assert (v is not None)==(cu>0 and denom>0)
   reasons[key]='available_same_role' if v is not None else ('no_cu_in_role' if cu<=0 else 'no_positive_denominator_in_role')
 rowdata[i]={'record_id':i,'doi':p['source']['doi'],'source_locator':r['input_locator'],'source_extraction_status':p['extraction']['status'],'ledger':ledger[i],'components':comp,'nominal_center_weights':{k:dict(v) for k,v in cent.items()},'descriptors':d,'ratio_status':reasons,'conditions':z['conditions']}
assert len(rowdata)==211
(out/'material_records.json').write_text(json.dumps({'catalog_sha256':cat['sha256'],'records':rowdata},indent=2,ensure_ascii=False),encoding='utf-8')
summary={}; reload={}
for seed in (45,46,47):
 proj=read('artifacts/reports/s5-01-m0-20261123-v1/copper_projection.json' if seed==45 else P/f'projection-{seed}.json'); allsplit=read(P/f'a-{seed}/split.json'); tr=set(proj['train']); te=set(proj['test']); folds=[set(f) for f in proj['validation_folds']]; assert tr|te==ids and not tr&te and tr==set(allsplit['train'])&ids and te==set(allsplit['test'])&ids; assert all(f==set(allsplit['validation_folds'][j])&ids for j,f in enumerate(folds)); assert all(not(set(g)&set(allsplit['train']) and set(g)&set(allsplit['test'])) and sum(bool(set(g)&set(f)) for f in allsplit['validation_folds'])<=1 for g in allsplit['groups'])
 partitions={'all':ids,'train':tr,'test':te,**{f'fold_{j}':f for j,f in enumerate(folds)}}; summary[str(seed)]={}
 for name,group in partitions.items():
  rs=[rowdata[i] for i in group]; counts={k:sum(r['descriptors'][k] is not None for r in rs) for k in next(iter(rowdata.values()))['descriptors']}; temps=[r['conditions']['temperature_k'] for r in rs]; doi=collections.Counter(r['doi'] for r in rs); cond={k:{'min':min(r['conditions'][k] for r in rs),'max':max(r['conditions'][k] for r in rs)} for k in rs[0]['conditions']}; summary[str(seed)][name]={'n':len(rs),'doi_n':len(doi),'doi_counts':dict(doi),'descriptors_applicable':counts,'ratio_status':{key:dict(collections.Counter(r['ratio_status'][key] for r in rs)) for key in rs[0]['ratio_status']},'conditions':cond,'temperature_gt_553':sum(x>553 for x in temps),'temperature_eq_553':sum(x==553 for x in temps),'allocation_groups':sum(bool(set(g)&group) for g in proj['groups'])}
 assert len(tr)>=100 and len(te)>=20 and summary[str(seed)]['train']['allocation_groups']>=5 and summary[str(seed)]['test']['allocation_groups']>=20 and all(folds)
 for prefix in ('a','b-select','b2'):
  run=P/f'{prefix}-{seed}'; lock,pkg=load_locked_model(run); arms=read(run/'holdout/all_arms.json'); counts=[]
  for j,arm in enumerate(arms):
   old=arm['predictions']; now=predict(pkg['packages'][j]['transformer'],pkg['packages'][j]['model'],[records[r['record_id']] for r in old]);
   for before,after in zip(old,now,strict=True):
    b={k:v for k,v in before.items() if k not in ('record_id','doi','observed')}; assert b==json.loads(json.dumps(after)), (seed,prefix,j,before['record_id'])
   counts.append(len(old))
  reload[f'{prefix}-{seed}']={'arm_records':counts,'lock_verified':True}
(out/'partition_audit.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8'); (out/'full_reload.json').write_text(json.dumps(reload,indent=2),encoding='utf-8'); print(json.dumps({'sizes':{s:{k:{x:v[x] for x in ('n','allocation_groups','temperature_gt_553','temperature_eq_553')} for k,v in d.items() if k in ('train','test')} for s,d in summary.items()},'reload':reload},indent=2))
