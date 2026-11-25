"""Submit S5-01 M0 for review after an isolated database rehearsal."""
import hashlib
import json
import sqlite3
from pathlib import Path
from catalyst_ai.storage.workbench import atomic_operations
from catalyst_ai.workbench import backup, index, service

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / 'data/workbench.sqlite'
OUT = ROOT / 'artifacts/reports/s5-01-m0-20261123-v2'
FILES = {
    'S5-01-m0-baseline-v2': 'artifacts/reports/s5-01-m0-20261123-v1/baseline_inventory.md',
    'S5-01-m0-split-v2': 'artifacts/reports/s5-01-m0-20261123-v1/split_audit.json',
    'S5-01-m0-protocol-v2': 'artifacts/reports/s5-01-m0-20261123-v2/protocol.md',
    'S5-01-m0-verification-v2': 'artifacts/reports/s5-01-m0-20261123-v2/verification.md',
    'S5-01-m0-evidence-v2': 'artifacts/reports/s5-01-m0-20261123-v2/evidence-sha256.json',
}

def auth(key):
    return {'request_id': 's5-01-m0-review-v2:' + key, 'actor': 'Codex'}

def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()

def verify_evidence():
    manifest = json.loads((OUT / 'evidence-sha256.json').read_text(encoding='utf-8-sig'))
    for path, expected in manifest['files'].items():
        if sha(path) != expected:
            raise ValueError('evidence mismatch: ' + path)
    return {ident: sha(path) for ident, path in FILES.items()}

def submit(db):
    hashes = verify_evidence()
    with atomic_operations(db):
        task = service.get_task(db, 'S5-01')
        assert task['status'] == 'in_progress'
        for ident, path in FILES.items():
            index.register(db, 'cat-ai', ident, 'document' if path.endswith('.md') else 'attachment', path, **auth('register:' + ident))
        index.scan(db, 'cat-ai', document_ids=list(FILES))
        results = [
            {'criterion_id': criterion, 'passed': True, 'evidence_id': ident,
             'evidence_version': hashes[ident], 'explanation': explanation}
            for criterion, ident, explanation in [
                ('baseline', 'S5-01-m0-baseline-v2', 'S4 基线与历史证据已对账；兼容重放见验证报告。'),
                ('split', 'S5-01-m0-split-v2', '身份、成员、随机分组、五折及铜基投影见逐项审计。'),
                ('protocol', 'S5-01-m0-protocol-v2', '训练侧选择、覆盖、回退及留出隔离见协议；实现验证见固定清单和验证报告。'),
            ]
        ]
        result = service.submit_review(db, 'S5-01', task['revision'], results,
            'S5-01 M0 证据已固定，提交科研审核；后续任务尚未启动。', **auth('submit'))
        assert result['status'] == 'in_review'
        assert verify_evidence() == hashes
    with sqlite3.connect(db) as conn:
        assert conn.execute('pragma integrity_check').fetchone()[0] == 'ok'
        assert not conn.execute('pragma foreign_key_check').fetchall()
        assert conn.execute("select count(*) from task where id in ('S5-02','S5-03','S5-04','S5-05') and status='planned'").fetchone()[0] == 4
    return result

if __name__ == '__main__':
    backup.backup_database(DB, OUT / 'review-before.sqlite')
    backup.backup_database(OUT / 'review-before.sqlite', OUT / 'review-rehearsal.sqlite')
    print('rehearsal', submit(OUT / 'review-rehearsal.sqlite'))
    print('formal', submit(DB))
