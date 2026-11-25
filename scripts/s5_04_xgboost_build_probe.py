"""Synthetic XGBoost package compatibility probe; not a supported candidate or S5 experiment."""
import hashlib,importlib.metadata as md,json,pickle,platform,datetime
from pathlib import Path
import numpy as np, xgboost as xgb
from catalyst_ai.features.pipeline import R1Features
from catalyst_ai.modeling.research_run import environment,load_locked_model,predict_payloads
from catalyst_ai.modeling.research_preflight import ResearchConfig
from catalyst_ai.modeling.s5_selection import predict
root=Path(__file__).resolve().parents[1];out=root/'artifacts/reports/s5-04-xgboost-feasibility-v1'; run=out/'synthetic-package-v1';run.mkdir(exist_ok=False)
def read(p): return json.loads(p.read_text(encoding='utf8'))
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
syn=root/'artifacts/reports/s5-04-remediation-20261124-v1/synthetic-e2e-v2'; snap=read(syn/'snapshot.json'); rows=snap['content']['records'];train=rows[:50];test=rows[50:]; trans=R1Features.fit([r['payload'] for r in train],'F_base'); X=np.array([trans.transform_one(r['payload'])['values'] for r in train]); y=np.array([r['payload']['observations'][0]['value']['normalized_value'] for r in train]);params={'n_estimators':30,'max_depth':2,'learning_rate':0.1,'random_state':42,'n_jobs':1,'tree_method':'hist','device':'cpu'}
models=[xgb.XGBRegressor(**params).fit(X,y) for _ in range(2)]; expected=predict(trans,models[0],test); duplicate=predict(trans,models[1],test);assert expected==duplicate
# Formal training config validation must continue rejecting xgboost.
cfg=read(syn/'config.json');cfg['candidates'].append({'feature':'F_base','model':'xgboost','params':{}})
try: ResearchConfig.model_validate(cfg)
except Exception as e: rejected={'type':type(e).__name__,'message':str(e)}
else:raise AssertionError('Unexpected XGBoost support in frozen config')
write(run/'config.json',{'selection_rule':'s5-paired-v1','purpose':'synthetic handcrafted compatibility probe only; not a valid ResearchConfig or approved training run','estimator':'xgboost-cpu==3.4.1','parameters':params});write(run/'split.json',{'train':[r['record_id'] for r in train],'test':[r['record_id'] for r in test]});write(run/'cross_validation.json',{'performed':False,'purpose':'not a performance comparison'});(run/'run.log').write_text('Hand-assembled synthetic packaging compatibility probe; formal training and model selection not run.\n',encoding='utf8')
package={'model':models[0],'transformer':trans,'packages':[{'candidate_index':0,'model':models[0],'transformer':trans}]};(run/'model.pkl').write_bytes(pickle.dumps(package,protocol=5));models[0].save_model(run/'model.ubj')
lock={'schema_version':1,'environment':environment(),'input_hashes':{'synthetic_snapshot_sha256':sha(syn/'snapshot.json')},'artifacts':{n:sha(run/n) for n in ('config.json','split.json','cross_validation.json','model.pkl','run.log')},'selected_index':0,'test_scored':False,'purpose':'post-review handcrafted synthetic XGBoost packaging compatibility; not a research run'};write(run/'lock.json',lock)
_,loaded=load_locked_model(run);assert predict(loaded['transformer'],loaded['model'],test)==expected
write(out/'expected-predictions.json',expected)
portable=xgb.XGBRegressor();portable.load_model(run/'model.ubj');assert predict(trans,portable,test)==expected
d=md.distribution('xgboost-cpu');records=[]
for f in d.files:
 if f.hash and f.hash.mode=='sha256':
  import base64
  p=Path(d.locate_file(f)); actual=base64.urlsafe_b64encode(hashlib.sha256(p.read_bytes()).digest()).decode().rstrip('='); assert actual==f.hash.value;records.append(str(f))
licensefile=next(f for f in d.files if str(f).endswith('/LICENSE')); (out/'xgboost-LICENSE.txt').write_bytes(Path(d.locate_file(licensefile)).read_bytes())
write(out/'build-result.json',{'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'python':platform.python_version(),'xgboost_cpu':d.version,'wheel_tag':d.read_text('WHEEL'),'license_expression':d.metadata.get('License-Expression'),'requirements':d.requires,'installed_record_files_sha256_verified':len(records),'synthetic_train_records':50,'synthetic_prediction_records':10,'cpu_parameters':params,'repeat_fit_predictions_bitwise_equal':True,'native_ubj_reload_predictions_equal':True,'formal_loader_build_environment':'pass','official_config_xgboost_rejected':rejected,'run_lock_sha256':sha(run/'lock.json'),'model_ubj_sha256':sha(run/'model.ubj'),'package_sha256':sha(run/'model.pkl'),'environment':environment()})
print('CPU repeated fit, native UBJ, official loader passed; official config rejects XGBoost')
