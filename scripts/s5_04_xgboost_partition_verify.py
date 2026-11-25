import json
from pathlib import Path
from catalyst_ai.modeling import research_run as rr
root=Path(__file__).resolve().parents[1]
out=root/'artifacts/reports/s5-04-xgboost-official-20261124-v1/partition-validation'
out.mkdir(parents=True,exist_ok=False)
base=json.loads((root/'artifacts/reports/s5-04-e02-20261124-v1/configs/fixed-45.json').read_text(encoding='utf8'))
base['candidates']=[base['candidates'][0], {'feature':'F_base','model':'xgboost','params':{'n_estimators':10,'max_depth':3,'learning_rate':0.1}}]
def write(path,obj): path.write_text(json.dumps(obj,indent=2)+'\n',encoding='utf8')
configs=out/'configs'; configs.mkdir()
write(configs/'valid.json',base)
write(configs/'invalid.json',dict(base,split_sha256='0'*64))
rr.preflight(configs/'valid.json',root=root)
rr.fit(configs/'valid.json',out/'single',root=root)
rr.score(out/'single',root=root)
batch=rr.fit_batch(configs,out/'batch',root=root)
assert [r['status'] for r in batch]==['failed','completed']
assert (out/'batch/invalid/failure.log').is_file()
original=rr._score_holdout
def fail(*args): raise OSError('injected failure')
rr._score_holdout=fail
try:
    try: rr.score(out/'batch/valid',root=root)
    except OSError: pass
    else: raise AssertionError('failure not raised')
finally: rr._score_holdout=original
assert (out/'batch/valid/holdout/failure.log').is_file()
try: rr.score(out/'batch/valid',root=root)
except FileExistsError: pass
else: raise AssertionError('implicit retry accepted')
rr.score(out/'batch/valid',root=root,retry=True)
assert (out/'batch/valid/holdout-retry-001/manifest.json').is_file()
write(out/'verification.json',{'purpose':'software validation only; not a preregistered performance comparison','batch':batch,'failure_preserved':True,'implicit_retry_rejected':True,'explicit_retry_completed':True})
print('Partition validation passed')
