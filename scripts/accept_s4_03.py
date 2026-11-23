"""Rehearse and register fixed S4-03 evidence before formal task acceptance."""
import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

from catalyst_ai.storage.workbench import atomic_operations
from catalyst_ai.web.config import load
from catalyst_ai.workbench import index, service

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    'S4-03-report': ('document', 'docs/s4_03_acceptance.md'),
    'S4-03-coverage': ('attachment', 'artifacts/reports/s4-03-frozen-20261120-v2/coverage.json'),
    'S4-03-verification': ('attachment', 'artifacts/reports/s4-03-verification-20261120-v5/verification.json'),
    'S4-03-test-log': ('attachment', 'artifacts/reports/s4-03-verification-20261120-v5/pytest.log'),
    'S4-03-runner': ('attachment', 'scripts/run_research_experiment.py'),
}
for seed in (42, 43, 44):
    for name in ('EXP-01', 'EXP-02', 'EXP-03'):
        FILES[f'S4-03-{name}-{seed}'] = ('attachment', f'artifacts/reports/s4-03-frozen-20261120-v2/{name}-{seed}.json')
        FILES[f'S4-03-config-{name}-{seed}'] = ('attachment', f'artifacts/reports/s4-03-frozen-20261120-v2/configs/{name}-{seed}.json')


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def auth(key):
    return {'request_id': 's4-03-accept-v1:' + key, 'actor': 'Codex'}


def backup(source, dest):
    if dest.exists():
        raise FileExistsError(dest)
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(dest)) as dst:
        src.backup(dst)


def accept(db, hashes):
    with atomic_operations(db):
        assert service.get_task(db, 'S4-02')['status'] == 'done'
        task = service.get_task(db, 'S4-03')
        assert task['status'] == 'in_progress'
        assert all(sha(p) == h for p, h in hashes.items())
        for ident, (kind, path) in FILES.items():
            index.register(db, 'cat-ai', ident, kind, path, **auth(ident))
        index.scan(db, 'cat-ai', document_ids=list(FILES))
        checks = [('splits', 'S4-03-coverage'), ('runner', 'S4-03-verification'),
                  ('compatibility', 'S4-03-verification')]
        results = [{'criterion_id': criterion, 'passed': True, 'evidence_id': evidence,
                    'evidence_version': hashes[FILES[evidence][1]],
                    'explanation': '固定证据、隔离测试及边界见验收报告'} for criterion, evidence in checks]
        revision = service.submit_review(db, 'S4-03', task['revision'], results,
                                         '划分、训练接口及隔离验证通过', **auth('submit'))['revision']
        service.accept_review(db, 'S4-03', revision, 'S4-03 固定证据验收通过', **auth('accept'))
        assert all(sha(p) == h for p, h in hashes.items())
    result = service.get_task(db, 'S4-03')
    assert result['status'] == 'done' and not result['evidence_needs_review']
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute('pragma quick_check').fetchone()[0] == 'ok'
        assert not conn.execute('pragma foreign_key_check').fetchall()


if __name__ == '__main__':
    _, root, live = load(ROOT / 'configs/workbench.yaml')
    assert root == ROOT
    hashes = {path: sha(path) for _, path in FILES.values()}
    out = ROOT / 'artifacts/reports/s4-03-registration-20261120-v1'
    out.mkdir(parents=True, exist_ok=False)
    baseline, rehearsal = out / 'before.sqlite', out / 'rehearsal.sqlite'
    backup(live, baseline)
    backup(baseline, rehearsal)
    accept(rehearsal, hashes)
    accept(live, hashes)
    print('S4-03: done; rehearsal and formal registration passed')
