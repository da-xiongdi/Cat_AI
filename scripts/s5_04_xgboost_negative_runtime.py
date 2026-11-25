from pathlib import Path
import json,datetime
from catalyst_ai.modeling.research_run import load_locked_model
out=Path('artifacts/reports/s5-04-xgboost-feasibility-v1')
try: load_locked_model(out/'synthetic-package-v1')
except ValueError as e:
 assert str(e)=='runtime or code differs from training';result={'mismatched_original_environment_rejected':str(e),'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
else: raise AssertionError('mismatched runtime accepted')
(out/'negative-runtime-result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');print(result)
