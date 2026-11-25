import subprocess,json,datetime,time
from pathlib import Path
p=Path('artifacts/reports/s5-04-remediation-20261124-v1/xgboost-attempt-v1');p.mkdir(exist_ok=False)
cmd=['uv','pip','install','--python','artifacts/reports/s5-04-remediation-20261124-v1/xgb-env/Scripts/python.exe','xgboost','numpy==2.5.4','scipy==1.18.1'];start=datetime.datetime.now(datetime.timezone.utc).isoformat();t=time.monotonic()
try:
 r=subprocess.run(cmd,capture_output=True,timeout=75); code=r.returncode; stdout=r.stdout;stderr=r.stderr; status='completed'
except subprocess.TimeoutExpired as e:
 code=None;stdout=e.stdout or b'';stderr=e.stderr or b'';status='timeout_75_seconds'
(p/'install.stdout.log').write_bytes(stdout);(p/'install.stderr.log').write_bytes(stderr);(p/'attempt.json').write_text(json.dumps({'command':cmd,'started_utc':start,'ended_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'duration_seconds':time.monotonic()-t,'status':status,'exit_code':code,'scope':'post-review packaging feasibility only; not algorithm performance'},indent=2)+'\n',encoding='utf8');print(status,code,flush=True)
