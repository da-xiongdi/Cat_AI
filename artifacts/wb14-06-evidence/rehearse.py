import sqlite3, pathlib, json, hashlib, zipfile
from catalyst_ai.workbench import backup, research_nodes
root=pathlib.Path.cwd(); out=root/'artifacts/wb14-06-evidence'; db=out/'rehearsal-v2.sqlite'
backup.backup_database(root/'data/workbench.sqlite',db)
with sqlite3.connect(db) as c:
 c.row_factory=sqlite3.Row
 node=dict(c.execute("select * from research_node where parent_id is null and stage='C'").fetchone())
 def snap(): return {t:sorted(c.execute('select * from "'+t+'"').fetchall(),key=repr) for (t,) in c.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'").fetchall()}
 c.row_factory=None
 before=snap()
fields={k:node[k] for k in ('stage','source_path','source_section','source_sha256')}; fields.update(parent_id=node['id'],sort_order=9999)
research_nodes.save_research_node(db,'cat-ai','WB14-rehearsal-node',fields,0,'隔离验收',request_id='wb14-rehearsal-create',actor='acceptance')
with sqlite3.connect(db) as c:
 def snap(): return {t:sorted(c.execute('select * from "'+t+'"').fetchall(),key=repr) for (t,) in c.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'").fetchall()}
 after=snap()
 changed=[t for t in before if before[t]!=after[t]]
 print('changed',changed)
 assert set(changed)<= {'research_node','research_node_revision','activity','request_log'}
content=backup.create_bundle(db,root); (out/'rehearsal-bundle.zip').write_bytes(content)
p=backup.preview_bundle(content); backup.restore_bundle(content,out/'restored',p['sha256'])
with sqlite3.connect(out/'restored/workbench.sqlite') as c:
 restored={t:sorted(c.execute('select * from "'+t+'"').fetchall(),key=repr) for t in after}
 for t in after:
  if t!='index_workspace': assert after[t]==restored[t],t
 assert not c.execute('pragma foreign_key_check').fetchall()
 assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
 print('tables compared',len(after),'missing',p['manifest']['missing'])
report={'changed_tables':changed,'tables_compared':len(after),'index_workspace':'root relocated by restore','integrity':'ok','foreign_key_errors':0,'bundle_sha256':p['sha256'],'missing':p['manifest']['missing']}
(out/'restore-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')

