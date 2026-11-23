"""Independently reconcile S4-02 outputs and reproduce their byte hashes."""

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from catalyst_ai.reporting.evidence import digest, write_json
from s4_01_profile import ROOT

OUT = ROOT / 'artifacts/reports/s4-02-20261120-v1'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    with tempfile.TemporaryDirectory() as temp:
        rebuilt = Path(temp) / 'rebuilt'
        subprocess.run([sys.executable, str(ROOT / 'scripts/s4_02_freeze.py'), '--output', str(rebuilt)], cwd=ROOT, check=True)
        hashes = {p.name: sha(p) for p in sorted(OUT.glob('*.json')) if p.name != 'verification.json'}
        assert set(hashes) == {'all-view.json', 'cu-view.json', 'ledger.json', 'distributions.json'}
        assert hashes == {p.name: sha(p) for p in sorted(rebuilt.glob('*.json'))}
    ledger = json.loads((OUT / 'ledger.json').read_text(encoding='utf-8'))['records']
    views = [json.loads((OUT / f'{x}-view.json').read_text(encoding='utf-8')) for x in ('all', 'cu')]
    for view in views:
        assert digest(view['content']) == view['content_sha256']
        assert view['view_id'].endswith(view['content_sha256'])
    all_content, cu_content = [v['content'] for v in views]
    source = list(csv.DictReader((ROOT / 'artifacts/reports/s4-01-20261120/audit/record-audit.csv').open(encoding='utf-8-sig', newline='')))
    pairs = list(csv.DictReader((ROOT / 'artifacts/reports/s4-01-20261120/audit/candidate-pairs.csv').open(encoding='utf-8-sig', newline='')))
    pending = {p[k] for p in pairs if p['disposition'].endswith('identity_unresolved') for k in ('left_record_id', 'right_record_id')}
    assert len(source) == len(ledger) == len({r['record_id'] for r in ledger}) == 593
    by_id = {r['record_id']: r for r in source}
    assert set(by_id) == {r['record_id'] for r in ledger}
    assert len(pending) == 15
    selection = json.loads((ROOT / 'artifacts/reports/s1-b-20261113-v4/selection.json').read_text(encoding='utf-8'))['content']
    eligible = {rid for ids in selection['retained'].values() for rid in ids}
    expect_all_target = set(by_id) - pending
    expect_all_common = expect_all_target & eligible
    expect_cu = {rid for rid, row in by_id.items() if row['classification'] == 'cu'}
    assert set(all_content['target_record_ids']) == expect_all_target
    assert set(all_content['common_record_ids']) == expect_all_common
    assert set(cu_content['target_record_ids']) == expect_all_target & expect_cu
    assert set(cu_content['common_record_ids']) == expect_all_common & expect_cu
    assert len(expect_all_common) == 542 and len(expect_cu) == 211 and len(pending & eligible) == 11
    for row in ledger:
        rid = row['record_id']; original = by_id[rid]
        assert row['classification'] == original['classification'] and row['raw_locator'] == original['raw_locator']
        assert row['target_view_included'] == (rid in expect_all_target)
        assert row['model_view_included'] == (rid in expect_all_common)
        assert row['cu_model_view_included'] == (rid in expect_all_common & expect_cu)
        assert ('unresolved_experiment_identity' in row['exclusion_reasons']) == (rid in pending)
    stats = json.loads((OUT / 'distributions.json').read_text(encoding='utf-8'))
    for key, ids in [('all_target', expect_all_target), ('all_common', expect_all_common), ('cu_common', expect_cu)]:
        counted = Counter(by_id[i]['doi'] for i in ids)
        assert stats[key]['records'] == len(ids) and stats[key]['doi_records'] == dict(counted)
        assert stats[key]['composition_signatures'] == len({by_id[i]['composition'] for i in ids})
        assert stats[key]['common_feature_qualified'] == len(ids & eligible)
        for field in ('temperature_k', 'pressure_bar_abs', 'h2_co2_ratio', 'flow_nl_g_h', 'conversion_pct'):
            values = sorted(float(by_id[i][field]) for i in ids)
            assert stats[key]['ranges'][field]['n'] == len(values)
            assert stats[key]['ranges'][field]['min'] == values[0] and stats[key]['ranges'][field]['max'] == values[-1]
    return {'result': 'passed', 'byte_identical_rebuild': hashes, 'parent_rows': 593, 'unresolved_excluded': 15,
            'all_target': 578, 'all_common': 542, 'cu_target': 211, 'cu_common': 211,
            'independent_checks': ['S4-01 CSV identity and candidates', 'S1-B selection', 'member subset and row exclusions', 'DOI and composition counts', 'numeric minima maxima and non-null counts', 'canonical manifest hashes', 'byte-identical rebuild'],
            'verification_script_sha256': sha(Path(__file__))}


if __name__ == '__main__':
    write_json(OUT / 'verification.json', verify())
