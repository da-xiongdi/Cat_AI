"""Rehearse and register S4-02 with fixed workbench evidence."""

import hashlib
import sqlite3
from pathlib import Path

from catalyst_ai.storage.workbench import atomic_operations
from catalyst_ai.web.config import load
from catalyst_ai.workbench import index, plans, research_nodes, service

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/reports/s4-02-20261120-v1'
PLAN = 'docs/Cat_AI_next_stage_execution_draft_20261120.md'
FILES = {
    'S4-02-report': ('document', 'docs/s4_02_acceptance.md'),
    'S4-02-all': ('attachment', 'artifacts/reports/s4-02-20261120-v1/all-view.json'),
    'S4-02-cu': ('attachment', 'artifacts/reports/s4-02-20261120-v1/cu-view.json'),
    'S4-02-ledger': ('attachment', 'artifacts/reports/s4-02-20261120-v1/ledger.json'),
    'S4-02-distributions': ('attachment', 'artifacts/reports/s4-02-20261120-v1/distributions.json'),
    'S4-02-verification': ('attachment', 'artifacts/reports/s4-02-20261120-v1/verification.json'),
}


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def auth(key):
    return {'request_id': 's4-02-v1:' + key, 'actor': 'Codex'}


def backup(source, dest):
    if dest.exists():
        raise FileExistsError(dest)
    with sqlite3.connect(source) as src, sqlite3.connect(dest) as dst:
        src.backup(dst)


def register(db, hashes):
    with atomic_operations(db):
        assert service.get_task(db, 'S4-01')['status'] == 'done'
        assert not service.get_task(db, 'S4-01')['evidence_needs_review']
        assert all(sha(p) == h for p, h in hashes.items())
        for ident, (kind, path) in FILES.items():
            index.register(db, 'cat-ai', ident, kind, path, **auth(ident))
        index.scan(db, 'cat-ai', document_ids=list(FILES))
        criteria = [
            {'id': 'scope', 'description': '父快照、纳排规则与分类可逐条对账'},
            {'id': 'views', 'description': '两套成员与共同资格、特征覆盖及分布固定'},
            {'id': 'rebuild', 'description': '独立对账和重建哈希通过'},
            {'id': 'readiness', 'description': '铜基训练可行性、限制和门槛已记录'},
        ]
        created = service.create_task(db, {'id': 'S4-02', 'project_id': 'cat-ai',
            'title': '全体系与铜基数据集冻结', 'goal': '基于 S4-01 冻结可追溯的数据视图与共同特征资格',
            'deliverables': [p for _, p in FILES.values()], 'criteria': criteria,
            'stages': ['B', 'C'], 'primary_stage': 'B', 'priority': 'high', 'category': 'research', 'owner': 'Codex'}, **auth('task'))
        revision = service.add_dependency(db, 'S4-02', 'S4-01', created['revision'], **auth('dependency'))['revision']
        ref = plans.save_task_plan_reference(db, 'cat-ai', 'S4-02-primary-plan',
            {'task_id': 'S4-02', 'document_id': 'S4-scientific-plan', 'path': PLAN,
             'section_locator': 'S4-02 全体系与铜基数据集冻结', 'purpose': 'execution_plan', 'is_primary': 1},
            0, '登记冻结任务对应方案章节', **auth('plan'))
        plans.verify_task_plan_reference(db, 'cat-ai', 'S4-02-primary-plan', ref['revision'], hashes[PLAN], **auth('plan-verify'))
        research_nodes.save_task_node_link(db, 'cat-ai', 'S4-02-stage-B',
            {'task_id': 'S4-02', 'node_id': 'cat-ai:stage:B', 'role': 'primary'}, 0,
            '关联数据治理科研阶段', **auth('node'))
        revision = service.transition(db, 'S4-02', revision, 'ready', **auth('ready'))['revision']
        revision = service.transition(db, 'S4-02', revision, 'in_progress', **auth('start'))['revision']
        results = []
        for criterion, evidence in [('scope', 'S4-02-ledger'), ('views', 'S4-02-all'),
                                    ('rebuild', 'S4-02-verification'), ('readiness', 'S4-02-report')]:
            results.append({'criterion_id': criterion, 'passed': True, 'evidence_id': evidence,
                            'evidence_version': hashes[FILES[evidence][1]], 'explanation': '固定成果与对账证据已核验'})
        revision = service.submit_review(db, 'S4-02', revision, results, '成员、纳排、覆盖和重建校验通过', **auth('submit'))['revision']
        service.accept_review(db, 'S4-02', revision, 'S4-02 冻结和固定证据验收通过', **auth('accept'))
        assert all(sha(p) == h for p, h in hashes.items())
    result = service.get_task(db, 'S4-02')
    assert result['status'] == 'done' and not result['evidence_needs_review']
    with sqlite3.connect(db) as conn:
        assert conn.execute('pragma quick_check').fetchone()[0] == 'ok'
        assert not conn.execute('pragma foreign_key_check').fetchall()
    return result


if __name__ == '__main__':
    _, root, live = load(ROOT / 'configs/workbench.yaml')
    assert root == ROOT and live == ROOT / 'data/workbench.sqlite'
    hashes = {p: sha(p) for p in [PLAN, *(v[1] for v in FILES.values())]}
    baseline = OUT / 'workbench-before.sqlite'
    rehearsal = OUT / 'workbench-rehearsal.sqlite'
    backup(live, baseline)
    backup(baseline, rehearsal)
    register(rehearsal, hashes)
    register(live, hashes)
    print('S4-02: done; rehearsal and formal registration passed')
