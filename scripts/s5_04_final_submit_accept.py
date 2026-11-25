"""Register frozen evidence, submit and accept as user-directed workbench actions."""
import hashlib,json,sqlite3
from pathlib import Path
from catalyst_ai.storage.workbench import atomic_operations,transaction
from catalyst_ai.workbench import service,index,backup
root=Path(__file__).resolve().parents[1];out=root/'artifacts/reports/s5-04-final-acceptance-v1';db=root/'data/workbench.sqlite';bak=root/'backups/s5-04-final-acceptance-v1';bak.mkdir(parents=True,exist_ok=False)
files={'S5-04-final-decision-v1':'artifacts/reports/s5-04-final-acceptance-v1/final-acceptance.md','S5-04-final-manifest-v1':'artifacts/reports/s5-04-final-acceptance-v1/final-evidence-manifest.json','S5-04-original-replay-v1':'artifacts/reports/s5-04-final-acceptance-v1/original-replay.json','S5-04-original-path-map-v1':'artifacts/reports/s5-04-final-acceptance-v1/original-evidence-path-map.json','S5-04-original-manifest-91':'artifacts/reports/s5-04-e02-20261124-v1/evidence-sha256-final.json','S5-04-remediation-manifest-v1':'artifacts/reports/s5-04-remediation-20261124-v1/remediation-manifest-v1.json','S5-04-xgboost-feasibility-manifest-v2':'artifacts/reports/s5-04-xgboost-feasibility-v1/evidence-manifest-v2.json','S5-04-xgboost-correction-manifest-v3':'artifacts/reports/s5-04-xgboost-correction-v3/evidence-manifest-v3.json','S5-04-exception-application-v3':'artifacts/reports/s5-04-xgboost-correction-v3/review-exception-v3.md'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify():
 m=json.loads((out/'final-evidence-manifest.json').read_text(encoding='utf8'));assert all((root/p).is_file() and sha(root/p)==h for p,h in m['files'].items());assert m['original_entries_verified_via_original_or_archive']==251
 mapping=json.loads((out/'original-evidence-path-map.json').read_text(encoding='utf8'))['entries'];assert len(mapping)==251 and all(sha(root/x['path'])==x['sha256'] for x in mapping.values())
 for p in ['artifacts/reports/s5-04-remediation-20261124-v1/remediation-manifest-v1.json','artifacts/reports/s5-04-xgboost-feasibility-v1/evidence-manifest-v2.json','artifacts/reports/s5-04-xgboost-correction-v3/evidence-manifest-v3.json']:
  source=json.loads((root/p).read_text(encoding='utf8'));assert all((root/k).is_file() and sha(root/k)==v for k,v in source['files'].items())
 return {k:sha(root/p) for k,p in files.items()}
def auth(x):return {'request_id':'s5-04-final-accept-v1:'+x,'actor':'Codex'}
def execute(target):
 hashes=verify()
 with atomic_operations(target):
  t=service.get_task(target,'S5-04');assert t['status']=='in_progress' and t['revision']==6
  with sqlite3.connect(target) as c:
   assert c.execute("select count(*) from review where id=91 and task_id='S5-04'").fetchone()[0]==1
   assert c.execute("select count(*) from activity where id=698 and task_id='S5-04'").fetchone()[0]==1
  for ident,path in files.items():index.register(target,'cat-ai',ident,'document' if path.endswith('.md') else 'attachment',path,**auth('register:'+ident))
  index.scan(target,'cat-ai',document_ids=list(files))
  criteria=[{'criterion_id':c,'passed':True,'evidence_id':i,'evidence_version':hashes[i],'explanation':e} for c,i,e in [('estimators','S5-04-final-decision-v1','Official XGBoost synthetic fit and independent release verification; historical lock replay; two procedural exceptions approved by user only for S5-04, as recorded.'),('benchmark','S5-04-remediation-manifest-v1','Frozen OOF DOI strata, holdout denominators and paper-equal MAE, supplemental per-arm timing and original predictions are bound by the manifest.'),('search','S5-04-xgboost-correction-manifest-v3','Original frozen selection and strict common metrics remain unchanged; post-review XGBoost validation is not a research comparison; final manifest binds original replay and exception decision.')]]
  sub=service.submit_review(target,'S5-04',t['revision'],criteria,'用户批准 S5-04 两项限定范围事前程序例外；原记录和冻结选模规则保持，事后 XGBoost 验证不进入原科研结论。',**auth('submit'));assert sub['status']=='in_review'
  accepted=service.accept_review(target,'S5-04',sub['revision'],'按用户明确指令完成审核：两项事前凭证缺口按 S5-04 限定例外处理，证据链及历史源码重放已核验；原留出复用和相关性限制保留。',**auth('accept'));assert accepted['status']=='done';assert verify()==hashes
 with sqlite3.connect(target) as c:
  assert c.execute('pragma quick_check').fetchone()[0]=='ok' and not c.execute('pragma foreign_key_check').fetchall()
 return {'submission':sub,'acceptance':accepted}
backup.backup_database(db,bak/'before.sqlite');backup.backup_database(bak/'before.sqlite',bak/'rehearsal.sqlite')
print('rehearsal',execute(bak/'rehearsal.sqlite'),flush=True)
print('formal',execute(db),flush=True)
with transaction(db) as conn:
 row=conn.execute("select * from task where id='S5-05'").fetchone();assert row['status']=='planned'
 try:service._ready(conn,row);readiness={'ready_conditions_met':True,'reason':None}
 except service.Conflict as e:readiness={'ready_conditions_met':False,'reason':str(e)}
 deps=[dict(r) for r in conn.execute("select t.id,t.status from task t join dependency d on d.prerequisite_id=t.id where d.task_id='S5-05' order by t.id")];print('S5-05',row['status'],readiness,'dependencies',deps,flush=True)
