"""Document purposes and versioned task plan references."""

import hashlib
import re
import sqlite3
import uuid

from catalyst_ai.storage.workbench import connect, now
from catalyst_ai.workbench.adapters import safe_path
from catalyst_ai.workbench.research_nodes import _save
from catalyst_ai.workbench.service import Conflict, Missing, _json, _text, _write

PURPOSES = ("construction_plan", "research_plan", "execution_plan", "acceptance")


def _document(db, project_id, document_id, path=None, *, check_path=True):
    row = db.execute("SELECT * FROM artifact WHERE id=?", (document_id,)).fetchone()
    if not row or row["project_id"] != project_id or row["kind"] != "document":
        raise ValueError("document does not belong to project")
    workspace = db.execute(
        "SELECT root FROM index_workspace WHERE project_id=?", (project_id,)
    ).fetchone()
    if not workspace:
        raise Missing("workspace not configured")
    if path is not None:
        if check_path:
            safe_path(workspace["root"], path)
        if not db.execute(
            "SELECT 1 FROM artifact_location WHERE artifact_id=? AND path=?", (document_id, path)
        ).fetchone():
            raise ValueError("document path is not registered")
    return workspace["root"]


def _inspect(root, path, section):
    try:
        resolved = safe_path(root, path)
    except ValueError:
        return "path_escape", None
    except OSError:
        return "missing_or_invalid", None
    try:
        raw = resolved.read_bytes()
        content = raw.decode("utf-8-sig")
        headings = []
        fence = None
        for line in content.splitlines():
            if fence:
                if re.match(
                    r"^ {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*$", line
                ):
                    fence = None
                continue
            opening = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
            if opening and (opening[1][0] != "`" or "`" not in opening[2]):
                fence = opening[1]
                continue
            heading = re.match(r"^ {0,3}#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$", line)
            if heading:
                headings.append(heading[1])
        count = headings.count(section)
        status = "valid" if count == 1 else "section_missing" if count == 0 else "section_ambiguous"
        return status, hashlib.sha256(raw).hexdigest()
    except (OSError, ValueError, UnicodeError):
        return "missing_or_invalid", None


def save_document_purpose(
    path, project_id, purpose_id, data, expected_revision, reason, *, request_id, actor
):
    purpose_id, reason = _text(purpose_id, "purpose_id"), _text(reason, "reason")
    values = {
        "document_id": _text(data.get("document_id"), "document_id"),
        "purpose": data.get("purpose"),
        "category": data.get("category"),
        "active": data.get("active", 1),
    }
    if (
        values["purpose"] not in PURPOSES
        or values["category"] not in (None, "research", "workbench")
        or values["active"] not in (0, 1)
    ):
        raise ValueError("invalid purpose fields")

    def run(db, actor):
        _document(db, project_id, values["document_id"])
        try:
            return _save(
                db,
                "document_purpose",
                project_id,
                purpose_id,
                values,
                expected_revision,
                reason,
                actor,
            )
        except sqlite3.IntegrityError as exc:
            raise Conflict("duplicate document purpose") from exc

    return _write(
        path,
        request_id,
        actor,
        "save_document_purpose",
        [project_id, purpose_id, values, expected_revision, reason],
        run,
    )


def save_task_plan_reference(
    path, project_id, reference_id, data, expected_revision, reason, *, request_id, actor
):
    reference_id, reason = _text(reference_id, "reference_id"), _text(reason, "reason")
    values = {
        k: _text(data.get(k), k)
        for k in ("task_id", "document_id", "path", "section_locator", "purpose")
    }
    values.update(is_primary=data.get("is_primary", 0), active=data.get("active", 1))
    if (
        values["purpose"] not in PURPOSES
        or values["is_primary"] not in (0, 1)
        or values["active"] not in (0, 1)
    ):
        raise ValueError("invalid plan fields")

    def run(db, actor):
        task = db.execute("SELECT project_id FROM task WHERE id=?", (values["task_id"],)).fetchone()
        if not task or task["project_id"] != project_id:
            raise ValueError("task does not belong to project")
        _document(db, project_id, values["document_id"], values["path"])
        try:
            return _save(
                db,
                "task_plan_reference",
                project_id,
                reference_id,
                values,
                expected_revision,
                reason,
                actor,
            )
        except sqlite3.IntegrityError as exc:
            raise Conflict("duplicate plan reference or primary plan") from exc

    return _write(
        path,
        request_id,
        actor,
        "save_task_plan_reference",
        [project_id, reference_id, values, expected_revision, reason],
        run,
    )


def _get(db, project_id, reference_id):
    row = db.execute(
        "SELECT * FROM task_plan_reference WHERE id=? AND project_id=?", (reference_id, project_id)
    ).fetchone()
    if not row:
        raise Missing("plan reference not found")
    return row


def _detection(db, row):
    root = _document(db, row["project_id"], row["document_id"], row["path"], check_path=False)
    status, digest = _inspect(root, row["path"], row["section_locator"])
    last = db.execute(
        "SELECT * FROM task_plan_verification WHERE reference_id=? ORDER BY rowid DESC LIMIT 1",
        (row["id"],),
    ).fetchone()
    if (
        status == "valid"
        and last
        and (last["file_sha256"] != digest or last["reference_revision"] != row["revision"])
    ):
        status = "changed"
    elif status == "valid" and not last:
        status = "unverified"
    return {
        "reference": dict(row),
        "status": status,
        "current_sha256": digest,
        "last_verification": dict(last) if last else None,
    }


def inspect_task_plan_reference(path, project_id, reference_id):
    db = connect(path)
    try:
        return _detection(db, _get(db, project_id, reference_id))
    finally:
        db.close()


def verify_task_plan_reference(
    path, project_id, reference_id, expected_revision, expected_sha256, *, request_id, actor
):
    def run(db, actor):
        row = _get(db, project_id, reference_id)
        if row["revision"] != expected_revision or not row["active"]:
            raise Conflict("reference revision conflict or inactive")
        root = _document(db, project_id, row["document_id"], row["path"], check_path=False)
        status, digest = _inspect(root, row["path"], row["section_locator"])
        if status != "valid" or digest != expected_sha256:
            raise Conflict("source changed or invalid: " + status)
        record = {
            "id": uuid.uuid4().hex,
            "project_id": project_id,
            "reference_id": reference_id,
            "file_sha256": digest,
            "actor": actor,
            "created_at": now(),
            "reference_revision": row["revision"],
        }
        db.execute(
            "INSERT INTO task_plan_verification VALUES(?,?,?,?,?,?,?)", tuple(record.values())
        )
        db.execute(
            "INSERT INTO activity(project_id,task_id,action,actor,created_at,summary) "
            "VALUES(?,?,?,?,?,?)",
            (project_id, row["task_id"], "plan_verified", actor, now(), _json(record)),
        )
        return record

    return _write(
        path,
        request_id,
        actor,
        "verify_task_plan_reference",
        [project_id, reference_id, expected_revision, expected_sha256],
        run,
    )


def list_task_plan_references(path, project_id, task_id):
    db = connect(path)
    try:
        return [
            _detection(db, row)
            for row in db.execute(
                "SELECT * FROM task_plan_reference WHERE project_id=? AND task_id=? ORDER BY id",
                (project_id, task_id),
            )
        ]
    finally:
        db.close()


def list_plan_verifications(path, project_id, reference_id):
    db = connect(path)
    try:
        _get(db, project_id, reference_id)
        return [
            dict(row)
            for row in db.execute(
                "SELECT * FROM task_plan_verification WHERE project_id=? "
                "AND reference_id=? ORDER BY rowid",
                (project_id, reference_id),
            )
        ]
    finally:
        db.close()


def list_document_purposes(path, project_id):
    db = connect(path)
    try:
        return [
            dict(row)
            for row in db.execute(
                "SELECT * FROM document_purpose WHERE project_id=? ORDER BY id", (project_id,)
            )
        ]
    finally:
        db.close()
