import hashlib,json,sqlite3
from pathlib import Path
from catalyst_ai.workbench import service,index,backup
from catalyst_ai.storage.workbench import atomic_operations
ROOT=Path(__file__).resolve().parents[1]; DB=ROOT/'data/workbench.sqlite'; OUT=ROOT/'artifacts/reports/s5-03-m2-audit-20261124'
FILES={'S5-03-M2-scope':'artifacts/reports/s5-03-m2-audit-20261124/partition_audit.json','S5-03-M2-features':'artifacts/reports/s5-03-m2-audit-20261124/material_records.json','S5-03-M2-report':'artifacts/reports/s5-03-m2-audit-20261124/report.md','S5-03-M2-manifest':'artifacts/reports/s5-03-m2-audit-20261124/evidence-sha256.json','S5-03-M2-reload':'artifacts/reports/s5-03-m2-audit-20261124/full_reload.json','S5-03-M2-historical':'artifacts/reports/s5-03-m2-audit-20261124/historical_replay.json'}
def auth(x): return {'request_id':'s5-03-m2-20261124:'+x,'actor':'Codex'}
def sha(p): return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
def verify():
 manifest=json.loads((OUT/'evidence-sha256.json').read_text(encoding='utf-8')); assert all(sha(p)==h for p,h in manifest['files'].items()); assert len(manifest['files'])>=125
 historical=json.loads((OUT/'historical_replay.json').read_text(encoding='utf-8')); assert len(historical['runs'])==9 and all(x['status']=='pass' for x in historical['runs']); return {i:sha(p) for i,p in FILES.items()}
def submit(db):
 h=verify()
 with atomic_operations(db):
  t=service.get_task(db,'S5-03'); assert t['status']=='in_progress'
  for i,p in FILES.items(): index.register(db,'cat-ai',i,'document' if p.endswith('.md') else 'attachment',p,**auth('register:'+i))
  index.scan(db,'cat-ai',document_ids=list(FILES))
  criteria=[{'criterion_id':c,'passed':True,'evidence_id':i,'evidence_version':h[i],'explanation':e} for c,i,e in [('copper_scope','S5-03-M2-scope','Partition and eligibility audit; record evidence and frozen manifest are registered separately.'),('copper_features','S5-03-M2-features','Nominal catalog evidence, formula applicability and per-record reasons; full reload is registered separately.'),('paired_or_gap','S5-03-M2-report','Paired results, training-side decisions, availability, and prior holdout exposure are documented; manifest binds the complete evidence.')]]
  result=service.submit_review(db,'S5-03',t['revision'],criteria,'S5-03 M2 evidence submitted for research review; prior holdout exposure and source limitations are disclosed.',**auth('submit')); assert result['status']=='in_review'; assert verify()==h
 with sqlite3.connect(db) as c:
  assert c.execute('pragma integrity_check').fetchone()[0]=='ok' and not c.execute('pragma foreign_key_check').fetchall()
 return result
if __name__=='__main__':
 backup.backup_database(DB,OUT/'workbench-before.sqlite'); backup.backup_database(OUT/'workbench-before.sqlite',OUT/'workbench-rehearsal.sqlite'); print('rehearsal',submit(OUT/'workbench-rehearsal.sqlite')); print('formal',submit(DB))
