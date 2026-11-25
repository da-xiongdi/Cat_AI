import hashlib,json,datetime
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=root/'artifacts/reports/s5-04-xgboost-correction-v3';official=root/'artifacts/reports/s5-04-xgboost-official-20261124-v1';manifest=out/'evidence-manifest-v3.json';assert not manifest.exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
files=[p for p in official.rglob('*') if p.is_file() and p.name!='.gitignore'];files += [out/'review-exception-v3.md',out/'verification.json',out/'tests.log',root/'artifacts/reports/s5-04-xgboost-feasibility-v1/evidence-manifest-v2.json',root/'artifacts/reports/s5-04-remediation-20261124-v1/remediation-manifest-v1.json',root/'artifacts/reports/s5-04-e02-20261124-v1/evidence-sha256-final.json',root/'pyproject.toml',root/'uv.lock']
files += [root/'src/catalyst_ai/modeling'/n for n in ('config.py','research_preflight.py','research_run.py','research_training.py')]
files += [root/'scripts'/n for n in ('s5_04_xgboost_correction_v3.py','s5_04_xgboost_official_synthetic.py','s5_04_xgboost_official_release.py','s5_04_xgboost_partition_verify.py','s5_04_xgboost_correction_freeze_v3.py')]
files += [root/'tests/unit'/n for n in ('test_s5_xgboost.py','test_s5_estimators.py','test_s5_metrics.py','test_s5_selection.py')]
files=sorted(set(files));obj={'algorithm':'sha256','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'purpose':'correct prior report and preserve supplemental verification; pending exception decision','files':{p.relative_to(root).as_posix():sha(p) for p in files}};manifest.write_text(json.dumps(obj,indent=2)+'\n',encoding='utf8');assert all(sha(root/p)==h for p,h in json.loads(manifest.read_text(encoding='utf8'))['files'].items());print(len(files),sha(manifest))
