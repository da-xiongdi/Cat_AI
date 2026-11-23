import pathlib,hashlib,sqlite3,json
from catalyst_ai.workbench import backup,research_nodes
root=pathlib.Path.cwd(); out=root/'artifacts/wb14-06-evidence'; db=out/'protection.sqlite'
paths={p for d in ['data/raw','data/staged','data/curated','data/snapshots','artifacts/models','artifacts/runs'] for p in (root/d).rglob('*') if p.is_file()}; paths.add(root/'data/catalog.sqlite')
with sqlite3.connect(root/'data/workbench.sqlite') as c:
 paths.update(root/r[0] for r in c.execute("select l.path from artifact_location l join artifact a on a.id=l.artifact_id where a.kind='features'"))
def hashes(): return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if p.is_file()}
before=hashes(); backup.backup_database(root/'data/workbench.sqlite',db)
with sqlite3.connect(db) as c:
 c.row_factory=sqlite3.Row; n=dict(c.execute("select * from research_node where stage='C' and parent_id is null").fetchone())
f={k:n[k] for k in ['stage','source_path','source_section','source_sha256']}; f.update(parent_id=n['id'],sort_order=9998)
research_nodes.save_research_node(db,'cat-ai','wb14-protection',f,0,'隔离保护检查',request_id='wb14-protection',actor='Codex')
after=hashes(); assert before==after
(out/'protection.json').write_text(json.dumps({'count':len(before),'unchanged':True,'sha256':before},ensure_ascii=False,indent=2),encoding='utf8'); print('protected files unchanged',len(before))
