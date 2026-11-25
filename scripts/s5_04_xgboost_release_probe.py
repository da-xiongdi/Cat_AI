"""Independently load and verify the synthetic XGBoost probe with the real loader."""
import hashlib,json,shutil,tempfile,datetime
from pathlib import Path
import catalyst_ai,xgboost
from catalyst_ai.modeling.research_run import environment,load_locked_model,predict_payloads
root=Path(__file__).resolve().parents[1];out=root/'artifacts/reports/s5-04-xgboost-feasibility-v1';run=out/'synthetic-package-v1';syn=root/'artifacts/reports/s5-04-remediation-20261124-v1/synthetic-e2e-v2'
def read(p):return json.loads(p.read_text(encoding='utf8'))
assert 'site-packages' in str(Path(catalyst_ai.__file__).resolve()); lock,pkg=load_locked_model(run);rows=read(syn/'snapshot.json')['content']['records'][50:]; expected=read(out/'expected-predictions.json');actual=predict_payloads(run,[r['payload'] for r in rows])['predictions'];assert actual==expected
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'tampered';shutil.copytree(run,p);(p/'model.pkl').write_bytes((p/'model.pkl').read_bytes()+b'tamper')
 try:load_locked_model(p)
 except ValueError as e: assert 'locked artifact mismatch' in str(e);tamper=str(e)
 else: raise AssertionError('tamper was not rejected')
result={'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'installed_catalyst_ai':str(catalyst_ai.__file__),'installed_xgboost':str(xgboost.__file__),'environment_exactly_matches_lock':environment()==lock['environment'],'formal_load_locked_model':'pass','formal_predict_payloads':'pass','prediction_records':len(actual),'predictions_exact_match':True,'tampered_model_rejected':tamper,'lock_sha256':hashlib.sha256((run/'lock.json').read_bytes()).hexdigest()}
(out/'release-result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');print(json.dumps(result,indent=2))
