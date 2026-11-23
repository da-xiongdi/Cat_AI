"""Register the active S4-03 task after a rehearsal on a database copy."""
import hashlib
import gc
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from catalyst_ai.storage.workbench import atomic_operations
from catalyst_ai.web.config import load
from catalyst_ai.workbench import plans, research_nodes, service

ROOT = Path(__file__).resolve().parents[1]
PLAN = 'docs/Cat_AI_next_stage_execution_draft_20261120.md'


def auth(key):
    return {'request_id': 's4-03-start-v1:' + key, 'actor': 'Codex'}


def register(db):
    with atomic_operations(db):
        assert service.get_task(db, 'S4-02')['status'] == 'done'
        task = service.create_task(db, {'id': 'S4-03', 'project_id': 'cat-ai',
            'title': '划分协议与训练接入', 'goal': '建立配置驱动的可重现科研划分、训练和隔离评分能力',
            'deliverables': ['划分与覆盖清单', '通用科研实验入口', '验证及验收证据'],
            'criteria': [{'id': 'splits', 'description': '分组隔离、覆盖与铜基共享测试通过'},
                         {'id': 'runner', 'description': '配置驱动训练、独立评分与成果可重现'},
                         {'id': 'compatibility', 'description': '历史兼容及功能验证通过'}],
            'stages': ['C', 'D'], 'primary_stage': 'C', 'priority': 'high',
            'category': 'research', 'owner': 'Codex'}, **auth('task'))
        rev = service.add_dependency(db, 'S4-03', 'S4-02', task['revision'], **auth('dependency'))['revision']
        ref = plans.save_task_plan_reference(db, 'cat-ai', 'S4-03-primary-plan',
            {'task_id': 'S4-03', 'document_id': 'S4-scientific-plan', 'path': PLAN,
             'section_locator': 'S4-03 划分协议与训练接入', 'purpose': 'execution_plan', 'is_primary': 1},
            0, '登记执行方案', **auth('plan'))
        sha = hashlib.sha256((ROOT / PLAN).read_bytes()).hexdigest()
        plans.verify_task_plan_reference(db, 'cat-ai', 'S4-03-primary-plan', ref['revision'], sha, **auth('verify'))
        research_nodes.save_task_node_link(db, 'cat-ai', 'S4-03-stage-C',
            {'task_id': 'S4-03', 'node_id': 'cat-ai:stage:C', 'role': 'primary'}, 0, '关联科研阶段', **auth('node'))
        rev = service.transition(db, 'S4-03', rev, 'ready', **auth('ready'))['revision']
        service.transition(db, 'S4-03', rev, 'in_progress', **auth('start'))


if __name__ == '__main__':
    _, root, live = load(ROOT / 'configs/workbench.yaml')
    assert root == ROOT
    with tempfile.TemporaryDirectory() as temp:
        copy = Path(temp) / 'workbench.sqlite'
        with closing(sqlite3.connect(live)) as source, closing(sqlite3.connect(copy)) as dest:
            source.backup(dest)
        register(copy)
        with closing(sqlite3.connect(copy)) as db:
            assert db.execute('pragma quick_check').fetchone()[0] == 'ok'
            assert not db.execute('pragma foreign_key_check').fetchall()
        register(live)
        gc.collect()
    print('S4-03 registered: in_progress')
