"""Exercise mixed batch failure and explicit retry on the frozen real dataset."""
import json
from pathlib import Path
from catalyst_ai.modeling import research_run

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/reports/s5-04-e02-20261124-v1/batch-verification'
OUT.mkdir(exist_ok=False)
configs=OUT/'configs'; configs.mkdir()
base=json.loads((ROOT/'artifacts/reports/s5-04-e02-20261124-v1/configs/fixed-45.json').read_text(encoding='utf-8'))
good=dict(base, candidates=base['candidates'][:3])
bad=dict(good, split_sha256='0'*64)
for name,value in [('valid',good),('invalid',bad)]:
    (configs/f'{name}.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
batch=research_run.fit_batch(configs, OUT/'batch', root=ROOT)
assert [r['status'] for r in batch] == ['failed','completed']
assert (OUT/'batch/invalid/failure.log').is_file()
retry_config=OUT/'retry.json'; retry_config.write_text(json.dumps(good,indent=2)+'\n',encoding='utf-8')
research_run.fit(retry_config,OUT/'retry',root=ROOT)
original=research_run._score_holdout
def fail(*args): raise OSError('injected scoring failure for retry verification')
research_run._score_holdout=fail
try:
    try: research_run.score(OUT/'retry',root=ROOT)
    except OSError: pass
    else: raise AssertionError('injected failure not observed')
    assert (OUT/'retry/holdout/failure.log').is_file()
finally: research_run._score_holdout=original
try: research_run.score(OUT/'retry',root=ROOT)
except FileExistsError: pass
else: raise AssertionError('implicit retry was accepted')
research_run.score(OUT/'retry',root=ROOT,retry=True)
result=OUT/'retry/holdout-retry-001'
assert (result/'manifest.json').is_file()
arms=json.loads((result/'all_arms.json').read_text(encoding='utf-8'))
reference=json.loads((ROOT/'artifacts/reports/s5-04-e02-20261124-v1/fixed-45/holdout/all_arms.json').read_text(encoding='utf-8'))
assert arms == reference[:3]
(OUT/'verification.json').write_text(json.dumps({'batch':batch,'failure_preserved':True,'implicit_retry_rejected':True,'explicit_retry_complete':True,'all_arms_match_fixed_run':True,'holdout_records_per_arm':[len(a['predictions']) for a in arms]},indent=2)+'\n',encoding='utf-8')
