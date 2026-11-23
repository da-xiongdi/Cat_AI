"""Describe S4-04 input support, source concentration and observed errors."""
import collections, csv, hashlib, json, statistics
from pathlib import Path
from catalyst_ai.features.pipeline import project
from catalyst_ai.modeling.research_preflight import preflight

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'artifacts/reports/s4-04-runs-20261120-v1'
AUDIT=ROOT/'artifacts/reports/s4-04-audit-20261120-v3.json'
OUT=ROOT/'artifacts/reports/s4-04-coverage-analysis-20261120-v1'

def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def group_stats(rows):
    if not rows: return {'n':0,'mae':None}
    return {'n':len(rows),'mae':statistics.mean(r['abs_error'] for r in rows)}
def fmt_key(v): return '/'.join(v) if isinstance(v,list) else v

def main():
    audit=read(AUDIT); assert len(audit['runs'])==9 and all(r['status']=='pass' for r in audit['runs'])
    output={'audit_sha256':sha(AUDIT),'runs':{}}
    details=[]
    for item in audit['runs']:
        name=item['run']; path=RUN/name
        assert sha(path/'holdout/predictions.json')==item['predictions_sha256']
        assert sha(path/'lock.json')==item['lock_sha256']
        assert sha(path/'model.pkl')==item['model_sha256']
        x=preflight(path/'config.json',root=ROOT)
        assert x['hashes']==read(path/'lock.json')['input_hashes']
        split=x['split']; records={r['record_id']:r for r in x['snapshot']['content']['records']}
        ids=split['train']+split['test']; projected={i:project(records[i]['payload']) for i in ids}
        def signature(i):
            return tuple(sorted((a,b,v) for (a,b),v in projected[i]['amounts'].items() if v>0))
        train_signatures={signature(i) for i in split['train']}
        train_roles={key for i in split['train'] for key,v in projected[i]['amounts'].items() if v>0}
        conditions=('temperature_k','pressure_bar_abs','h2_co2_ratio','reactants_flow_nl_g_h')
        ranges={k:[min(projected[i]['conditions'][k] for i in split['train']),max(projected[i]['conditions'][k] for i in split['train'])] for k in conditions}
        tests=read(path/'holdout/predictions.json'); assert {r['record_id'] for r in tests}==set(split['test']) and len(tests)==len(split['test'])
        rows=[]
        for p in tests:
            record=projected[p['record_id']]; cond=record['conditions']
            novel=sorted(key for key,v in record['amounts'].items() if v>0 and key not in train_roles)
            outside=[k for k in conditions if not ranges[k][0]<=cond[k]<=ranges[k][1]]
            if item['selected'] in ('F_base','F1','F2'):
                assert {tuple(v) for v in p['unseen_species_roles']}==set(novel)
            row={'record_id':p['record_id'],'doi':p['doi'],'status':p['status'],
                 'observed':p['observed'],'prediction':p['raw_prediction'],'abs_error':abs(p['observed']-p['raw_prediction']),
                 'temperature_k':cond['temperature_k'],'pressure_bar_abs':cond['pressure_bar_abs'],
                 'h2_co2_ratio':cond['h2_co2_ratio'],'flow_nl_g_h':cond['reactants_flow_nl_g_h'],
                 'outside_conditions':outside,'new_role_species':novel,'new_composition':signature(p['record_id']) not in train_signatures,
                 'warnings':[fmt_key(v) for v in p['out_of_range']]}
            rows.append(row)
            details.append({'run':name,**{k:json.dumps(v,ensure_ascii=False) if isinstance(v,list) else v for k,v in row.items()}})
        assert len(rows)==item['test_records']
        species=collections.Counter('/'.join(pair) for r in rows for pair in r['new_role_species'])
        warnings=collections.Counter(w for r in rows for w in r['warnings'])
        dois=collections.defaultdict(list)
        for r in rows: dois[r['doi']].append(r)
        bydoi={k:{**group_stats(v),'error_sum':sum(r['abs_error'] for r in v),
                  'statuses':dict(sorted(collections.Counter(r['status'] for r in v).items())),
                  'unseen_records':sum(bool(r['new_role_species']) for r in v)} for k,v in sorted(dois.items())}
        outcond={k:{'train_range':ranges[k],
                    'test_range':[min(r[k if k!='reactants_flow_nl_g_h' else 'flow_nl_g_h'] for r in rows),max(r[k if k!='reactants_flow_nl_g_h' else 'flow_nl_g_h'] for r in rows)],
                    'below':sum((r[k if k!='reactants_flow_nl_g_h' else 'flow_nl_g_h']<ranges[k][0]) for r in rows),
                    'above':sum((r[k if k!='reactants_flow_nl_g_h' else 'flow_nl_g_h']>ranges[k][1]) for r in rows)} for k in conditions}
        strata={status:group_stats([r for r in rows if r['status']==status]) for status in sorted({r['status'] for r in rows})}
        for flag in ('new_composition','new_role_species','outside_conditions'):
            strata[flag]=group_stats([r for r in rows if r[flag]])
        strata['known_composition']=group_stats([r for r in rows if not r['new_composition']])
        counts=sorted((len(v) for v in dois.values()),reverse=True)
        output['runs'][name]={'selected':item['selected'],'train':len(split['train']),'test':len(rows),
          'conditions':outcond,'train_composition_count':len(train_signatures),
          'test_composition_count':len({signature(i) for i in split['test']}),
          'new_composition_records':sum(r['new_composition'] for r in rows),
          'new_composition_signatures':len({signature(i) for i in split['test']} - train_signatures),
          'new_role_species_records':sum(bool(r['new_role_species']) for r in rows),
          'new_role_species':dict(sorted(species.items())),'warning_counts':dict(sorted(warnings.items())),
          'status_and_coverage_strata':strata,'test_doi_count':len(dois),'largest_doi_count':counts[0],
          'top_4_doi_count':sum(counts[:4]),'doi_stats':bydoi}
    OUT.mkdir(parents=True,exist_ok=False)
    (OUT/'coverage.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    with (OUT/'test_records.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(details[0]));w.writeheader();w.writerows(details)
    print('completed',len(output['runs']),'runs,',len(details),'test predictions')
if __name__=='__main__': main()
