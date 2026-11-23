"""Build reproducible S4-02 manifest views over the existing frozen snapshot."""

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path
from statistics import median

from catalyst_ai.reporting.evidence import digest, write_json
from s4_01_profile import FILES, ROOT, distribution, profile

SELECTION = ROOT / FILES['selection']
FEATURES = ROOT / 'artifacts/reports/s1-b-20261113-v4/features.json'
QUALIFICATION = ROOT / 'data/snapshots/qualifications/qualification-b450e999aca00cd7e035b5bb1006a48d3fbd171520391710eb05a2490aa85967.json'
AUDIT = ROOT / 'artifacts/reports/s4-01-20261120/audit'


def filehash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ordered(counter):
    return dict(sorted(counter.items(), key=lambda x: (-x[1], x[0])))


def report(rows, features):
    result = distribution(rows)
    result.pop('historical_partition')
    result['composition_distribution'] = ordered(Counter(r['composition'] for r in rows))
    result['sample_name_distribution'] = ordered(Counter(r['sample_name'] for r in rows))
    species = Counter()
    for row in rows:
        species.update({part[1] for part in json.loads(row['composition'])})
    result['species_presence'] = ordered(species)
    for field in ('temperature_k', 'pressure_bar_abs', 'h2_co2_ratio', 'flow_nl_g_h', 'conversion_pct'):
        values = sorted(r[field] for r in rows if r[field] is not None)
        result['ranges'][field]['value_counts'] = dict(sorted(Counter(str(x) for x in values).items(), key=lambda x: float(x[0])))
        result['ranges'][field]['missing'] = len(rows) - len(values)
    present = [features[r['record_id']] for r in rows if r['record_id'] in features]
    result['common_feature_qualified'] = len(present)
    result['derived_feature_states'] = {
        key: ordered(Counter(r['derived'][key]['state'] for r in present))
        for key in sorted(present[0]['derived'])
    } if present else {}
    return result


def build(out):
    out.mkdir(parents=True, exist_ok=False)
    summary, rows, candidates, matched = profile()
    source_profile = json.loads((AUDIT / 'profile.json').read_text(encoding='utf-8'))
    assert summary == source_profile, 'S4-01 source or rules changed'
    selection = json.loads(SELECTION.read_text(encoding='utf-8'))
    feature_doc = json.loads(FEATURES.read_text(encoding='utf-8'))
    qual = json.loads(QUALIFICATION.read_text(encoding='utf-8'))
    for d in (selection, feature_doc, qual):
        assert digest(d['content']) == d['content_sha256']
    assert feature_doc['content']['selection_id'] == selection['selection_id']
    assert selection['content']['binding']['qualification_id'] == qual['qualification_id']
    features = {r['record_id']: r for r in feature_doc['content']['rows']}
    common = {i for ids in selection['content']['retained'].values() for i in ids}
    exclusions = {x['record_id']: x['reason'] for group in selection['content']['excluded'].values() for x in group}
    assert len(features) == len(common) == 553 and set(features) == common
    assert len(exclusions) == 40 and set(exclusions).isdisjoint(common)
    assert set(exclusions) | common == {r['record_id'] for r in rows}
    pending = {p[k] for p in candidates if p['disposition'].endswith('identity_unresolved') for k in ('left_record_id', 'right_record_id')}
    assert len(pending) == 15 and len(pending & common) == 11
    assert all(r['classification'] == 'non_cu' for r in rows if r['record_id'] in pending)
    parent = json.loads((ROOT / FILES['snapshot']).read_text(encoding='utf-8'))
    with sqlite3.connect(f'file:{(ROOT / "data/catalog.sqlite").as_posix()}?mode=ro', uri=True) as db:
        saved = db.execute('select content_sha256,manifest from dataset_snapshot where id=?', (parent['snapshot_id'],)).fetchone()
        assert saved and saved[0] == parent['content_sha256'] and json.loads(saved[1]) == parent
        ids = {x[0] for x in db.execute('select id from curated_record')}
        assert {r['record_id'] for r in rows} <= ids
    ledger = []
    for r in rows:
        rid = r['record_id']; qualified = rid in common; unresolved = rid in pending
        ledger.append({'record_id': rid, 'raw_locator': r['raw_locator'], 'doi': r['doi'],
                       'classification': r['classification'], 'repeat_identity_status': r['repeat_identity_status'],
                       's1_common_eligible': qualified, 's1_exclusion_reasons': exclusions.get(rid, []),
                       'target_view_included': not unresolved, 'model_view_included': qualified and not unresolved,
                       'cu_target_view_included': r['classification'] == 'cu' and not unresolved,
                       'cu_model_view_included': r['classification'] == 'cu' and qualified and not unresolved,
                       'exclusion_reasons': (['unresolved_experiment_identity'] if unresolved else []) + ([] if qualified else ['s1_common_feature_ineligible'])})
    target = [r for r in rows if r['record_id'] not in pending]
    model = [r for r in target if r['record_id'] in common]
    cu_target = [r for r in target if r['classification'] == 'cu']
    cu_model = [r for r in model if r['classification'] == 'cu']
    assert [len(x) for x in (target, model, cu_target, cu_model)] == [578, 542, 211, 211]
    paths = [ROOT / p for p in FILES.values()] + [FEATURES, QUALIFICATION, AUDIT / 'profile.json', AUDIT / 'record-audit.csv', AUDIT / 'candidate-pairs.csv', AUDIT / 'same-input-groups.json', ROOT / 'scripts/s4_01_profile.py', ROOT / 'scripts/s4_02_freeze.py']
    binding = {'sources': {p.relative_to(ROOT).as_posix(): filehash(p) for p in paths},
               'parent_snapshot_id': parent['snapshot_id'], 'parent_content_sha256': parent['content_sha256'],
               'selection_id': selection['selection_id'], 'feature_snapshot_id': feature_doc['feature_snapshot_id'],
               'qualification_id': qual['qualification_id'], 'rules_version': 's4-02-v1',
               'target': parent['content']['target'], 'target_definition': parent['content']['target_definition'],
               'target_unit': parent['content']['target_unit'], 'split_status': 'not_performed',
               'duplicate_policy': 'exclude all S4-01 identity_unresolved records; no database deletion; prior exact duplicate already excluded',
               'classification_policy': 'S4-01 positive Cu-containing formula components',
               'feature_policy': 'S1-B v4 common eligibility applied equally to F_base F1 F2'}
    write_json(out / 'ledger.json', {'binding': binding, 'records': ledger})
    write_json(out / 'distributions.json', {'all_target': report(target, features), 'all_common': report(model, features), 'cu_target': report(cu_target, features), 'cu_common': report(cu_model, features)})
    for name, targ, eligible in [('all', target, model), ('cu', cu_target, cu_model)]:
        content = {'binding': binding, 'view': name, 'target_record_ids': sorted(r['record_id'] for r in targ),
                   'common_record_ids': sorted(r['record_id'] for r in eligible),
                   'ledger_sha256': filehash(out / 'ledger.json'), 'distributions_sha256': filehash(out / 'distributions.json')}
        h = digest(content)
        write_json(out / f'{name}-view.json', {'view_id': 's4-02-' + name + '-' + h, 'content_sha256': h, 'content': content})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
