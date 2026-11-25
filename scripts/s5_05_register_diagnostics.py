from pathlib import Path
from catalyst_ai.workbench import index
p=Path('data/workbench.sqlite')
index.register(p,'cat-ai','S5-05-diagnostics-supplement-v1','document','docs/s5_05_diagnostics_supplement_v1.md',request_id='s5-05-diagnostics-v1:register',actor='Codex')
index.scan(p,'cat-ai',document_ids=['S5-05-diagnostics-supplement-v1'])
print('registered')
