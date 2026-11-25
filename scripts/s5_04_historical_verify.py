"""Revalidate historical packages in their original locked source environment."""
import hashlib
import json
from pathlib import Path
from catalyst_ai.modeling.research_run import load_locked_model, code_hash
from catalyst_ai.modeling.experiments import _predict
from catalyst_ai.modeling.predictor import load_package, predict_batch

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/reports/s5-04-e02-20261124-v1'
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
assert code_hash()=='3101069f67405f02c4280a4d9675b8ea3ef66b75d6a6e10bf1f6ea77ef105f4a'
snap=read(ROOT/'data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json')
rows={r['record_id']:r for r in snap['content']['records']}
runs={}
for run in sorted((ROOT/'artifacts/reports/s4-04-runs-20261120-v1').glob('EXP-*')):
    lock,pkg=load_locked_model(run)
    before=read(run/'holdout/predictions.json'); selected=[rows[r['record_id']] for r in before]
    results=_predict(pkg['transformer'],pkg['model'],selected,range(len(selected)))
    for a,b in zip(before,results,strict=True):
        assert {k:v for k,v in a.items() if k not in ('record_id','doi','observed')} == json.loads(json.dumps(b))
    runs[run.name]={'records':len(before),'lock_sha256':sha(run/'lock.json'),'status':'pass'}
assert len(runs)==9
history={}
for name in ('formal-r1','formal-r2'):
    d=ROOT/'artifacts/reports/s3-02-20261118-02a'; scenario=read(d/'scenarios.json')[name]
    items=read(d/f'{name}-input.json'); expected=[r['prediction'] for r in read(d/f'{name}-checks.json')]
    actual=predict_batch(load_package(ROOT/scenario['package']),items)
    assert json.loads(json.dumps(actual)) == expected
    history[name]={'records':len(actual),'status':'pass','manifest_sha256':sha(ROOT/scenario['package']/'manifest.json')}
d=ROOT/'artifacts/reports/themecat-r1-prediction-20261112-final'
actual=predict_batch(load_package(ROOT/'artifacts/models/themecat-r1-prediction-20261112-final'),read(d/'validation-input.json'))
assert json.loads(json.dumps(actual))==read(d/'validation-predictions.json')
history['historical-r1']={'records':len(actual),'status':'pass'}
(OUT/'historical-verification.json').write_text(json.dumps({'source_code_sha256':code_hash(),'runs':runs,'packages':history},indent=2)+'\n',encoding='utf-8')
