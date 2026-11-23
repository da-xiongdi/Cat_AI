"""Descriptive comparison of the locked S4-04 holdout results."""
import collections
import csv
import hashlib
import itertools
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'artifacts/reports/s4-04-runs-20261120-v1'
FROZEN = ROOT / 'artifacts/reports/s4-03-frozen-20261120-v2'
AUDIT = ROOT / 'artifacts/reports/s4-04-audit-20261120-v3.json'
OUT = ROOT / 'artifacts/reports/s4-04-comparison-20261120-v1'

def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def mean(x):
    return statistics.mean(x) if x else None

def metric(rows):
    return mean([abs(x['observed'] - x['raw_prediction']) for x in rows])

def overlap(a, b):
    return {'a': len(a), 'b': len(b), 'intersection': len(a & b), 'union': len(a | b),
            'jaccard': len(a & b) / len(a | b) if a | b else None}

def main():
    OUT.mkdir(parents=True, exist_ok=False)
    audit = read(AUDIT)
    assert len(audit['runs']) == 9 and all(r['status'] == 'pass' for r in audit['runs'])
    runs = {}
    for item in audit['runs']:
        name = item['run']
        path = RUN / name
        assert sha(path / 'holdout/predictions.json') == item['predictions_sha256']
        assert sha(path / 'model.pkl') == item['model_sha256']
        assert sha(path / 'lock.json') == item['lock_sha256']
        assert sha(path / 'holdout/manifest.json') == item['holdout_manifest_sha256']
        split = read(path / 'split.json')
        preds = read(path / 'holdout/predictions.json')
        assert len(preds) == len({r['record_id'] for r in preds}) and {r['record_id'] for r in preds} == set(split['test'])
        runs[name] = {'split': split, 'preds': {r['record_id']:r for r in preds},
                      'selected': item['selected']}
    coverage = read(FROZEN / 'coverage.json')['seeds']
    result = {'method': 'delta = absolute error EXP-03 minus EXP-02; negative favors EXP-03',
              'audit_sha256': sha(AUDIT), 'coverage_sha256': sha(FROZEN/'coverage.json'),
              'paired': {}, 'overlap_between_seeds': {}, 'protocol_comparison': {}}
    csvrows = []
    for seed in (42, 43, 44):
        a, b = (runs[f'EXP-0{i}-{seed}'] for i in (2,3))
        s2, s3 = a['split'], b['split']
        test = set(s3['test'])
        assert test <= set(s2['test']) and set(s3['train']) <= set(s2['train'])
        assert set(s3['train']).isdisjoint(set(s2['test']))
        pairs = []
        for rid in sorted(test):
            x, y = a['preds'][rid], b['preds'][rid]
            assert x['observed'] == y['observed'] and x['doi'] == y['doi']
            e2, e3 = abs(x['observed']-x['raw_prediction']), abs(y['observed']-y['raw_prediction'])
            row = {'seed': seed, 'record_id': rid, 'doi': x['doi'], 'observed': x['observed'],
                   'exp02_prediction': x['raw_prediction'], 'exp03_prediction': y['raw_prediction'],
                   'exp02_status': x['status'], 'exp03_status': y['status'],
                   'exp02_absolute_error': e2, 'exp03_absolute_error': e3, 'delta_exp03_minus_exp02': e3-e2,
                   'joint_available': x['status'] in ('ok','caution') and y['status'] in ('ok','caution')}
            pairs.append(row); csvrows.append(row)
        def summary(rs):
            ds = [r['delta_exp03_minus_exp02'] for r in rs]
            bydoi = collections.defaultdict(list)
            for r in rs: bydoi[r['doi']].append(r['delta_exp03_minus_exp02'])
            return {'records':len(rs), 'dois':len(bydoi),
                    'exp02_mae':mean([r['exp02_absolute_error'] for r in rs]),
                    'exp03_mae':mean([r['exp03_absolute_error'] for r in rs]),
                    'mean_delta':mean(ds), 'median_delta':statistics.median(ds) if ds else None,
                    'doi_equal_delta':mean([mean(v) for v in bydoi.values()]),
                    'exp03_lower_error':sum(d<0 for d in ds), 'exp02_lower_error':sum(d>0 for d in ds),
                    'ties':sum(d==0 for d in ds),
                    'doi_counts':dict(sorted(collections.Counter(r['doi'] for r in rs).items())),
                    'doi_mean_deltas':{k:mean(v) for k,v in sorted(bydoi.items())}}
        result['paired'][str(seed)] = {'all_diagnostic':summary(pairs),
            'joint_available':summary([r for r in pairs if r['joint_available']]),
            'selected_features':{'exp02':a['selected'], 'exp03':b['selected']},
            'exp02_train':len(s2['train']), 'exp03_train':len(s3['train'])}
        one, two = (runs[f'EXP-0{i}-{seed}'] for i in (1,2))
        t1, t2 = set(one['split']['test']), set(two['split']['test'])
        common = t1 & t2
        cv1, cv2 = coverage[str(seed)]['EXP-01'], coverage[str(seed)]['EXP-02']
        result['protocol_comparison'][str(seed)] = {
            'test_overlap':overlap(t1,t2), 'common_test_mae':{'records':len(common),
                'exp01':metric([one['preds'][i] for i in common]),
                'exp02':metric([two['preds'][i] for i in common])},
            'train_overlap':overlap(set(one['split']['train']),set(two['split']['train'])),
            'exp01':{k:cv1[k] for k in ('train','test')},
            'exp02':{k:cv2[k] for k in ('train','test')},
            'test_doi_overlap_train':{
                'exp01':len(set(cv1['test']['doi_records']) & set(cv1['train']['doi_records'])),
                'exp02':len(set(cv2['test']['doi_records']) & set(cv2['train']['doi_records']))}}
    for exp in (1,2,3):
        byseed = {s:set(runs[f'EXP-0{exp}-{s}']['split']['test']) for s in (42,43,44)}
        result['overlap_between_seeds'][f'EXP-0{exp}'] = {
            'pairs':{f'{a}-{b}':overlap(byseed[a],byseed[b]) for a,b in itertools.combinations(byseed,2)},
            'all_three':len(set.intersection(*byseed.values())), 'any':len(set.union(*byseed.values()))}
    with (OUT/'paired_records.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(csvrows[0])); w.writeheader(); w.writerows(csvrows)
    (OUT/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'paired':result['paired'], 'overlaps':result['overlap_between_seeds'],
                      'protocol':{s:{'test_overlap':p['test_overlap'],'common_test_mae':p['common_test_mae'],
                      'train_overlap':p['train_overlap'],'test_doi_overlap_train':p['test_doi_overlap_train'],
                      'coverage':{e:{k:{z:v[z] for z in ('records','groups','dois','compositions','ranges')} for k,v in p[e].items()} for e in ('exp01','exp02')}} for s,p in result['protocol_comparison'].items()}},ensure_ascii=False,indent=2))

if __name__ == '__main__': main()
