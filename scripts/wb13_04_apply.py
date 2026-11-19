import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from catalyst_ai.workbench.research_nodes import (
    apply_research_initialization,
    preview_research_nodes,
)

path = Path("data/workbench.sqlite")
stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
evidence = Path("artifacts") / ("wb13-04-" + stamp)
evidence.mkdir()
backup = Path("backups") / ("wb13-04-before-" + stamp + ".sqlite")
fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
os.close(fd)
source = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
target = sqlite3.connect(backup)
source.backup(target)
target.close()
source.close()
copy = evidence / "rehearsal.sqlite"
shutil.copyfile(backup, copy)
preview = preview_research_nodes(copy, "cat-ai")
if preview["warnings"] or len(preview["nodes"]) != 14 or len(preview["link_candidates"]) != 8:
    raise RuntimeError("preview differs from reviewed scope")
by_id = {t["id"]: t for t in preview["tasks"]}
if any(by_id[c["task_id"]]["primary_stage"] != "C" for c in preview["link_candidates"]):
    raise RuntimeError("primary stage requires review")
links = [
    {**c, "id": "cat-ai:node-primary:" + c["task_id"], "expected_revision": 0}
    for c in preview["link_candidates"]
]
if any(n["expected_revision"] != 0 for n in preview["nodes"]):
    raise RuntimeError("existing node requires review")
request = "wb13-04-init-" + str(uuid.uuid4())
reason = "Reviewed stage C task sections and primary stages; WB-13-04 initialization"
(evidence / "preview.json").write_text(
    json.dumps(
        {"preview": preview, "links": links, "request_id": request}, ensure_ascii=False, indent=2
    ),
    encoding="utf-8",
)


def protected(dbpath):
    c = sqlite3.connect(dbpath)
    result = {}
    for table in ("task", "dependency", "criterion", "review", "evidence"):
        rows = c.execute("SELECT * FROM " + table + " ORDER BY rowid").fetchall()
        result[table] = hashlib.sha256(repr(rows).encode()).hexdigest()
    c.close()
    return result


before = protected(copy)
rehearsal = apply_research_initialization(
    copy, "cat-ai", preview["nodes"], links, reason, request_id=request, actor="codex"
)
assert rehearsal == apply_research_initialization(
    copy, "cat-ai", preview["nodes"], links, reason, request_id=request, actor="codex"
)
assert protected(copy) == before
c = sqlite3.connect(copy)
assert c.execute("pragma integrity_check").fetchone()[0] == "ok"
assert not c.execute("pragma foreign_key_check").fetchall()
c.close()
result = apply_research_initialization(
    path, "cat-ai", preview["nodes"], links, reason, request_id=request, actor="codex"
)
c = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
checks = {
    "integrity": c.execute("pragma integrity_check").fetchone()[0],
    "foreign_keys": c.execute("pragma foreign_key_check").fetchall(),
    "nodes": len(result["nodes"]),
    "links": len(result["links"]),
}
c.close()
checks.update(
    {
        "backup": str(backup),
        "rehearsal_protected_before": before,
        "live_protected_after": protected(path),
        "request_id": request,
    }
)
(evidence / "result.json").write_text(
    json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps({"evidence": str(evidence), **checks}, ensure_ascii=False, indent=2))
