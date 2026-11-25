"""Post-review descriptive recalculation from frozen predictions; no model selection."""
import json, math, statistics
from collections import defaultdict, Counter
from pathlib import Path
from catalyst_ai.modeling.s5_selection import _available
from catalyst_ai.modeling.s5_metrics import compare

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'artifacts/reports/s5-04-e02-20261124-v1'
OUT=ROOT/'artifacts/reports/s5-04-remediation-20261124-v1'
OUT.mkdir(parents=True,exist_ok=True)
def read(p): return json.loads(p.read_text(encoding='utf8'))
def calc(rows):
    valid=[r for r in rows if isinstance(r.get('raw_prediction'),(int,float)) and math.isfinite(r['raw_prediction'])]
    groups=defaultdict(list)
    for r in valid: groups[r['doi']].append(abs(r['observed']-r['raw_prediction']))
    return {'total':len(rows),'diagnostic_finite':len(valid),'status_counts':dict(Counter(r['status'] for r in rows)), 'available':sum(_available(r) for r in rows), 'papers_with_finite_prediction':len(groups), 'paper_equal_mae':statistics.mean(statistics.mean(v) for v in groups.values()) if groups else None}
def strata(rows):
    d=defaultdict(list)
    for r in rows: d[r['doi']].append(r)
    return {doi:{**calc(g),'available_mae':statistics.mean(abs(r['observed']-r['raw_prediction']) for r in g if _available(r)) if any(_available(r) for r in g) else None} for doi,g in sorted(d.items())}
output={}
for phase in ('fixed','search'):
 for seed in (45,46,47):
    name=f'{phase}-{seed}'; run=OLD/name
    cv=read(run/'cross_validation.json'); held=read(run/'holdout/all_arms.json'); prior=read(OLD/f'{name}-metrics.json')
    oof={str(i):x['predictions'] for i,x in enumerate(cv['results'])}; hold={str(x['candidate_index']):x['predictions'] for x in held}
    reports={}; stability={}
    for stage,arms in [('oof',oof),('holdout',hold)]:
        report=compare(arms)
        assert report==prior[stage], f'{name} {stage} differs from frozen report'
        for section in [report['overall'],*report.get('folds',{}).values()]:
            section['common_count']=len(section['common_ids']); section['common_coverage']=len(section['common_ids'])/section['denominator']
        reports[stage]=report
        if stage=='oof':
            for arm in arms:
                stability[arm]={}
                for metric in ('mae','rmse','r2'):
                    vals=[f['arms'][arm]['common'][metric] for f in report['folds'].values() if f['arms'][arm]['common'][metric] is not None]
                    stability[arm][metric]={'folds_with_value':len(vals),'mean':statistics.mean(vals) if vals else None,'population_sd':statistics.pstdev(vals) if vals else None,'min':min(vals) if vals else None,'max':max(vals) if vals else None}
    output[name]={'metrics':reports,'fold_stability_common':stability,'oof_doi':{k:strata(v) for k,v in oof.items()},'holdout_diagnostics':{k:calc(v) for k,v in hold.items()},'historical_fold_timing':{str(i):x['fold_timing'] for i,x in enumerate(cv['results'])}}
(OUT/'recomputed-report.json').write_text(json.dumps(output,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
print('Verified original metrics and generated supplemental reports for',len(output),'runs')
