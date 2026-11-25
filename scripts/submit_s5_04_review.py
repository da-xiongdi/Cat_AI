"""Freeze and register independently verified S5-04 M1/M2 evidence."""
import hashlib
import json
import sqlite3
from pathlib import Path

from catalyst_ai.storage.workbench import atomic_operations
from catalyst_ai.workbench import backup, index, model_runs, service

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/reports/s5-04-e02-20261124-v1'
BACKUP=ROOT/'backups/s5-04-review-20261124-v1'
MANIFEST=OUT/'evidence-sha256-final.json'
FILES={'S5-04-M1-estimators': 'release-verification.json',
       'S5-04-M1-benchmark': 'final-review-report.md',
       'S5-04-M2-search': 'reload-and-membership-audit.json',
       'S5-04-M2-manifest': 'evidence-sha256-final.json',
       'S5-04-M1-batch': 'batch-verification/verification.json',
       'S5-04-M1-historical': 'historical-verification.json'}
for phase in ('fixed','search'):
    for seed in (45,46,47):
        FILES[f'S5-04-{phase}-{seed}-lock'] = f'{phase}-{seed}/lock.json'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def auth(k): return {'request_id':'s5-04-review-v1:'+k,'actor':'Codex'}
def freeze():
    assert not MANIFEST.exists()
    previous=read(OUT/'evidence-sha256.json')
    assert all((ROOT/p).is_file() and sha(ROOT/p)==h for p,h in previous['files'].items())
    prereg=read(OUT/'preregistration-sha256.json')
    assert all(sha(ROOT/p)==h for p,h in prereg.items())
    release=read(OUT/'release-verification.json'); assert len(release['runs'])==6
    assert sum(v['arms'] for v in release['runs'].values())==48
    assert all(all(n==108 for n in v['records_per_arm']) for v in release['runs'].values())
    hist=read(OUT/'historical-verification.json'); assert len(hist['runs'])==9 and all(x['status']=='pass' for x in hist['runs'].values())
    assert len(hist['packages'])==3 and all(x['status']=='pass' for x in hist['packages'].values())
    batch=read(OUT/'batch-verification/verification.json'); assert batch['failure_preserved'] and batch['implicit_retry_rejected'] and batch['explicit_retry_complete'] and batch['all_arms_match_fixed_run']
    audit=read(OUT/'reload-and-membership-audit.json'); assert len(audit)==6 and all(x['selected']==0 for x in audit.values())
    assert '37 passed' in (OUT/'regression-tests.log').read_text(encoding='utf-8')
    files=[p for p in OUT.rglob('*') if p.is_file() and p != MANIFEST]
    files += list((ROOT/'src/catalyst_ai').rglob('*.py'))
    files += [ROOT/p for p in ['pyproject.toml','uv.lock','docs/s5_04_execution.md','docs/s5_implementation_plan.md','docs/s5_evaluation_metrics_supplement_v1.md','scripts/s5_04_execute.py','scripts/s5_04_audit.py','scripts/s5_04_batch_verify.py','scripts/s5_04_release_verify.py','scripts/s5_04_historical_verify.py','scripts/submit_s5_04_review.py','tests/unit/test_s5_estimators.py','tests/unit/test_s5_metrics.py','tests/unit/test_s5_selection.py','data/catalog.sqlite','data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json','artifacts/reports/s4-02-20261120-v1/all-view.json','artifacts/reports/s4-02-20261120-v1/ledger.json','artifacts/reports/s4-02-20261120-v1/distributions.json']]
    for name in hist['runs']:
        files.extend((ROOT/'artifacts/reports/s4-04-runs-20261120-v1'/name/p) for p in ('lock.json','model.pkl','holdout/predictions.json'))
    files=list(set(files))
    manifest={'algorithm':'sha256','files':{p.relative_to(ROOT).as_posix():sha(p) for p in sorted(files)}}
    MANIFEST.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('frozen files',len(files))
def verify():
    m=read(MANIFEST); assert all((ROOT/p).is_file() and sha(ROOT/p)==h for p,h in m['files'].items())
    return {k:sha(OUT/v) for k,v in FILES.items()}
def submit(db):
    hashes=verify()
    with atomic_operations(db):
        task=service.get_task(db,'S5-04'); assert task['status']=='in_progress'
        for ident,name in FILES.items():
            path=(OUT/name).relative_to(ROOT).as_posix()
            index.register(db,'cat-ai',ident,'document' if path.endswith('.md') else 'attachment',path,**auth('register:'+ident))
        index.scan(db,'cat-ai',document_ids=list(FILES))
        for phase in ('fixed','search'):
            for seed in (45,46,47):
                evidence_id=f'S5-04-{phase}-{seed}-lock'
                model_runs.save(db,'cat-ai',f'S5-04-{phase}-{seed}',{
                    'title':f'S5-E02 {phase} seed {seed}', 'task_id':'S5-04',
                    'execution_status':'succeeded','research_status':'unreviewed',
                    'target':'CO2 conversion','unit':'%','dataset':f'S5 frozen all-system seed {seed}',
                    'feature_version':'F_base','algorithm':'Extra Trees, random forest, gradient boosting, dummy, ridge',
                    'configuration':f'{phase} candidate catalog; model seed 42; five folds',
                    'evaluation_scope':'Internal held-out evaluation; training-only s5-paired-v1 selection',
                    'conclusion':'Fixed Extra Trees selected; see review report for paired results.',
                    'limitations':'Previously used holdout; overlapping seeds; no external validation.',
                    'evidence':[{'id':evidence_id,'version':hashes[evidence_id],'role':'other'},
                                {'id':'S5-04-M1-benchmark','version':hashes['S5-04-M1-benchmark'],'role':'report'},
                                {'id':'S5-04-M2-manifest','version':hashes['S5-04-M2-manifest'],'role':'other'}]
                },0,**auth('run:'+phase+str(seed)))
        criteria=[{'criterion_id':c,'passed':True,'evidence_id':i,'evidence_version':hashes[i],'explanation':e} for c,i,e in [
            ('estimators','S5-04-M1-estimators','Independent wheel installation and all arm predictions reproduced; batch failure/retry and locked historical replay are registered separately.'),
            ('benchmark','S5-04-M1-benchmark','Fixed-parameter paired comparisons, coverage, R2, DOI strata, seeds and limitations; manifest binds all underlying outputs.'),
            ('search','S5-04-M2-search','Frozen candidates, training-only selection, membership and fold verification, all model reloads and full locked traces are bound by the evidence manifest.')]]
        result=service.submit_review(db,'S5-04',task['revision'],criteria,'S5-04 M1/M2 submitted for review; internal holdout exposure and algorithm scope are documented.',**auth('submit'))
        assert result['status']=='in_review' and verify()==hashes
    with sqlite3.connect(db) as c:
        assert c.execute('pragma quick_check').fetchone()[0]=='ok' and not c.execute('pragma foreign_key_check').fetchall()
    return result
if __name__=='__main__':
    freeze(); verify()
    BACKUP.mkdir(parents=True,exist_ok=False)
    db=ROOT/'data/workbench.sqlite'
    backup.backup_database(db,BACKUP/'before.sqlite')
    backup.backup_database(BACKUP/'before.sqlite',BACKUP/'rehearsal.sqlite')
    print('rehearsal',submit(BACKUP/'rehearsal.sqlite'))
    print('formal',submit(db))
