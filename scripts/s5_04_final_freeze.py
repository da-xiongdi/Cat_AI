"""Verify S5-04 chain and freeze new acceptance evidence; never rewrite prior manifests."""
import hashlib,json,datetime
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=root/'artifacts/reports/s5-04-final-acceptance-v1';old=root/'artifacts/reports/s5-04-e02-20261124-v1/evidence-sha256-final.json';manifest=out/'final-evidence-manifest.json';assert not manifest.exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf8'))
prior=[root/'artifacts/reports/s5-04-remediation-20261124-v1/remediation-manifest-v1.json',root/'artifacts/reports/s5-04-xgboost-feasibility-v1/evidence-manifest-v2.json',root/'artifacts/reports/s5-04-xgboost-correction-v3/evidence-manifest-v3.json']; assert sha(old)=='edc12f8da675b418cbaeeb1aaf9f1ce188c0ce72f50e381e1a4ead7997a11c81'
for p in prior:
 bad=[k for k,v in read(p)['files'].items() if not (root/k).is_file() or sha(root/k)!=v];assert not bad,(p,bad)
archive=out/'original-source';mapping={};bad=[]
for k,v in read(old)['files'].items():
 active=root/k
 if active.is_file() and sha(active)==v:mapping[k]={'path':k,'sha256':v}
 elif (archive/k).is_file() and sha(archive/k)==v:mapping[k]={'path':(archive/k).relative_to(root).as_posix(),'sha256':v}
 else:bad.append(k)
assert not bad,bad;assert len(mapping)==251
replay=read(out/'original-replay.json'); assert len(replay['runs'])==6 and sum(r['arms'] for r in replay['runs'].values())==48 and sum(r['records'] for r in replay['runs'].values())==5184
(out/'original-evidence-path-map.json').write_text(json.dumps({'original_manifest_sha256':sha(old),'entries':mapping},indent=2)+'\n',encoding='utf8')
files=[p for p in out.rglob('*') if p.is_file() and p!=manifest];files+=prior+[old,root/'artifacts/reports/s5-04-xgboost-correction-v3/review-exception-v3.md',root/'scripts/s5_04_final_replay.py',root/'scripts/s5_04_final_freeze.py']
obj={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'algorithm':'sha256','purpose':'S5-04 final acceptance with two user-approved limited exceptions','original_entries_verified_via_original_or_archive':len(mapping),'previous_manifests_verified':len(prior),'files':{p.relative_to(root).as_posix():sha(p) for p in sorted(set(files))}};manifest.write_text(json.dumps(obj,indent=2)+'\n',encoding='utf8');assert all(sha(root/k)==v for k,v in read(manifest)['files'].items());print('original entries verified',len(mapping),'final files',len(obj['files']),'manifest sha256',sha(manifest))
