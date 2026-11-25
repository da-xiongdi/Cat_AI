import hashlib,json,sqlite3
from pathlib import Path
from catalyst_ai.storage.workbench import atomic_operations
from catalyst_ai.workbench import backup,index,model_runs,plans,service
R=Path(__file__).resolve().parents[1];O=R/'artifacts/reports/s5-05-e05-20261124-v1';M=R/'artifacts/models/s5-e05-20261124-v1';DB=R/'data/workbench.sqlite';MAN=O/'evidence-sha256.json';B=R/'backups/s5-05-m3-20261124-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def auth(k):return {'request_id':'s5-05-m3-v1:'+k,'actor':'Codex'}
FILES={'S5-05-M3-report-v1':O/'final_report.md','S5-05-M3-model-card-v1':O/'model_card.md','S5-05-M3-limitations-v1':O/'limitations.md','S5-05-M3-evidence-v1':MAN,'S5-05-M3-metrics-v1':O/'metrics.json','S5-05-M3-historical-r2-v1':O/'historical-r2.json','S5-05-M3-domain-v1':O/'applicability-and-permutation.json','S5-05-M3-fold-permutation-v1':O/'fold-permutation.json','S5-05-M3-verify-v1':O/'verification.json'}
for seed in (45,46,47):FILES[f'S5-05-M3-run-{seed}-lock-v1']=O/f'run-{seed}/lock.json'
def freeze():
 assert not MAN.exists()
 v=read(O/'verification.json');assert len(v['historical_members_targets'])==30 and v['E05_replayed_arms']==54 and v['fold_replay']==15
 files=[p for p in O.rglob('*') if p.is_file() and p.suffix!='.sqlite']+ [p for p in M.rglob('*') if p.is_file()]
 files += [R/p for p in ['docs/s5_05_execution.md','docs/s5_05_research_decision_v1.md','docs/s5_05_diagnostics_supplement_v1.md','docs/s5_implementation_plan.md','docs/s5_evaluation_metrics_supplement_v1.md','scripts/s5_05_start.py','scripts/s5_05_e05.py','scripts/s5_05_metrics.py','scripts/s5_05_diagnostics.py','scripts/s5_05_fold_permutation.py','scripts/s5_05_register_diagnostics.py','scripts/s5_05_prepare_report.py','scripts/s5_05_verify.py','scripts/s5_05_submit.py','data/catalog.sqlite','data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json','artifacts/reports/s4-02-20261120-v1/all-view.json','artifacts/reports/s4-02-20261120-v1/ledger.json','artifacts/reports/s4-02-20261120-v1/distributions.json','artifacts/reports/s1-b-20261113-v4/selection.json','artifacts/reports/s5-01-m0-20261123-v2/protocol.md','artifacts/reports/s5-03-m2-audit-20261124/report.md','artifacts/reports/s5-03-m2-audit-20261124/evidence-sha256.json','artifacts/reports/s5-04-final-acceptance-v1/final-acceptance.md','artifacts/reports/s5-04-final-acceptance-v1/final-evidence-manifest.json','artifacts/reports/s5-04-xgboost-official-20261124-v1/synthetic/result.json','artifacts/reports/s5-04-xgboost-official-20261124-v1/synthetic/release-result.json','artifacts/reports/s5-04-xgboost-official-20261124-v1/partition-validation/verification.json','artifacts/reports/s5-02-e01-20261124-v1/feature_importance.json','artifacts/reports/s5-03-start-20261124/paired_metrics.json']]
 for path in v['historical_members_targets']:
  p=R/path
  for rel in ('lock.json','config.json','split.json','cross_validation.json','holdout/all_arms.json','holdout/predictions.json'):
   if (p/rel).is_file():files.append(p/rel)
 files=set(files);assert all(p.is_file() for p in files)
 MAN.write_text(json.dumps({'algorithm':'sha256','files':{p.relative_to(R).as_posix():sha(p) for p in sorted(files)}},ensure_ascii=False,indent=2)+'\n',encoding='utf8'); print('frozen',len(files),flush=True)
def verify():
 manifest=read(MAN);bad=[p for p,h in manifest['files'].items() if not (R/p).is_file() or sha(R/p)!=h];assert not bad,bad
 return {k:sha(p) for k,p in FILES.items()}
def submit(db):
 hashes=verify()
 with atomic_operations(db):
  task=service.get_task(db,'S5-05');assert task['status']=='in_progress'
  for key,p in FILES.items():index.register(db,'cat-ai',key,'document' if p.suffix=='.md' else 'attachment',p.relative_to(R).as_posix(),**auth('register:'+key))
  index.scan(db,'cat-ai',document_ids=list(FILES))
  ref=plans.save_task_plan_reference(db,'cat-ai','S5-05-M3-report-reference-v1',{'task_id':'S5-05','document_id':'S5-05-M3-report-v1','path':(O/'final_report.md').relative_to(R).as_posix(),'section_locator':'S5-05 综合模型评价与收口报告 v1','purpose':'acceptance','is_primary':0},0,'登记综合评价验收报告',**auth('reference'))
  plans.verify_task_plan_reference(db,'cat-ai','S5-05-M3-report-reference-v1',ref['revision'],hashes['S5-05-M3-report-v1'],**auth('verify-reference'))
  assert plans.inspect_task_plan_reference(db,'cat-ai','S5-05-primary-plan')['status']=='valid'
  for seed in (45,46,47):
   key=f'S5-05-M3-run-{seed}-lock-v1';model_runs.save(db,'cat-ai',f'S5-05-E05-{seed}-v1',{'title':f'S5-E05 seed {seed}','task_id':'S5-05','execution_status':'succeeded','research_status':'unreviewed','target':'CO2 conversion','unit':'%','dataset':f'S5 frozen all-system seed {seed}','feature_version':'F_base and training-selected F3-P','algorithm':'Extra Trees, random forest, XGBoost','configuration':'18 arms; 3 parameter sets per algorithm per feature; five folds; model seed 42','evaluation_scope':'Previously observed internal holdout; training-only paired MAE selection','conclusion':'Baseline selected under training-side tie rule.','limitations':'Internal exploratory evaluation; overlapping seeds; no independent external validation.','evidence':[{'id':key,'version':hashes[key],'role':'model'},{'id':'S5-05-M3-report-v1','version':hashes['S5-05-M3-report-v1'],'role':'report'},{'id':'S5-05-M3-evidence-v1','version':hashes['S5-05-M3-evidence-v1'],'role':'other'}]},0,**auth('run:'+str(seed)))
  criteria=[{'criterion_id':c,'passed':True,'evidence_id':i,'evidence_version':hashes[i],'explanation':e} for c,i,e in [('evidence','S5-05-M3-evidence-v1','锁定三种子配置、训练与逐条预测、模型、输入、源码环境、历史补算和回放证据。'),('conclusions','S5-05-M3-report-v1','训练侧选择、配对误差、分层、稳定性、特征贡献、铜基及适用范围，披露留出已观察。'),('release','S5-05-M3-model-card-v1','主模型卡和研究报告、局限、版本清单已归档，审核提交不等于通过。')]]
  result=service.submit_review(db,'S5-05',task['revision'],criteria,'S5-05 M3 综合评价证据提交审核；留出此前已观察，结论仅为内部探索。',**auth('submit'));assert result['status']=='in_review';assert verify()==hashes
 with sqlite3.connect(db) as c:assert c.execute('pragma quick_check').fetchone()[0]=='ok' and not c.execute('pragma foreign_key_check').fetchall()
 return result['status']
if __name__=='__main__':
 freeze(); B.mkdir(parents=True,exist_ok=False);backup.backup_database(DB,B/'before.sqlite');backup.backup_database(B/'before.sqlite',B/'rehearsal.sqlite');print('rehearsal',submit(B/'rehearsal.sqlite'),flush=True);print('formal',submit(DB),flush=True)

