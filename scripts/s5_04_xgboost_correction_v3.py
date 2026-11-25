"""Record current XGBoost integration evidence; preserve prior immutable manifests."""
import datetime,hashlib,json,subprocess,sys,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=root/'artifacts/reports/s5-04-xgboost-correction-v3';out.mkdir(exist_ok=False)
old=root/'artifacts/reports/s5-04-e02-20261124-v1/evidence-sha256-final.json'; prior=root/'artifacts/reports/s5-04-xgboost-feasibility-v1/evidence-manifest-v2.json'; official=root/'artifacts/reports/s5-04-xgboost-official-20261124-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf8'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
checks={}
for f in [old,root/'artifacts/reports/s5-04-remediation-20261124-v1/remediation-manifest-v1.json',prior]:
 data=read(f)['files'];bad={p:{'expected':h,'actual':sha(root/p) if (root/p).is_file() else None} for p,h in data.items() if not (root/p).is_file() or sha(root/p)!=h};checks[f.relative_to(root).as_posix()]={'manifest_sha256':sha(f),'file_count':len(data),'mismatches':bad}
release=read(official/'synthetic/release-result.json');syn=read(official/'synthetic/result.json');assert release['formal_lock_match'] and release['arms']==2 and release['predictions_per_arm']==[10,10] and syn['formal_loader']=='pass'
wheel=official/'dist/catalyst_ai-0.1.0-py3-none-any.whl';diff=[]
with zipfile.ZipFile(wheel) as z:
 for n in z.namelist():
  if n.startswith('catalyst_ai/') and n.endswith('.py'):
   p=root/'src'/n
   if not p.is_file() or hashlib.sha256(z.read(n)).digest()!=hashlib.sha256(p.read_bytes()).digest():diff.append(n)
assert not diff
proc=subprocess.run([str(root/'.venv-xgb-release/Scripts/python.exe'),'-m','pytest','-q','tests/unit/test_s5_xgboost.py','tests/unit/test_s5_estimators.py','tests/unit/test_s5_metrics.py','tests/unit/test_s5_selection.py'],cwd=root,capture_output=True,text=True,encoding='utf8',timeout=120)
(out/'tests.log').write_text(proc.stdout+'\n'+proc.stderr,encoding='utf8');assert proc.returncode==0
write(out/'verification.json',{'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'historical_manifest_checks':checks,'current_source_matches_official_wheel':True,'official_wheel_sha256':sha(wheel),'synthetic_formal_result':syn,'independent_release_result':release,'partition_validation':read(official/'partition-validation/verification.json'),'pytest_exit_code':proc.returncode,'pytest_log_sha256':sha(out/'tests.log')})
print('verified; historical original mismatches',len(next(iter(checks.values()))['mismatches']),'tests',proc.stdout.strip())
