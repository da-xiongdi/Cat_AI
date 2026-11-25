"""Freeze and verify supplemental S5-04 evidence without changing the original submission."""
import hashlib,json,datetime
from pathlib import Path
root=Path(__file__).resolve().parents[1]; out=root/'artifacts/reports/s5-04-remediation-20261124-v1'; old=root/'artifacts/reports/s5-04-e02-20261124-v1'; manifest=out/'remediation-manifest-v1.json'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert not manifest.exists()
prior=read(old/'evidence-sha256-final.json')['files'];bad=[name for name,h in prior.items() if not (root/name).is_file() or sha(root/name)!=h];assert not bad,bad
release=read(out/'formal-release-verification.json');assert len(release['runs'])==6 and sum(x['arms'] for x in release['runs'].values())==48 and sum(x['records'] for x in release['runs'].values())==5184
completion=read(out/'timing-v1/completion.json'); timings=read(out/'timing-v1/timings.json');assert completion['arms']==48 and len(timings)==6 and all(x['reproduces_saved_predictions'] for r in timings.values() for x in r);assert completion['timings_sha256']==sha(out/'timing-v1/timings.json') and completion['run_lock_sha256']==sha(out/'timing-v1/run-lock.json')
syn=read(out/'synthetic-e2e-v2/result.json'); assert syn['formal_loader']=='pass' and syn['holdout_arms']==3 and syn['run_lock_sha256']==sha(out/'synthetic-e2e-v2/run/lock.json')
assert read(out/'xgboost-attempt-v1/attempt.json')['status']=='timeout_75_seconds'
assert '9 passed' in (out/'regression-tests-v1.log').read_text(encoding='utf8')
files=[out/name for name in ('review-and-exception-v1.md','formal-release-verification.json','release-requirements.txt','recomputed-report.json','provenance-final.json','regression-tests-v1.log')]
for folder in ('timing-v1','xgboost-attempt-v1','synthetic-e2e-v2'):files += [p for p in (out/folder).rglob('*') if p.is_file()]
files += [old/'evidence-sha256-final.json',root/'docs/s5_04_execution.md',root/'docs/s5_evaluation_metrics_supplement_v1.md']
files += [root/'scripts'/f for f in ('s5_04_remediation_metrics.py','s5_04_remediation_release.py','s5_04_remediation_timing.py','s5_04_xgb_attempt.py','s5_04_synthetic_e2e.py','s5_04_provenance.py','s5_04_freeze_remediation.py')]
obj={'schema_version':1,'purpose':'supplemental evidence and pending exception decision; not acceptance','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'algorithm':'sha256','original_manifest_sha256':sha(old/'evidence-sha256-final.json'),'original_entries_verified':len(prior),'files':{p.relative_to(root).as_posix():sha(p) for p in sorted(files)}}
manifest.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
assert all(sha(root/p)==h for p,h in read(manifest)['files'].items()); print('frozen',len(files),'files; manifest sha256',sha(manifest))
