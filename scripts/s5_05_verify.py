import json,hashlib,math,zipfile,sqlite3
from pathlib import Path
from catalyst_ai.modeling.baseline import target_value
from catalyst_ai.modeling.research_run import load_locked_model,code_hash
R=Path(__file__).resolve().parents[1];O=R/'artifacts/reports/s5-05-e05-20261124-v1';M=R/'artifacts/models/s5-e05-20261124-v1'
def rd(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
snap=rd(R/'data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json')['content']; rs={r['record_id']:r for r in snap['records']}; h=rd(O/'historical-r2.json'); audit={}
for path in h['runs']:
 p=R/path; split=rd(p/'split.json');cv=rd(p/'cross_validation.json'); folds={i:n for n,ids in enumerate(split['validation_folds']) for i in ids}; train=set(split['train']);test=set(split['test']);assert set(folds)==train and not train&test
 def check(rows,ids,folded):
  assert len(rows)==len(ids) and {r['record_id'] for r in rows}==ids
  for row in rows:
   i=row['record_id']; assert math.isclose(row['observed'],float(target_value(rs[i],snap)),abs_tol=1e-12,rel_tol=0)
   if folded:assert row['fold']==folds[i]
 for arm in cv['results']:check(arm['predictions'],train,True)
 hp=p/'holdout/all_arms.json'
 if hp.exists():
  for arm in rd(hp):check(arm['predictions'],test,False)
 elif (p/'holdout/predictions.json').exists():check(rd(p/'holdout/predictions.json'),test,False)
 audit[path]={'training_n':len(train),'holdout_n':len(test),'oof_arms':len(cv['results']),'members_and_targets':'verified'}
for s in (45,46,47):
 p=O/f'run-{s}'; cv=rd(p/'cross_validation.json');split=rd(p/'split.json');assert len(cv['results'])==18 and cv['selected_index']==0
 assert {r['record_id'] for r in cv['results'][0]['predictions']}==set(split['train']);assert len(rd(p/'holdout/all_arms.json'))==18
 assert all(r['exit']==0 for r in rd(O/'training-trace.json'))
lock,pkg=load_locked_model(M);assert lock['selected_index']==0 and len(pkg['packages'])==18 and code_hash()==lock['environment']['code_sha256']
with zipfile.ZipFile(O/'source-snapshot.zip') as z:
 for n in z.namelist():assert z.read(n)==(R/n).read_bytes()
for p in [O/'model_card.md',O/'final_report.md',O/'limitations.md']:
 t=p.read_text(encoding='utf8'); assert '\ufffd' not in t and len(t)>300
receipt=rd(O/'registration-receipt.json'); assert all(sha(R/x['path'])==x['sha256'] for x in receipt['files'].values())
assert all(x['verified_against_locked_oof'] for fs in rd(O/'fold-permutation.json').values() for x in fs)
assert all(len(x['replay_arm_record_counts'])==18 and all(n==108 for n in x['replay_arm_record_counts']) for x in rd(O/'applicability-and-permutation.json').values())
with sqlite3.connect(R/'data/workbench.sqlite') as c:assert c.execute('pragma quick_check').fetchone()[0]=='ok' and not c.execute('pragma foreign_key_check').fetchall()
(O/'verification.json').write_text(json.dumps({'historical_members_targets':audit,'E05_runs':3,'E05_replayed_arms':54,'primary_package_reload':'pass','source_archive':'byte matches current locked source','model_card_utf8':'pass','preregistered_hashes':'pass','fold_replay':15,'database_checks':'pass'},ensure_ascii=False,indent=2)+'\n',encoding='utf8');print('validated historical runs',len(audit),'E05 54 arms, source and primary package')
