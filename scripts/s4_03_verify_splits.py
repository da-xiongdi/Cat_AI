"""Audit preliminary partitions without reading prediction or model results."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from catalyst_ai.datasets.research_split import partition
from catalyst_ai.reporting.evidence import write_json
from s4_01_profile import ROOT, profile


def main(directory, output):
    _, rows, _, _ = profile()
    rows = {r['record_id']: r for r in rows}
    base = ROOT / 'artifacts/reports/s4-02-20261120-v1'
    views = [json.loads((base / f'{x}-view.json').read_text(encoding='utf-8')) for x in ('all', 'cu')]
    all_ids, cu = [set(v['content']['common_record_ids']) for v in views]
    result = {'status': 'preliminary', 'training_performed': False, 'seeds': {}}
    for seed in (42, 43, 44):
        manifests = {name: json.loads((directory / f'{name}-{seed}.json').read_text(encoding='utf-8')) for name in ('EXP-01', 'EXP-02', 'EXP-03')}
        entries = {}
        for name, p in manifests.items():
            pool = cu if name == 'EXP-03' else all_ids
            train, test = set(p['train']), set(p['test'])
            if train & test or train | test != pool:
                raise ValueError(f'{name}: invalid membership')
            flat = [x for fold in p['validation_folds'] for x in fold]
            if len(flat) != len(set(flat)) or set(flat) != train or len(p['validation_folds']) != 5:
                raise ValueError(f'{name}: invalid folds')
            for group in p['groups']:
                group = set(group)
                if group & train and group & test or sum(bool(group & set(f)) for f in p['validation_folds']) > 1:
                    raise ValueError(f'{name}: split group')
            if name != 'EXP-03':
                inputs = [dict(rows[i], repeat_group=rows[i]['confirmed_repeat_group']) for i in pool]
                expected = partition(inputs, strategy=p['strategy'], seed=seed)
                if any(p[k] != expected[k] for k in expected):
                    raise ValueError(f'{name}: replay mismatch')
            if name == 'EXP-01':
                if {rows[i]['doi'] for i in train} & {rows[i]['doi'] for i in test}:
                    raise ValueError('DOI leakage')
                if any({rows[i]['doi'] for i in fold} & {rows[i]['doi'] for i in train - set(fold)} for fold in p['validation_folds']):
                    raise ValueError('DOI fold leakage')
            def coverage(ids):
                subset = [rows[i] for i in sorted(ids)]
                return {'records': len(ids), 'groups': sum(bool(set(g) & set(ids)) for g in p['groups']),
                        'dois': len({r['doi'] for r in subset}),
                        'doi_records': dict(sorted(Counter(r['doi'] for r in subset).items())),
                        'compositions': len({r['composition'] for r in subset}),
                        'ranges': {k: [min(r[k] for r in subset), max(r[k] for r in subset)] for k in ('temperature_k', 'pressure_bar_abs', 'h2_co2_ratio', 'flow_nl_g_h')}}
            entries[name] = {'train': coverage(train), 'test': coverage(test),
                             'folds': [coverage(f) for f in p['validation_folds']],
                             'sha256': hashlib.sha256((directory / f'{name}-{seed}.json').read_bytes()).hexdigest()}
        if set(manifests['EXP-02']['test']) & cu != set(manifests['EXP-03']['test']) or set(manifests['EXP-02']['train']) & cu != set(manifests['EXP-03']['train']):
            raise ValueError('Cu projection mismatch')
        if any(set(a) & cu != set(b) for a, b in zip(manifests['EXP-02']['validation_folds'], manifests['EXP-03']['validation_folds'], strict=True)):
            raise ValueError('Cu fold projection mismatch')
        c = entries['EXP-03']
        c['threshold_passed'] = c['train']['records'] >= 100 and c['train']['groups'] >= 5 and c['test']['records'] >= 20 and c['test']['groups'] >= 20
        result['seeds'][str(seed)] = entries
    write_json(output, result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    main(args.directory, args.output)
