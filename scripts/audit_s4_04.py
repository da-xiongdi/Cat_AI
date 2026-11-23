"""Read-only S4-04 evidence audit; writes a new verification report."""
import collections
import json
import math
from pathlib import Path

from catalyst_ai.datasets.split import normalize_doi
from catalyst_ai.modeling.baseline import target_value
from catalyst_ai.modeling.experiments import _predict
from catalyst_ai.modeling.research_preflight import preflight, read_json, sha
from catalyst_ai.modeling.research_run import load_locked_model

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / 'artifacts/reports/s4-04-runs-20261120-v1'
CONFIGS = ROOT / 'artifacts/reports/s4-03-frozen-20261120-v2/configs'
OUT = ROOT / 'artifacts/reports/s4-04-audit-20261120-v3.json'


def close(a, b):
    return math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-10)


def check_metrics(rows, stored):
    errors = [r['observed'] - r['raw_prediction'] for r in rows]
    mean = sum(r['observed'] for r in rows) / len(rows)
    ss = sum((r['observed'] - mean) ** 2 for r in rows)
    vals = {'mae': sum(map(abs, errors)) / len(rows),
            'rmse': math.sqrt(sum(e * e for e in errors) / len(rows)),
            'records': len(rows), 'papers': len({r['doi'] for r in rows})}
    if ss and len(rows) > 1:
        vals['r2'] = 1 - sum(e * e for e in errors) / ss
    by_doi = collections.defaultdict(list)
    for r, e in zip(rows, errors, strict=True):
        by_doi[r['doi']].append(abs(e))
    vals['paper_equal_mae'] = sum(sum(v)/len(v) for v in by_doi.values()) / len(by_doi)
    for k, v in vals.items():
        if k in stored:
            assert close(v, stored[k]), (k, v, stored[k])
    return vals


def audit(run):
    lock, package = load_locked_model(run)
    checked = preflight(run / 'config.json', root=ROOT)
    original = preflight(CONFIGS / (run.name + '.json'), root=ROOT)
    assert checked['config'] == original['config']
    assert checked['hashes'] == original['hashes'] == lock['input_hashes']
    split = checked['split']
    assert split == read_json(run / 'split.json')
    cv = read_json(run / 'cross_validation.json')
    assert cv['selected_index'] == lock['selected_index']
    assert cv['selected_index'] == min(range(len(cv['results'])), key=lambda i: cv['results'][i]['metrics']['mae'])
    assert [r['candidate'] for r in cv['results']] == checked['config']['candidates']
    selected = cv['results'][cv['selected_index']]['candidate']
    assert package['transformer'].feature_set == selected['feature']
    assert type(package['model']).__name__ == 'ExtraTreesRegressor' and selected['model'] == 'extra_trees'
    params = package['model'].get_params()
    assert all(params[k] == v for k, v in selected['params'].items())
    assert params['random_state'] == checked['config']['model_seed']
    for result in cv['results']:
        preds = result['predictions']
        assert len(preds) == len(split['train']) and {r['record_id'] for r in preds} == set(split['train'])
        assert len({r['record_id'] for r in preds}) == len(preds)
        for n, fold in enumerate(split['validation_folds']):
            part = [r for r in preds if r['fold'] == n]
            assert {r['record_id'] for r in part} == set(fold)
            check_metrics(part, result['fold_metrics'][n])
        check_metrics(preds, result['metrics'])
    hold = run / 'holdout'
    assert [p.name for p in run.glob('holdout*') if p.is_dir()] == ['holdout']
    manifest = read_json(hold / 'manifest.json')
    assert set(manifest['files']) == {p.name for p in hold.iterdir() if p.is_file() and p.name != 'manifest.json'}
    for name, expected in manifest['files'].items():
        assert sha(hold / name) == expected, name
    metrics = read_json(hold / 'metrics.json')
    assert metrics['model_sha256'] == lock['artifacts']['model.pkl']
    preds = read_json(hold / 'predictions.json')
    assert len(preds) == len(split['test']) and len({p['record_id'] for p in preds}) == len(preds)
    assert {p['record_id'] for p in preds} == set(split['test'])
    content = checked['snapshot']['content']
    records = {r['record_id']: r for r in content['records']}
    rows = [records[p['record_id']] for p in preds]
    replay = _predict(package['transformer'], package['model'], rows, range(len(rows)))
    for p, record, generated in zip(preds, rows, replay, strict=True):
        assert p['doi'] == normalize_doi(record['payload']['source']['doi'])
        assert close(p['observed'], float(target_value(record, content)))
        assert {k:v for k,v in p.items() if k not in ('record_id','doi','observed')} == json.loads(json.dumps(generated))
    full = check_metrics(preds, metrics['metrics'])
    available = [p for p in preds if p['status'] in ('ok', 'caution')]
    rejected = [p for p in preds if p['status'] not in ('ok', 'caution')]
    reasons = collections.Counter(reason for p in rejected for reason in p['status'].split('+') if reason != 'caution')
    a = metrics['availability']
    assert a['total_records'] == len(preds) and a['available_records'] == len(available)
    assert close(a['available_fraction'], len(available)/len(preds))
    assert a['rejected_records'] == len(rejected) and a['rejection_reasons'] == dict(sorted(reasons.items()))
    assert a['total_papers'] == len({p['doi'] for p in preds})
    assert a['available_papers'] == len({p['doi'] for p in available})
    assert a['unavailable_metrics_reason'] is None
    check_metrics(available, a['available_metrics'])
    return {'run': run.name, 'status': 'pass', 'selected': cv['results'][cv['selected_index']]['candidate']['feature'],
            'train_records': len(split['train']), 'test_records': len(preds), 'test_dois': full['papers'],
            'status_counts': dict(sorted(collections.Counter(p['status'] for p in preds).items())),
            'rejection_reasons': dict(sorted(reasons.items())), 'diagnostic_metrics': full,
            'available_metrics': a['available_metrics'], 'model_sha256': lock['artifacts']['model.pkl'],
            'predictions_sha256': manifest['files']['predictions.json'], 'lock_sha256': sha(run/'lock.json'),
            'holdout_manifest_sha256': sha(hold/'manifest.json')}


def main():
    assert not OUT.exists(), 'audit output already exists'
    expected = {f'EXP-0{e}-{s}' for e in (1,2,3) for s in (42,43,44)}
    runs = {p.name: p for p in RUNS.glob('EXP-*') if p.is_dir()}
    assert set(runs) == expected
    results = []
    for name in sorted(runs):
        try:
            results.append(audit(runs[name]))
        except Exception as exc:
            results.append({'run': name, 'status': 'failed', 'error': repr(exc)})
    OUT.write_text(json.dumps({'schema_version': 1, 'runs': results}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if any(r['status'] != 'pass' for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()

