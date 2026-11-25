import json
from pathlib import Path
import catalyst_ai
from catalyst_ai.modeling.research_run import load_locked_model
from catalyst_ai.modeling.s5_selection import predict
root=Path(__file__).resolve().parents[1]
assert 'site-packages' in str(Path(catalyst_ai.__file__).resolve())
base=root/'artifacts/reports/s5-04-xgboost-official-20261124-v1/synthetic'
lock,pkg=load_locked_model(base/'run')
snapshot=json.loads((base/'snapshot.json').read_text(encoding='utf8'))
records={r['record_id']:r for r in snapshot['content']['records']}
arms=json.loads((base/'run/holdout/all_arms.json').read_text(encoding='utf8'))
for package,arm in zip(pkg['packages'],arms,strict=True):
    rows=[records[p['record_id']] for p in arm['predictions']]
    predictions=predict(package['transformer'],package['model'],rows)
    for actual,saved in zip(predictions,arm['predictions'],strict=True):
        assert json.loads(json.dumps(actual))=={k:v for k,v in saved.items() if k not in ('record_id','doi','observed')}
(base/'release-result.json').write_text(json.dumps({'installed_module':str(catalyst_ai.__file__),'formal_lock_match':True,'arms':len(arms),'predictions_per_arm':[len(a['predictions']) for a in arms]},indent=2)+'\n',encoding='utf8')
print('Independent installed wheel formal lock and predictions passed')
