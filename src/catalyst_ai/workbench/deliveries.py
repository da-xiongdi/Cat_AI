"""Historical workbench delivery references and source-backed registration preview."""

import hashlib
import re
import uuid

from catalyst_ai.storage.workbench import connect, now
from catalyst_ai.workbench.adapters import safe_path
from catalyst_ai.workbench.service import Conflict, Missing, _json, _text, _write


def _inspect(root, path, section, expected_hash=None):
    try:
        raw = safe_path(root, path).read_bytes()
        content = raw.decode("utf-8-sig")
        headings = re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", content, re.MULTILINE)
        if headings.count(section) != 1:
            return "section_missing_or_ambiguous"
        if expected_hash and hashlib.sha256(raw).hexdigest() != expected_hash:
            return "changed"
        return "valid"
    except (OSError, ValueError, UnicodeError):
        return "missing_or_invalid"


def preview_historical_deliveries(path, project_id):
    """Read the current scope table; no task or delivery is created."""
    db = connect(path)
    try:
        workspace = db.execute(
            "SELECT root FROM index_workspace WHERE project_id=?", (project_id,)
        ).fetchone()
        if not workspace:
            raise Missing("workspace not configured")
        source = "docs/architecture/project_workbench_plan.md"
        section = "2.1 既有建设进度承接"
        raw = safe_path(workspace["root"], source).read_bytes()
        content = raw.decode("utf-8-sig")
        if _inspect(workspace["root"], source, section) != "valid":
            raise ValueError("source section missing or ambiguous")
        body = content.split("### " + section, 1)[1].split("\n### ", 1)[0]
        digest = hashlib.sha256(raw).hexdigest()
        existing = {
            r["original_wb_id"]: dict(r)
            for r in db.execute(
                "SELECT * FROM workbench_delivery WHERE project_id=?", (project_id,)
            )
        }
        entries = []
        for line in body.splitlines():
            match = re.match(r"^\|\s*(WB-\d{2})\s+[^|]*\|\s*([^|]+)\|\s*([^|]+)\|", line)
            if not match:
                continue
            wb_id, delivered, remaining = match.groups()
            old = existing.get(wb_id)
            entries.append(
                {
                    "original_wb_id": wb_id,
                    "delivered_scope": delivered.strip(),
                    "remaining_scope": remaining.strip(),
                    "source_path": source,
                    "source_section": section,
                    "source_sha256": digest,
                    "registration": "registered" if old else "pending_registration",
                    "existing_revision": old["revision"] if old else None,
                }
            )
        if len(entries) != 12 or len({e["original_wb_id"] for e in entries}) != 12:
            raise ValueError("historical scope table incomplete")
        return entries
    finally:
        db.close()


def list_historical_deliveries(path, project_id):
    db = connect(path)
    try:
        workspace = db.execute(
            "SELECT root FROM index_workspace WHERE project_id=?", (project_id,)
        ).fetchone()
        rows = []
        for row in db.execute(
            "SELECT * FROM workbench_delivery WHERE project_id=? ORDER BY original_wb_id",
            (project_id,),
        ):
            item = dict(row)
            item["source_status"] = (
                _inspect(
                    workspace["root"],
                    item["source_path"],
                    item["source_section"],
                    item["source_sha256"],
                )
                if workspace
                else "missing_or_invalid"
            )
            item["registration_status"] = (
                "registered" if item["task_id"] else "historical_pending_task_registration"
            )
            rows.append(item)
        return rows
    finally:
        db.close()


def upsert_workbench_delivery(
    path, project_id, data, expected_revision, reason, *, request_id, actor
):
    fields = (
        "original_wb_id",
        "delivered_scope",
        "remaining_scope",
        "source_path",
        "source_section",
        "source_sha256",
    )
    values = {key: _text(data.get(key), key) for key in fields}
    if not re.fullmatch(r"WB-\d{2}", values["original_wb_id"]) or not re.fullmatch(
        r"[0-9a-f]{64}", values["source_sha256"]
    ):
        raise ValueError("invalid WB ID or source hash")
    values.update(
        original_delivered_at=data.get("original_delivered_at"),
        task_id=data.get("task_id"),
        active=data.get("active", 1),
    )
    if values["active"] not in (0, 1):
        raise ValueError("invalid active flag")
    reason = _text(reason, "reason")

    def run(db, actor):
        workspace = db.execute(
            "SELECT root FROM index_workspace WHERE project_id=?", (project_id,)
        ).fetchone()
        if not workspace:
            raise Missing("workspace not configured")
        old = db.execute(
            "SELECT * FROM workbench_delivery WHERE project_id=? AND original_wb_id=?",
            (project_id, values["original_wb_id"]),
        ).fetchone()
        if (old["revision"] if old else 0) != expected_revision:
            raise Conflict("delivery revision conflict")
        if values["task_id"]:
            task = db.execute(
                "SELECT project_id,category FROM task WHERE id=?", (values["task_id"],)
            ).fetchone()
            if not task or task["project_id"] != project_id or task["category"] != "workbench":
                raise ValueError("task must belong to project and be workbench category")
        old_data = dict(old) if old else None
        if old and all(old[k] == v for k, v in values.items()):
            return old_data
        if (
            _inspect(
                workspace["root"],
                values["source_path"],
                values["source_section"],
                values["source_sha256"],
            )
            != "valid"
        ):
            raise Conflict("source requires review")
        entity_id = old["id"] if old else str(uuid.uuid4())
        revision = expected_revision + 1
        registered_at = old["registered_at"] if old else now()
        if old:
            db.execute(
                "UPDATE workbench_delivery SET delivered_scope=?,remaining_scope=?,source_path=?,"
                "source_section=?,source_sha256=?,original_delivered_at=?,task_id=?,"
                "active=?,revision=? WHERE id=?",
                (
                    values["delivered_scope"],
                    values["remaining_scope"],
                    values["source_path"],
                    values["source_section"],
                    values["source_sha256"],
                    values["original_delivered_at"],
                    values["task_id"],
                    values["active"],
                    revision,
                    entity_id,
                ),
            )
        else:
            db.execute(
                "INSERT INTO workbench_delivery VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    entity_id,
                    project_id,
                    values["original_wb_id"],
                    values["delivered_scope"],
                    values["remaining_scope"],
                    values["source_path"],
                    values["source_section"],
                    values["source_sha256"],
                    values["original_delivered_at"],
                    registered_at,
                    values["task_id"],
                    revision,
                    values["active"],
                ),
            )
        new = dict(
            db.execute("SELECT * FROM workbench_delivery WHERE id=?", (entity_id,)).fetchone()
        )
        db.execute(
            "INSERT INTO workbench_delivery_revision VALUES(?,?,?,?,?,?,?,?)",
            (
                entity_id,
                project_id,
                revision,
                _json(old_data) if old else None,
                _json(new),
                reason,
                actor,
                now(),
            ),
        )
        db.execute(
            "INSERT INTO activity(project_id,task_id,action,actor,created_at,summary) "
            "VALUES(?,?,?,?,?,?)",
            (
                project_id,
                values["task_id"],
                "workbench_delivery_saved",
                actor,
                now(),
                _json({"id": entity_id, "revision": revision, "reason": reason}),
            ),
        )
        return new

    return _write(
        path,
        request_id,
        actor,
        "upsert_workbench_delivery",
        [project_id, values, expected_revision, reason],
        run,
    )
