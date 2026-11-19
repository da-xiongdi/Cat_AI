"""Atomic, versioned index of registered, read-only workspace files."""

import hashlib
import json
import uuid
from pathlib import Path

from catalyst_ai.storage.workbench import now, transaction
from catalyst_ai.workbench import adapters
from catalyst_ai.workbench.service import Conflict, Missing, _json, _text, _write


def configure_workspace(path, project_id, root, *, request_id, actor):
    root = str(Path(root).resolve(strict=True))
    if not Path(root).is_dir():
        raise ValueError("workspace root must be a directory")

    def run(db, actor):
        if not db.execute("SELECT 1 FROM project WHERE id=?", (project_id,)).fetchone():
            raise Missing("project not found")
        old = db.execute(
            "SELECT root FROM index_workspace WHERE project_id=?", (project_id,)
        ).fetchone()
        if old and old["root"] != root:
            raise Conflict("workspace root already configured")
        db.execute("INSERT OR IGNORE INTO index_workspace VALUES(?,?)", (project_id, root))
        return {"project_id": project_id, "root": root}

    return _write(path, request_id, actor, "configure_workspace", [project_id, root], run)


def register(path, project_id, artifact_id, kind, relative_path, *, request_id, actor):
    artifact_id = _text(artifact_id, "artifact_id")
    if kind not in adapters.KINDS:
        raise ValueError("unknown artifact kind")
    payload = [project_id, artifact_id, kind, relative_path]

    def run(db, actor):
        workspace = db.execute(
            "SELECT root FROM index_workspace WHERE project_id=?", (project_id,)
        ).fetchone()
        if not workspace:
            raise Missing("workspace not configured")
        adapters.safe_path(workspace["root"], relative_path)
        old = db.execute("SELECT * FROM artifact WHERE id=?", (artifact_id,)).fetchone()
        if old and (old["project_id"] != project_id or old["kind"] != kind):
            raise Conflict("artifact identity conflict")
        if not old:
            db.execute(
                "INSERT INTO artifact VALUES(?,?,?,?)", (artifact_id, project_id, kind, now())
            )
        db.execute(
            "INSERT OR IGNORE INTO artifact_location VALUES(?,?)",
            (artifact_id, Path(relative_path).as_posix()),
        )
        db.execute(
            "INSERT INTO activity(project_id,action,actor,created_at,summary) VALUES(?,?,?,?,?)",
            (project_id, "artifact_registered", actor, now(), _json(payload)),
        )
        return {"id": artifact_id, "path": Path(relative_path).as_posix()}

    return _write(path, request_id, actor, "register_artifact", payload, run)


def register_historical_r1(path, project_id, *, request_id, actor):
    """Register the known R1 evidence atomically after validating its bindings."""
    entries = [
        (
            "R1-comparison",
            "report",
            "artifacts/reports/themecat-r1-comparison-20261112-verified/report.json",
        ),
        (
            "R1-prediction-report",
            "report",
            "artifacts/reports/themecat-r1-prediction-20261112-final/report.json",
        ),
        (
            "R1-model",
            "model",
            "artifacts/models/themecat-r1-prediction-20261112-final/manifest.json",
        ),
        ("I5-model-card", "document", "artifacts/reports/themecat-i5-20261110/model_card.md"),
        ("I5-diagnostics", "attachment", "artifacts/reports/themecat-i5-20261110/diagnostics.json"),
    ]

    def run(db, actor):
        workspace = db.execute(
            "SELECT root FROM index_workspace WHERE project_id=?", (project_id,)
        ).fetchone()
        if not workspace:
            raise Missing("workspace not configured")
        inspected = [
            adapters.inspect(workspace["root"], rel, kind, 64 * 1024 * 1024)
            for _, kind, rel in entries
        ]
        if inspected[2]["metadata"]["report_sha256"] != inspected[1]["content_sha256"]:
            raise Conflict("R1 model and report do not match")
        for artifact_id, kind, rel in entries:
            old = db.execute(
                "SELECT project_id,kind FROM artifact WHERE id=?", (artifact_id,)
            ).fetchone()
            if old and (old["project_id"] != project_id or old["kind"] != kind):
                raise Conflict("artifact identity conflict: " + artifact_id)
            db.execute(
                "INSERT OR IGNORE INTO artifact VALUES(?,?,?,?)",
                (artifact_id, project_id, kind, now()),
            )
            db.execute("INSERT OR IGNORE INTO artifact_location VALUES(?,?)", (artifact_id, rel))
        db.execute(
            "INSERT INTO activity(project_id,action,actor,created_at,summary) VALUES(?,?,?,?,?)",
            (project_id, "historical_r1_registered", actor, now(), _json(entries)),
        )
        return {"artifacts": [item[0] for item in entries]}

    return _write(path, request_id, actor, "register_historical_r1", [project_id], run)


def _scope(db, project_id):
    return [
        dict(row)
        for row in db.execute(
            "SELECT a.id,a.kind,l.path FROM artifact a JOIN artifact_location l "
            "ON l.artifact_id=a.id WHERE a.project_id=? ORDER BY a.id,l.path",
            (project_id,),
        )
    ]


def _published(db, project_id):
    row = db.execute(
        "SELECT scan_id FROM published_index WHERE project_id=?", (project_id,)
    ).fetchone()
    return row["scan_id"] if row else None


def scan(path, project_id, *, max_bytes=64 * 1024 * 1024, document_ids=None):
    """Refresh the project index, or publish observations for selected documents."""
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    selected = None if document_ids is None else set(document_ids)
    scan_id = uuid.uuid4().hex
    with transaction(path) as db:
        workspace = db.execute(
            "SELECT root FROM index_workspace WHERE project_id=?", (project_id,)
        ).fetchone()
        if not workspace:
            raise Missing("workspace not configured")
        root = workspace["root"]
        scope = _scope(db, project_id)
        targets = scope if selected is None else [item for item in scope if item["id"] in selected]
        if selected is not None and (
            not selected
            or {item["id"] for item in targets} != selected
            or any(item["kind"] not in {"document", "attachment"} for item in targets)
        ):
            raise ValueError("selected document or attachment is not registered in the project")
        previous = _published(db, project_id)
        db.execute(
            "INSERT INTO index_scan(id,project_id,started_at,status) VALUES(?,?,?,'running')",
            (scan_id, project_id, now()),
        )
    try:
        results = []
        for item in targets:
            result = {
                **item,
                "observed_at": now(),
                "status": "available",
                "error": None,
                "inspection": None,
            }
            try:
                result["inspection"] = adapters.inspect(root, item["path"], item["kind"], max_bytes)
            except FileNotFoundError as exc:
                result.update(status="missing", error=str(exc))
            except (adapters.InvalidArtifact, ValueError) as exc:
                result.update(status="invalid", error=str(exc))
            except OSError as exc:
                result.update(status="read_error", error=str(exc))
            results.append(result)
        available_ids = {
            r["inspection"]["content_id"] for r in results if r["inspection"] is not None
        }
        for result in results:
            info = result["inspection"]
            if not info:
                continue
            metadata = info["metadata"]
            references = []
            if result["kind"] == "features":
                references.append(metadata.get("selection_id"))
            if result["kind"] in {"features", "selection"}:
                binding = metadata.get("binding", {})
                references.extend(
                    binding.get(key) for key in ("snapshot_id", "qualification_id", "split_id")
                )
            if result["kind"] in {"split", "model"}:
                references.append(metadata.get("snapshot_id"))
            missing = sorted(
                {value for value in references if value and value not in available_ids}
            )
            if missing:
                result["error"] = "unresolved indexed references: " + ", ".join(missing)
        with transaction(path) as db:
            state = db.execute("SELECT status FROM index_scan WHERE id=?", (scan_id,)).fetchone()
            if not state or state["status"] != "running":
                raise Conflict("scan is no longer running")
            if _scope(db, project_id) != scope or _published(db, project_id) != previous:
                raise Conflict("index scope or published generation changed during scan")
            if selected is not None and previous:
                observations = db.execute(
                    "SELECT artifact_id,path,status,file_sha256,error,observed_at "
                    "FROM index_observation WHERE scan_id=?",
                    (previous,),
                ).fetchall()
                db.executemany(
                    "INSERT INTO index_observation VALUES(?,?,?,?,?,?,?)",
                    ((scan_id, *row) for row in observations if row["artifact_id"] not in selected),
                )
            for result in results:
                info = result["inspection"]
                db.execute(
                    "INSERT INTO index_observation VALUES(?,?,?,?,?,?,?)",
                    (
                        scan_id,
                        result["id"],
                        result["path"],
                        result["status"],
                        info["file_sha256"] if info else None,
                        result["error"],
                        result["observed_at"],
                    ),
                )
                if info:
                    db.execute(
                        "INSERT OR IGNORE INTO artifact_revision VALUES(?,?,?,?,?,?)",
                        (
                            result["id"],
                            info["file_sha256"],
                            info["content_id"],
                            info["content_sha256"],
                            _json(info["metadata"]),
                            result["observed_at"],
                        ),
                    )
            for item in {r["id"] for r in results}:
                observations = [r for r in results if r["id"] == item]
                versions = db.execute(
                    "SELECT * FROM artifact_revision WHERE artifact_id=?", (item,)
                ).fetchall()
                for version in versions:
                    matches = [
                        r
                        for r in observations
                        if r["inspection"]
                        and r["inspection"]["file_sha256"] == version["file_sha256"]
                    ]
                    states = {r["status"] for r in observations}
                    status = (
                        "available"
                        if matches
                        else (
                            "changed"
                            if "available" in states
                            else "read_error"
                            if "read_error" in states
                            else "invalid"
                            if "invalid" in states
                            else "missing"
                        )
                    )
                    existing = db.execute(
                        "SELECT project_id,description FROM evidence WHERE id=? AND version=?",
                        (item, version["file_sha256"]),
                    ).fetchone()
                    description = f"indexed artifact: {item}"
                    if existing and (
                        existing["project_id"] != project_id
                        or existing["description"] != description
                    ):
                        raise Conflict("evidence identity collision")
                    db.execute(
                        "INSERT INTO evidence VALUES(?,?,?,?,?,?) ON CONFLICT(id,version) "
                        "DO UPDATE SET status=excluded.status,observed_at=excluded.observed_at",
                        (item, version["file_sha256"], project_id, description, status, now()),
                    )
            db.execute(
                "INSERT INTO published_index VALUES(?,?) ON CONFLICT(project_id) "
                "DO UPDATE SET scan_id=excluded.scan_id",
                (project_id, scan_id),
            )
            db.execute(
                "UPDATE index_scan SET status='complete',finished_at=? WHERE id=?", (now(), scan_id)
            )
            summary = {"scan_id": scan_id}
            if selected is not None:
                summary["document_ids"] = sorted(selected)
            db.execute(
                "INSERT INTO activity(project_id,action,actor,created_at,summary) "
                "VALUES(?,?,?,?,?)",
                (project_id, "index_published", "indexer", now(), _json(summary)),
            )
        return scan_id
    except Exception as exc:
        with transaction(path) as db:
            db.execute(
                "UPDATE index_scan SET status='failed',finished_at=?,error=? "
                "WHERE id=? AND status='running'",
                (now(), str(exc), scan_id),
            )
        raise


def interrupt_scan(path, scan_id):
    with transaction(path) as db:
        row = db.execute("SELECT status FROM index_scan WHERE id=?", (scan_id,)).fetchone()
        if not row:
            raise Missing("scan not found")
        if row["status"] != "running":
            raise Conflict("scan is not running")
        db.execute(
            "UPDATE index_scan SET status='interrupted',finished_at=? WHERE id=?", (now(), scan_id)
        )


def get_scan(path, scan_id):
    with transaction(path) as db:
        row = db.execute("SELECT * FROM index_scan WHERE id=?", (scan_id,)).fetchone()
        if not row:
            raise Missing("scan not found")
        result = dict(row)
        result["observations"] = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM index_observation WHERE scan_id=? ORDER BY artifact_id,path",
                (scan_id,),
            )
        ]
        return result


def list_artifacts(path, project_id, *, offset=0, limit=100):
    if offset < 0 or not 1 <= limit <= 500:
        raise ValueError("invalid page")
    with transaction(path) as db:
        if not db.execute("SELECT 1 FROM project WHERE id=?", (project_id,)).fetchone():
            raise Missing("project not found")
        scan_id = _published(db, project_id)
        rows = db.execute(
            "SELECT * FROM artifact WHERE project_id=? ORDER BY id LIMIT ? OFFSET ?",
            (project_id, limit, offset),
        ).fetchall()
        return {"scan_id": scan_id, "items": [dict(row) for row in rows]}


def get_artifact(path, artifact_id):
    with transaction(path) as db:
        row = db.execute("SELECT * FROM artifact WHERE id=?", (artifact_id,)).fetchone()
        if not row:
            raise Missing("artifact not found")
        scan_id = _published(db, row["project_id"])
        data = dict(row)
        data["scan_id"] = scan_id
        data["locations"] = [
            r[0]
            for r in db.execute(
                "SELECT path FROM artifact_location WHERE artifact_id=? ORDER BY path",
                (artifact_id,),
            )
        ]
        data["observations"] = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM index_observation WHERE scan_id=? AND artifact_id=? ORDER BY path",
                (scan_id, artifact_id),
            )
        ]
        data["revisions"] = [
            dict(r)
            for r in db.execute(
                "SELECT r.*,e.status,e.observed_at FROM artifact_revision r LEFT JOIN evidence e "
                "ON e.id=r.artifact_id AND e.version=r.file_sha256 "
                "WHERE r.artifact_id=? ORDER BY r.created_at DESC",
                (artifact_id,),
            )
        ]
        for revision in data["revisions"]:
            revision["metadata"] = json.loads(revision["metadata"])
        return data


def preview(path, artifact_id, version, *, offset=0, limit=100, max_bytes=64 * 1024 * 1024):
    """Read a published revision and paginate its primary row collection when present."""
    if offset < 0 or not 1 <= limit <= 500:
        raise ValueError("invalid page")
    with transaction(path) as db:
        row = db.execute(
            "SELECT a.kind,w.root,a.project_id FROM artifact a JOIN index_workspace w "
            "ON w.project_id=a.project_id WHERE a.id=?",
            (artifact_id,),
        ).fetchone()
        if not row:
            raise Missing("artifact not found")
        scan_id = _published(db, row["project_id"])
        locations = [
            r[0]
            for r in db.execute(
                "SELECT path FROM index_observation WHERE scan_id=? AND artifact_id=? "
                "AND status='available' AND file_sha256=? ORDER BY path",
                (scan_id, artifact_id, version),
            )
        ]
        kind, root = row["kind"], row["root"]
    for location in locations:
        try:
            inspected = adapters.inspect(root, location, kind, max_bytes)
            raw = adapters.read_limited(adapters.safe_path(root, location), max_bytes)
            if inspected["file_sha256"] != version or hashlib.sha256(raw).hexdigest() != version:
                continue
            if kind in {"document", "attachment"}:
                return {"path": location, "text": raw.decode("utf-8"), "version": version}
            obj = adapters.strict_json(raw.decode("utf-8-sig"))
            container = obj.get("content", obj)
            for key in ("rows", "records", "oof_predictions"):
                values = container.get(key) if isinstance(container, dict) else None
                if isinstance(values, list):
                    return {
                        "path": location,
                        "version": version,
                        "field": key,
                        "total": len(values),
                        "offset": offset,
                        "items": values[offset : offset + limit],
                    }
            return {"path": location, "version": version, "data": obj}
        except (OSError, ValueError, UnicodeError):
            continue
    raise Conflict("published file version is unavailable or changed; refresh index")
