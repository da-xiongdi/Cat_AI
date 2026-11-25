import hashlib,json,datetime
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=root/'artifacts/reports/s5-04-xgboost-feasibility-v1';prior=root/'artifacts/reports/s5-04-remediation-20261124-v1/remediation-manifest-v1.json';orig=root/'artifacts/reports/s5-04-e02-20261124-v1/evidence-sha256-final.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf8'))
for m in (prior,orig):
 bad=[k for k,h in read(m)['files'].items() if not (root/k).is_file() or sha(root/k)!=h];assert not bad,(m,bad)
assert sha(prior)=='a12585f5271d7e7ee27d9ad4776a830d7538315365c9a6f5ad43993d7a214723'
b=read(out/'build-result.json');r=read(out/'release-result.json');w=read(out/'wheel-download.json');d=read(out/'dependency-lock.json')
assert b['repeat_fit_predictions_bitwise_equal'] and b['native_ubj_reload_predictions_equal'] and b['formal_loader_build_environment']=='pass'
assert r['environment_exactly_matches_lock'] and r['predictions_exact_match'] and r['prediction_records']==10 and r['tampered_model_rejected'] and r['lock_sha256']==sha(out/'synthetic-package-v1/lock.json')
assert w['status']=='pass' and w['sha256']==w['pypi_sha256']==d['xgboost_wheel_sha256'] and d['wheel_members_matched_installed']==59
assert b['official_config_xgboost_rejected'] and read(out/'negative-runtime-result.json')['mismatched_original_environment_rejected']
files=[p for p in out.iterdir() if p.is_file()];files += [p for p in (out/'synthetic-package-v1').rglob('*') if p.is_file()];files += [prior,orig,root/'artifacts/reports/s5-04-remediation-20261124-v1/synthetic-e2e-v2/snapshot.json',root/'artifacts/reports/s5-04-remediation-20261124-v1/release-requirements.txt',root/'artifacts/reports/s5-04-e02-20261124-v1/release-wheel/catalyst_ai-0.1.0-py3-none-any.whl'];files += [root/'scripts'/x for x in ('s5_04_xgboost_build_probe.py','s5_04_xgboost_release_probe.py','s5_04_xgboost_dependency_lock.py','s5_04_xgboost_wheel.py','s5_04_xgboost_negative_runtime.py','s5_04_xgboost_freeze.py')]
manifest=out/'evidence-manifest-v2.json';assert not manifest.exists();payload={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'supplemental feasibility evidence; exception decisions pending','algorithm':'sha256','previous_manifest_sha256':sha(prior),'original_manifest_sha256':sha(orig),'previous_entries_verified':len(read(prior)['files']),'original_entries_verified':len(read(orig)['files']),'files':{p.relative_to(root).as_posix():sha(p) for p in sorted(files)}};manifest.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf8');assert all(sha(root/k)==v for k,v in read(manifest)['files'].items());print('files',len(files),'manifest sha256',sha(manifest))
