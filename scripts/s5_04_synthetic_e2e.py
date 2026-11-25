"""Post-review synthetic-only real preflight/fit/lock/load/score supplement."""
import json,copy,datetime
from pathlib import Path
from catalyst_ai.reporting.evidence import digest
from catalyst_ai.modeling.research_preflight import preflight,sha
from catalyst_ai.modeling.research_run import fit,score,load_locked_model
root=Path(__file__).resolve().parents[1]; out=root/'artifacts/reports/s5-04-remediation-20261124-v1/synthetic-e2e-v2';out.mkdir(exist_ok=False)
def write(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def read(p):return json.loads(p.read_text(encoding='utf8'))
def m(n,u):return {'state':'reported','normalized_value':n,'normalized_unit':u}
records=[]
for i in range(60):
 payload={'dataset_kind':'synthetic_demo','source':{'doi':f'10.9999/synthetic{i//3}'},'recipe':{'composition_basis':'mol_pct','composition_scope':'whole','components':[{'species':'Cu','role':'element','amount':m(40.0+i%5,'%')},{'species':'ZnO','role':'support','amount':m(60.0-i%5,'%')}]},'test':{'temperature':m(500.0+i%7,'K'),'pressure':m(20.0+i%3,'bar(abs)'),'pressure_type':'absolute','reactant_ratio':{'numerator':'H2','denominator':'CO2','value':m(3.0,'1')},'mass_normalized_volume_flow':{'mass_basis':'catalyst','gas_scope':'reactants_only','reference_temperature':m(293.15,'K'),'reference_pressure':m(1.01325,'bar(abs)'),'reference_pressure_type':'absolute','value':m(100.0+i%4,'NL/g_cat/h')}},'observations':[{'metric':'co2_conversion','value':{**m(float(10+i%11),'%'),'definition':'synthetic target'}}]}
 records.append({'record_id':f'synthetic-{i:03}','payload':payload})
content={'dataset_kind':'synthetic_demo','scientific_use':False,'target':'co2_conversion','target_unit':'%','target_definition':'synthetic target','records':records}; h=digest(content); snapshot={'snapshot_id':'synthetic-'+h,'content_sha256':h,'content':content};write(out/'snapshot.json',snapshot)
selection=read(root/'artifacts/reports/s1-b-20261113-v4/selection.json'); selection['content']['binding']['snapshot_id']=snapshot['snapshot_id'];selection['content']['binding']['snapshot_sha256']=h;selection['content_sha256']=digest(selection['content']);selection['selection_id']='selection-'+selection['content_sha256'];write(out/'selection.json',selection)
ids=[r['record_id'] for r in records];ledger={'records':[{'record_id':i,'repeat_identity_status':'no_confirmed_repeat'} for i in ids]};write(out/'ledger.json',ledger);write(out/'distributions.json',{'synthetic':True})
binding={'sources':{(out/'selection.json').as_posix():sha(out/'selection.json')},'parent_snapshot_id':snapshot['snapshot_id'],'parent_content_sha256':h,'selection_id':selection['selection_id']};vc={'binding':binding,'common_record_ids':ids,'target_record_ids':ids,'ledger_sha256':sha(out/'ledger.json'),'distributions_sha256':sha(out/'distributions.json')};vh=digest(vc);view={'content':vc,'content_sha256':vh,'view_id':'synthetic-view-'+vh};write(out/'view.json',view)
train=ids[:50];test=ids[50:];split={'dataset_view_id':view['view_id'],'strategy':'random','train':train,'test':test,'folds':5,'validation_folds':[train[k::5] for k in range(5)]};write(out/'split.json',split)
config=read(root/'artifacts/reports/s5-04-e02-20261124-v1/fixed-45/config.json');config.update(view=str(out/'view.json'),snapshot=str(out/'snapshot.json'),split=str(out/'split.json'),split_sha256=sha(out/'split.json'),candidates=config['candidates'][:3]);write(out/'config.json',config)
checked=preflight(out/'config.json',root=root);lock=fit(out/'config.json',out/'run',root=root);loaded,pkg=load_locked_model(out/'run');assert loaded==lock and len(pkg['packages'])==3
score(out/'run',root=root); arms=read(out/'run/holdout/all_arms.json');assert len(arms)==3 and all(len(a['predictions'])==10 for a in arms)
write(out/'result.json',{'purpose':'post-review synthetic software validation only; not historical evidence or scientific evaluation','completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'preflight':checked['counts'],'models':[c['model'] for c in config['candidates']],'formal_loader':'pass','holdout_arms':len(arms),'records_per_arm':10,'run_lock_sha256':sha(out/'run/lock.json')})
print('Synthetic formal preflight fit lock load score passed',flush=True)

