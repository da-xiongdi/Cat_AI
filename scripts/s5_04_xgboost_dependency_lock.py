import hashlib,importlib.metadata as md,json,zipfile,datetime,sys
from pathlib import Path
from catalyst_ai.modeling.research_run import environment
root=Path(__file__).resolve().parents[1];out=root/'artifacts/reports/s5-04-xgboost-feasibility-v1';wheel=out/'xgboost_cpu-3.4.1-py3-none-win_amd64.whl';dist=md.distribution('xgboost-cpu');matched=0
with zipfile.ZipFile(wheel) as z:
 for name in z.namelist():
  if name.endswith('/') or name.endswith('/RECORD'):continue
  p=Path(dist.locate_file(name));assert p.is_file(),name;assert hashlib.sha256(p.read_bytes()).digest()==hashlib.sha256(z.read(name)).digest(),name;matched+=1
records={}
for d in md.distributions():
 name=d.metadata['Name']; raw=d.read_text('RECORD');records[name]={'version':d.version,'record_sha256':hashlib.sha256(raw.encode()).hexdigest() if raw is not None else None}
obj={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'purpose':'isolated XGBoost feasibility runtime, not original S5 training lock','environment':environment(),'distributions_record_sha256':records,'xgboost_wheel_sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),'wheel_members_matched_installed':matched,'catalyst_wheel_sha256':hashlib.sha256((root/'artifacts/reports/s5-04-e02-20261124-v1/release-wheel/catalyst_ai-0.1.0-py3-none-any.whl').read_bytes()).hexdigest(),'reconstruction':'offline mirror cache xgboost-cpu==3.4.1 plus original release-requirements.txt and original catalyst wheel; exact environment and RECORD hashes are recorded'}
(out/'dependency-lock.json').write_text(json.dumps(obj,indent=2)+'\n',encoding='utf8');print('wheel files matched',matched,'distributions',len(records))
