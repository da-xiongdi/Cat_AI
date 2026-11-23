"""Register and accept the fixed S4-04 evidence after a database rehearsal."""
import hashlib, json, sqlite3
from contextlib import closing
from pathlib import Path
from catalyst_ai.storage.workbench import atomic_operations
from catalyst_ai.web.config import load
from catalyst_ai.workbench import index, plans, research_nodes, service
ROOT=Path(__file__).resolve().parents[1]
PLAN='docs/Cat_AI_next_stage_execution_draft_20261120.md'
FILES={
'S4-04-report':('document','docs/s4_04_final_report.md'),
'S4-04-audit':('document','docs/s4_04_evidence_audit.md'),
'S4-04-comparison':('document','docs/s4_04_comparison_analysis.md'),
'S4-04-applicability':('document','docs/s4_04_applicability_coverage.md'),
'S4-04-index':('attachment','artifacts/reports/s4-04-final-20261123-v1/evidence-sha256.json'),
'S4-04-figure':('attachment','artifacts/reports/s4-04-final-20261123-v1/fold-seed-maa.svg'),
}
FILES['S4-04-figure']=('attachment','artifacts/reports/s4-04-final-20261123-v1/fold-seed-mae.svg')
def sha(path): return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
def auth(key): return {'request_id':'s4-04-close-20261123-v1:'+key,'actor':'Codex'}
def verify():
    doc=json.loads((ROOT/FILES['S4-04-index'][1]).read_text(encoding='utf8'))
    assert len(doc['files'])>=140
    for path,h in doc['files'].items():
        if sha(path)!=h: raise ValueError('evidence hash mismatch: '+path)
    return {p:sha(p) for _,p in FILES.values()}
def backup(src,dst):
    if dst.exists(): raise FileExistsError(dst)
    with closing(sqlite3.connect(src)) as a, closing(sqlite3.connect(dst)) as b:a.backup(b)
def close(db,hashes):
    with atomic_operations(db):
        assert service.get_task(db,'S4-03')['status']=='done'
        assert verify()==hashes
        task=service.create_task(db,{'id':'S4-04','project_id':'cat-ai','title':'首轮模型对照',
          'goal':'完成固定协议的全体系与铜基首轮内部对照并记录证据边界',
          'deliverables':['docs/s4_04_final_report.md','artifacts/reports/s4-04-final-20261123-v1/evidence-sha256.json'],
          'criteria':[{'id':'runs','description':'九组固定配置、模型、逐条结果及指标绑定并复核'},
                      {'id':'comparison','description':'共同铜基留出配对及种子与划分差异已分析'},
                      {'id':'scope','description':'覆盖、来源、可用性与证据限制已报告'}],
          'stages':['C','D'],'primary_stage':'C','priority':'high','category':'research','owner':'Codex'},**auth('task'))
        rev=service.add_dependency(db,'S4-04','S4-03',task['revision'],**auth('dependency'))['revision']
        ref=plans.save_task_plan_reference(db,'cat-ai','S4-04-primary-plan',{'task_id':'S4-04','document_id':'S4-scientific-plan','path':PLAN,'section_locator':'S4-04 第一轮模型对照','purpose':'execution_plan','is_primary':1},0,'登记执行计划',**auth('plan'))
        plans.verify_task_plan_reference(db,'cat-ai','S4-04-primary-plan',ref['revision'],sha(PLAN),**auth('verify-plan'))
        research_nodes.save_task_node_link(db,'cat-ai','S4-04-stage-C',{'task_id':'S4-04','node_id':'cat-ai:stage:C','role':'primary'},0,'关联科研阶段',**auth('node'))
        rev=service.transition(db,'S4-04',rev,'ready',**auth('ready'))['revision']
        rev=service.transition(db,'S4-04',rev,'in_progress',**auth('start'))['revision']
        for ident,(kind,path) in FILES.items(): index.register(db,'cat-ai',ident,kind,path,**auth(ident))
        index.scan(db,'cat-ai',document_ids=list(FILES))
        checks=[('runs','S4-04-index'),('comparison','S4-04-comparison'),('scope','S4-04-applicability')]
        results=[{'criterion_id':c,'passed':True,'evidence_id':e,'evidence_version':hashes[FILES[e][1]],'explanation':'固定内部对照及限制见最终报告和证据'} for c,e in checks]
        rev=service.submit_review(db,'S4-04',rev,results,'固定内部实验、比较与证据边界核验通过',**auth('submit'))['revision']
        service.accept_review(db,'S4-04',rev,'S4-04 首轮内部对照证据验收通过',**auth('accept'))
        assert verify()==hashes
    task=service.get_task(db,'S4-04'); assert task['status']=='done' and not task['evidence_needs_review']
    with closing(sqlite3.connect(db)) as c:
        assert c.execute('pragma quick_check').fetchone()[0]=='ok'
        assert not c.execute('pragma foreign_key_check').fetchall()
if __name__=='__main__':
    _,root,live=load(ROOT/'configs/workbench.yaml');assert root==ROOT
    hashes=verify(); out=ROOT/'artifacts/reports/s4-04-registration-20261123-v1';out.mkdir(parents=True,exist_ok=False)
    backup(live,out/'before.sqlite');backup(out/'before.sqlite',out/'rehearsal.sqlite')
    close(out/'rehearsal.sqlite',hashes);close(live,hashes)
    print('S4-04 done: rehearsal and formal acceptance passed')
