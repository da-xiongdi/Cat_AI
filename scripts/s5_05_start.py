from pathlib import Path
import hashlib, sqlite3
from catalyst_ai.workbench import backup, index, service
from catalyst_ai.storage.workbench import atomic_operations
root=Path.cwd(); db=root/'data/workbench.sqlite'; dest=root/'backups/s5-05-start-20261124-v1'; dest.mkdir(parents=True,exist_ok=False)
backup.backup_database(db,dest/'before.sqlite'); backup.backup_database(dest/'before.sqlite',dest/'rehearsal.sqlite')
def run(d):
 with atomic_operations(d):
  assert all(service.get_task(d,x)['status']=='done' for x in ('S5-02','S5-03','S5-04'))
  index.register(d,'cat-ai','S5-05-research-decision-v1','document','docs/s5_05_research_decision_v1.md',request_id='s5-05-start-v1:decision',actor='Codex')
  index.scan(d,'cat-ai',document_ids=['S5-05-research-decision-v1'])
  t=service.get_task(d,'S5-05'); assert t['status']=='planned'
  t=service.transition(d,'S5-05',t['revision'],'ready',request_id='s5-05-start-v1:ready',actor='Codex')
  t=service.transition(d,'S5-05',t['revision'],'in_progress',request_id='s5-05-start-v1:start',actor='Codex')
 with sqlite3.connect(d) as c:
  assert c.execute('pragma quick_check').fetchone()[0]=='ok' and not c.execute('pragma foreign_key_check').fetchall()
 return t['status']
print('rehearsal',run(dest/'rehearsal.sqlite')); print('formal',run(db)); print('decision sha256',hashlib.sha256((root/'docs/s5_05_research_decision_v1.md').read_bytes()).hexdigest())
