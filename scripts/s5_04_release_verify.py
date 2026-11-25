"""Validate trusted locked S5 packages with the separately installed wheel."""
import hashlib
import json
import pickle
import platform
from pathlib import Path
import catalyst_ai
import numpy
import sklearn
from catalyst_ai.modeling.s5_selection import predict

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/reports/s5-04-e02-20261124-v1'
assert 'site-packages' in str(Path(catalyst_ai.__file__).resolve())
snapshot=json.loads((ROOT/'data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json').read_text(encoding='utf-8'))
records={r['record_id']:r for r in snapshot['content']['records']}
result={}
for phase in ('fixed','search'):
    for seed in (45,46,47):
        name=f'{phase}-{seed}'; run=OUT/name
        lock=json.loads((run/'lock.json').read_text(encoding='utf-8'))
        for file,expected in lock['artifacts'].items():
            assert hashlib.sha256((run/file).read_bytes()).hexdigest()==expected
        package=pickle.loads((run/'model.pkl').read_bytes())
        old=json.loads((run/'holdout/all_arms.json').read_text(encoding='utf-8'))
        counts=[]
        for arm, saved in zip(package['packages'],old,strict=True):
            assert arm['candidate_index']==saved['candidate_index']
            values=predict(arm['transformer'],arm['model'],[records[r['record_id']] for r in saved['predictions']])
            for a,b in zip(saved['predictions'],values,strict=True):
                assert {k:v for k,v in a.items() if k not in ('record_id','doi','observed')} == json.loads(json.dumps(b))
            counts.append(len(values))
        result[name]={'arms':len(counts),'records_per_arm':counts}
result={'python':platform.python_version(),'numpy':numpy.__version__,'sklearn':sklearn.__version__,'installed_module':str(catalyst_ai.__file__),'runs':result}
(OUT/'release-verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
