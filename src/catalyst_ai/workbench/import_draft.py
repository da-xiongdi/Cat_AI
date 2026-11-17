"""Preview and transactionally import a reviewed WB-01 draft."""

import hashlib
import subprocess
from pathlib import Path

from catalyst_ai.storage.workbench import now
from catalyst_ai.workbench.schema import ImportDraft
from catalyst_ai.workbench.service import Conflict, _json, _text, _write


def preview(root: Path, manifest: Path):
    root = root.resolve(strict=True)
    raw = manifest.read_bytes()
    draft = ImportDraft.model_validate_json(raw)
    sources = []
    for source in draft.sources:
        target = (root / source.path).resolve()
        if not target.is_relative_to(root):
            raise ValueError("source escapes workspace")
        try:
            content = target.read_bytes()
            sha = hashlib.sha256(content).hexdigest()
            status = "available"
        except FileNotFoundError:
            sha, status = None, "missing"
        sources.append({"id": source.id, "path": source.path, "status": status, "sha256": sha})
    git = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=False
    )
    return {
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "project_id": draft.project_id,
        "sources": sources,
        "tasks": [{"id": t.id, "proposed_status": t.status} for t in draft.tasks],
        "differences": [d.model_dump() for d in draft.differences],
        "git_status": git.stdout if git.returncode == 0 else "unavailable",
    }


def apply(db: Path, root: Path, manifest: Path, expected_sha256: str, *, request_id, actor):
    """Import only new IDs; never overwrite existing tasks or fabricate reviews."""
    actor = _text(actor, "actor")
    details = preview(root, manifest)
    if details["manifest_sha256"] != expected_sha256:
        raise Conflict("manifest changed since preview")
    if any(s["status"] != "available" for s in details["sources"]):
        raise Conflict("source files missing; inspect preview")
    raw = manifest.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise Conflict("manifest changed since preview")
    draft = ImportDraft.model_validate_json(raw)

    def run(conn, actor):
        if not conn.execute("SELECT 1 FROM project WHERE id=?", (draft.project_id,)).fetchone():
            raise ValueError("project not found")
        previous = conn.execute(
            "SELECT summary FROM activity WHERE project_id=? AND action='import_preview'",
            (draft.project_id,),
        ).fetchall()
        import json

        for row in previous:
            if json.loads(row[0]).get("manifest_sha256") == expected_sha256:
                return {"tasks": len(draft.tasks), "manifest_sha256": expected_sha256}
        for task in draft.tasks:
            old = conn.execute("SELECT project_id FROM task WHERE id=?", (task.id,)).fetchone()
            if old:
                raise Conflict(f"task already exists: {task.id}")
        for task in draft.tasks:
            conn.execute(
                "INSERT INTO task(id,project_id,title,goal,deliverables,status,priority,owner,"
                "planned_date,milestone,stages,primary_stage) "
                "VALUES(?,?,?,?,?,'planned',?,?,?,?,?,?)",
                (
                    task.id,
                    draft.project_id,
                    task.title,
                    task.goal,
                    _json([]),
                    "normal",
                    task.owner,
                    task.planned_date,
                    task.milestone,
                    _json(task.stages),
                    task.primary_stage,
                ),
            )
            for number, criterion in enumerate(task.criteria, 1):
                conn.execute(
                    "INSERT INTO criterion VALUES(?,?,?,?,?)",
                    (task.id, 1, f"C{number}", criterion.description, criterion.required),
                )
            conn.execute(
                "INSERT INTO activity(project_id,task_id,action,actor,created_at,summary,revision) "
                "VALUES(?,?,?,?,?,?,1)",
                (
                    draft.project_id,
                    task.id,
                    "draft_imported",
                    actor,
                    now(),
                    _json(
                        {
                            "manifest_sha256": expected_sha256,
                            "proposed_status": task.status,
                            "sources": task.sources,
                        }
                    ),
                ),
            )
        for task in draft.tasks:
            for dep in task.dependencies:
                conn.execute("INSERT INTO dependency VALUES(?,?)", (task.id, dep))
        conn.execute(
            "INSERT INTO activity(project_id,action,actor,created_at,summary) VALUES(?,?,?,?,?)",
            (draft.project_id, "import_preview", actor, now(), _json(details)),
        )
        return {"tasks": len(draft.tasks), "manifest_sha256": expected_sha256}

    return _write(db, request_id, actor, "import_draft", details, run)
