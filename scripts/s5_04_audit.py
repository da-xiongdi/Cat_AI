"""Recompute S5-E02 evidence without changing any model or selection."""
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from catalyst_ai.modeling.research_run import load_locked_model
from catalyst_ai.modeling.s5_selection import _available, predict, select

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'artifacts/reports/s5-04-e02-20261124-v1'
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, obj): p.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n',encoding='utf-8')
snap = read(ROOT/'data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json')
rows = {r['record_id']: r for r in snap['content']['records']}
audit = {}; strata = {}; summary = {}
for phase in ('fixed', 'search'):
    for seed in (45, 46, 47):
        name=f'{phase}-{seed}'; run=OUT/name
        lock, package=load_locked_model(run)
        cv=read(run/'cross_validation.json'); split=read(run/'split.json'); held=read(run/'holdout/all_arms.json')
        assert json.loads(json.dumps(select(cv['results']))) == cv['selection_decision']
        assert set(split['train']).isdisjoint(split['test'])
        assert set().union(*(set(f) for f in split['validation_folds'])) == set(split['train'])
        assert sum(map(len, split['validation_folds'])) == len(split['train'])
        per=[]; strata[name]={}
        for i, (candidate, arm) in enumerate(zip(cv['results'], held, strict=True)):
            assert arm['candidate_index'] == i and set(r['record_id'] for r in candidate['predictions']) == set(split['train'])
            assert set(r['record_id'] for r in arm['predictions']) == set(split['test'])
            for r in candidate['predictions']:
                assert r['record_id'] in split['validation_folds'][r['fold']]
            p = package['packages'][i]; old=arm['predictions']
            new=predict(p['transformer'], p['model'], [rows[r['record_id']] for r in old])
            for a,b in zip(old,new,strict=True):
                assert {k:v for k,v in a.items() if k not in ('record_id','doi','observed')} == json.loads(json.dumps(b))
            per.append({'candidate':i,'reloaded':len(old),'statuses':dict(Counter(r['status'] for r in old))})
            bydoi=defaultdict(list)
            for r in old:
                bydoi[r['doi']].append(r)
            strata[name][str(i)]={doi:{'total':len(group), 'available':sum(_available(x) for x in group),
                'mae': (sum(abs(x['observed']-x['raw_prediction']) for x in group if _available(x))/sum(_available(x) for x in group)) if any(_available(x) for x in group) else None} for doi,group in sorted(bydoi.items())}
        audit[name]={'train':len(split['train']),'holdout':len(split['test']), 'folds':[len(f) for f in split['validation_folds']], 'selected':cv['selected_index'], 'arms':per, 'lock_sha256':sha(run/'lock.json'), 'model_sha256':lock['artifacts']['model.pkl']}
        report=read(OUT/f'{name}-metrics.json')
        summary[name]={'selected':cv['selected_index'], 'candidates':cv['results'] and [r['candidate'] for r in cv['results']],
          'oof':{k:{'coverage':v['coverage'],'individual':v['individual'],'common':v['common']} for k,v in report['oof']['overall']['arms'].items()},
          'holdout':{k:{'coverage':v['coverage'],'individual':v['individual'],'common':v['common']} for k,v in report['holdout']['overall']['arms'].items()}}
write(OUT/'reload-and-membership-audit.json',audit)
write(OUT/'doi-strata.json',strata)
write(OUT/'summary.json',summary)
print(json.dumps({k:{'selected':v['selected'],'arms':len(v['arms']),'train':v['train'],'holdout':v['holdout']} for k,v in audit.items()},indent=2))
