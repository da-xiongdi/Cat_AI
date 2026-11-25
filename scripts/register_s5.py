"""Rehearse and atomically deploy the approved S5 tasks."""
import hashlib, json, sqlite3
from pathlib import Path
from catalyst_ai.storage.workbench import atomic_operations
from catalyst_ai.workbench import index, plans, research_nodes, service, backup
ROOT=Path(__file__).resolve().parents[1]; DB=ROOT/'data/workbench.sqlite'; OUT=ROOT/'artifacts/reports/s5-deployment-20261123-v2'
P='cat-ai'; TITLES=['科研协议与基线诊断','通用催化剂特征工程','铜基专项特征研究','机器学习算法与优化','综合模型评价与收口']
DEPS=[['S4-04'],['S5-01'],['S5-01','S5-02'],['S5-01'],['S5-02','S5-03','S5-04']]
STAGES=[['B','C','D'],['B','C'],['B','C','D'],['C'],['C','D']]
CHECKS=[['baseline','split','protocol'],['descriptors','transform','ablation'],['copper_scope','copper_features','paired_or_gap'],['estimators','benchmark','search'],['evidence','conclusions','release']]
def auth(key): return {'request_id':'s5-deployment-v1:'+key,'actor':'Codex'}
def sha(p): return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
def deploy(db, fail=False):
 with atomic_operations(db):
  assert service.get_task(db,'S4-04')['status']=='done' and not service.get_task(db,'S4-04')['evidence_needs_review']
  docs=[('S5-research-plan','docs/s5_implementation_plan.md','research_plan')]+[(f'S5-0{i}-execution-plan',f'docs/s5_0{i}_execution.md','execution_plan') for i in range(1,6)]
  for ident,path,purpose in docs: index.register(db,P,ident,'document',path,**auth('doc:'+ident))
  index.scan(db,P,document_ids=[x[0] for x in docs])
  for ident,path,purpose in docs: plans.save_document_purpose(db,P,ident+'-purpose',{'document_id':ident,'purpose':purpose,'category':'research'},0,'登记 S5 方案',**auth('purpose:'+ident))
  with sqlite3.connect(db) as c: order=c.execute("select coalesce(max(sort_order),-1)+1 from research_node where parent_id='cat-ai:stage:C'").fetchone()[0]
  research_nodes.save_research_node(db,P,'cat-ai:task-branch:S5',{'stage':'C','parent_id':'cat-ai:stage:C','sort_order':order,'source_path':docs[0][1],'source_section':'S5 特征工程与模型评价','source_sha256':sha(docs[0][1])},0,'登记 S5 路线',**auth('branch'))
  for i,title in enumerate(TITLES,1):
   tid=f'S5-0{i}'; path=f'docs/s5_0{i}_execution.md'; heading=tid+' '+title
   service.create_task(db,{'id':tid,'project_id':P,'title':title,'goal':'按批准的执行计划完成'+title,'deliverables':[path], 'criteria':[{'id':x,'description':f'{heading}：按执行计划完成 {x} 验收证据'} for x in CHECKS[i-1]],'stages':STAGES[i-1],'primary_stage':'C','priority':'high' if i in (1,2,4) else 'normal','category':'research','milestone':'S5','owner':'Codex'},**auth('task:'+tid))
   ref=tid+'-primary-plan'; saved=plans.save_task_plan_reference(db,P,ref,{'task_id':tid,'document_id':tid+'-execution-plan','path':path,'section_locator':heading,'purpose':'execution_plan','is_primary':1},0,'登记主执行计划',**auth('ref:'+tid))
   plans.verify_task_plan_reference(db,P,ref,saved['revision'],sha(path),**auth('verify:'+tid))
   research_nodes.save_task_node_link(db,P,tid+'-S5',{'task_id':tid,'node_id':'cat-ai:task-branch:S5','role':'primary'},0,'关联 S5 路线',**auth('link:'+tid))
   for stage in STAGES[i-1]:
    if stage!='C': research_nodes.save_task_node_link(db,P,tid+'-stage-'+stage,{'task_id':tid,'node_id':'cat-ai:stage:'+stage,'role':'reference'},0,'关联跨阶段路线',**auth('link:'+tid+stage))
  if fail: raise RuntimeError('intentional rollback')
  for i,deps in enumerate(DEPS,1):
   tid=f'S5-0{i}'; rev=service.get_task(db,tid)['revision']
   for dep in deps: rev=service.add_dependency(db,tid,dep,rev,**auth('dep:'+tid+dep))['revision']
   if i==1:
    rev=service.transition(db,tid,rev,'ready',**auth('ready'))['revision']; service.transition(db,tid,rev,'in_progress',**auth('start'))
def verify(db):
 with sqlite3.connect(db) as c:
  assert c.execute('pragma integrity_check').fetchone()[0]=='ok' and not c.execute('pragma foreign_key_check').fetchall()
  tasks=c.execute("select id,status from task where id like 'S5-0%' order by id").fetchall(); assert tasks==[(f'S5-0{i}','in_progress' if i==1 else 'planned') for i in range(1,6)]
  deps=c.execute("select task_id,prerequisite_id from dependency where task_id like 'S5-0%' order by 1,2").fetchall(); assert set(deps)=={(f'S5-0{i}',d) for i,ds in enumerate(DEPS,1) for d in ds}
  return {'tasks':tasks,'dependencies':deps}
if __name__=='__main__':
 OUT.mkdir(parents=True,exist_ok=False)
 bundle=backup.create_bundle(DB,ROOT); (OUT/'before.zip').write_bytes(bundle); preview=backup.preview_bundle(bundle); restored=backup.restore_bundle(bundle,OUT/'restored',preview['sha256']); print('bundle missing',len(preview['manifest']['missing']))
 rehearsal=OUT/'rehearsal.sqlite'; backup.backup_database(DB,rehearsal)
 # Intentional exception tests rollback of all nested writes.
 try:
  deploy(rehearsal, fail=True)
 except RuntimeError as e:
  assert str(e)=='intentional rollback'
 with sqlite3.connect(rehearsal) as c: assert c.execute("select count(*) from task where id like 'S5-0%'").fetchone()[0]==0
 deploy(rehearsal); result=verify(rehearsal)
 # Exact request replay must be harmless, or duplicate deployment must fail atomically.
 try: deploy(rehearsal)
 except Exception as e: print('duplicate safely rejected:',type(e).__name__,str(e))
 assert verify(rehearsal)==result
 deploy(DB); result=verify(DB)
 (OUT/'verification.json').write_text(json.dumps({'rehearsal':result,'live':result,'rollback':'passed','duplicate':'no duplicate records','bundle_sha256':preview['sha256'],'bundle_missing':preview['manifest']['missing'],'restored':restored['path']},ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(result,ensure_ascii=False))

