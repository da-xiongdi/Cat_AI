"""Durable, leased prediction jobs. Web submits; a separate CLI process executes."""

import hashlib
import importlib.metadata
import json
import os
import platform
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from catalyst_ai.storage.workbench import now, transaction
from catalyst_ai.workbench import adapters, index, model_runs
from catalyst_ai.workbench.service import Conflict, Missing, _json, _write


def sha(data):
    return hashlib.sha256(data).hexdigest()


def implementation():
    source = Path(__file__).parents[1]
    return {
        name: sha((source / name).read_bytes())
        for name in (
            "modeling/predictor.py",
            "features/pipeline.py",
            "features/design.py",
            "workbench/predictions.py",
        )
    }


def environment():
    value = {"python": platform.python_version()}
    for name in ("numpy", "scikit-learn"):
        try:
            value[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            value[name] = "not installed"
    return value


def workspace(db, project_id):
    with transaction(db) as conn:
        row = conn.execute(
            "SELECT root FROM index_workspace WHERE project_id=?", (project_id,)
        ).fetchone()
    if not row:
        raise Missing("workspace not configured")
    return Path(row[0]).resolve(strict=True)


def job_dir(root, job_id):
    if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        raise ValueError("invalid prediction job ID")
    return adapters.safe_path(root, "artifacts/workbench-predictions/" + job_id)


def get(db, project_id, job_id):
    with transaction(db) as conn:
        row = conn.execute(
            "SELECT * FROM prediction_job WHERE id=? AND project_id=?", (job_id, project_id)
        ).fetchone()
        if not row:
            raise Missing("prediction job not found")
        value = dict(row)
        value["payload"] = json.loads(value["payload"])
        value["result"] = json.loads(value["result"]) if value["result"] else None
        value["events"] = [
            dict(e)
            for e in conn.execute(
                "SELECT created_at,message FROM prediction_event WHERE job_id=? ORDER BY id",
                (job_id,),
            )
        ]
        root = conn.execute(
            "SELECT root FROM index_workspace WHERE project_id=?", (project_id,)
        ).fetchone()
        log = job_dir(root[0], job_id) / "execution.log"
        value["log"] = log.read_text(encoding="utf-8")[-65536:] if log.is_file() else ""
        return value


def list_jobs(db, project_id):
    with transaction(db) as conn:
        ids = [
            r[0]
            for r in conn.execute(
                "SELECT id FROM prediction_job WHERE project_id=? "
                "ORDER BY created_at DESC LIMIT 100",
                (project_id,),
            )
        ]
    return [get(db, project_id, ident) for ident in ids]


def enqueue(
    db, project_id, model_id, version, items, task_id=None, retry_of=None, *, request_id, actor
):
    if not isinstance(items, list) or not 1 <= len(items) <= 1000:
        raise ValueError("prediction input must contain 1 to 1000 rows")
    raw = json.dumps(items, ensure_ascii=False, allow_nan=False, sort_keys=True).encode("utf-8")
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("prediction input exceeds 2 MiB")
    root = workspace(db, project_id)
    artifact = index.get_artifact(db, model_id)
    if artifact["project_id"] != project_id or artifact["kind"] != "model":
        raise ValueError("select a registered model in this project")
    paths = [
        o["path"]
        for o in artifact["observations"]
        if o["status"] == "available" and o["file_sha256"] == version
    ]
    if len(paths) != 1:
        raise Conflict("refresh index and select an available fixed model version")
    manifest = adapters.safe_path(root, paths[0]).read_bytes()
    metadata = json.loads(manifest)
    model = adapters.safe_path(root, str(Path(paths[0]).parent / "model.pkl")).read_bytes()
    if sha(manifest) != version or sha(model) != metadata["artifact_sha256"]:
        raise Conflict("model changed since indexing")
    spec = dict(
        model_id=model_id,
        version=version,
        items=items,
        task_id=task_id,
        retry_of=retry_of,
        input_sha256=sha(raw),
        implementation=implementation(),
        submitted_environment=environment(),
    )

    def create(conn, operator):
        if (
            task_id
            and not conn.execute(
                "SELECT 1 FROM task WHERE id=? AND project_id=?", (task_id, project_id)
            ).fetchone()
        ):
            raise Missing("task not found in project")
        if (
            retry_of
            and not conn.execute(
                "SELECT 1 FROM prediction_job WHERE id=? AND project_id=?", (retry_of, project_id)
            ).fetchone()
        ):
            raise Missing("parent prediction job not found")
        ident = uuid.uuid4().hex
        directory = job_dir(root, ident)
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "manifest.json").write_bytes(manifest)
        (directory / "model.pkl").write_bytes(model)
        (directory / "input.json").write_bytes(raw)
        (directory / "execution.log").write_text("queued\n", encoding="utf-8")
        for name, kind in (
            ("manifest.json", "model"),
            ("input.json", "attachment"),
            ("execution.log", "attachment"),
        ):
            artifact_id = ident + "-" + name
            conn.execute(
                "INSERT INTO artifact VALUES(?,?,?,?)", (artifact_id, project_id, kind, now())
            )
            conn.execute(
                "INSERT INTO artifact_location VALUES(?,?)",
                (artifact_id, (directory / name).relative_to(root).as_posix()),
            )
        conn.execute(
            "INSERT INTO prediction_job VALUES(?,?, 'queued',1,?,?,?,NULL,NULL,NULL,NULL,NULL)",
            (ident, project_id, _json(spec), operator, now()),
        )
        conn.execute(
            "INSERT INTO prediction_event(job_id,created_at,message) VALUES(?,?,?)",
            (ident, now(), "queued; model and inputs pinned"),
        )
        return {"id": ident, "status": "queued", "revision": 1}

    return _write(db, request_id, actor, "enqueue_prediction", [project_id, spec], create)


def cancel(db, project_id, job_id, expected_revision, *, request_id, actor):
    if type(expected_revision) is not int or expected_revision < 1:
        raise ValueError("expected_revision must be a positive integer")

    def change(conn, operator):
        row = conn.execute(
            "SELECT status,revision FROM prediction_job WHERE id=? AND project_id=?",
            (job_id, project_id),
        ).fetchone()
        if not row:
            raise Missing("prediction job not found")
        if row[1] != expected_revision or row[0] not in {"queued", "running"}:
            raise Conflict("prediction status or revision conflict")
        conn.execute(
            "UPDATE prediction_job SET status='cancelled',revision=revision+1,lease=NULL "
            "WHERE id=?",
            (job_id,),
        )
        conn.execute(
            "INSERT INTO prediction_event(job_id,created_at,message) VALUES(?,?,?)",
            (job_id, now(), "cancelled by " + operator),
        )
        return {"id": job_id, "status": "cancelled"}

    return _write(
        db, request_id, actor, "cancel_prediction", [project_id, job_id, expected_revision], change
    )


def retry(db, project_id, job_id, *, request_id, actor):
    job = get(db, project_id, job_id)
    if job["status"] not in {"failed", "interrupted", "cancelled"}:
        raise Conflict("only failed, interrupted or cancelled jobs can be retried")
    spec = job["payload"]
    # Reuse the verified pinned package even if the original source has moved or changed.
    index.scan(db, project_id)
    return enqueue(
        db,
        project_id,
        job_id + "-manifest.json",
        spec["version"],
        spec["items"],
        spec["task_id"],
        job_id,
        request_id=request_id,
        actor=actor,
    )


def recover(db, project_id, stale_seconds=60):
    cutoff = (datetime.now(UTC) - timedelta(seconds=stale_seconds)).isoformat()
    with transaction(db) as conn:
        ids = [
            r[0]
            for r in conn.execute(
                "SELECT id FROM prediction_job WHERE project_id=? "
                "AND status='running' AND heartbeat<?",
                (project_id, cutoff),
            )
        ]
        for ident in ids:
            conn.execute(
                "UPDATE prediction_job SET status='interrupted',lease=NULL,"
                "revision=revision+1,error='worker heartbeat expired' WHERE id=?",
                (ident,),
            )
            conn.execute(
                "INSERT INTO prediction_event(job_id,created_at,message) VALUES(?,?,?)",
                (ident, now(), "interrupted: heartbeat expired; retry creates a new job"),
            )
    return ids


def run_once(db, project_id):
    """Claim one queued job atomically; heartbeat and lease fence stale processes."""
    from catalyst_ai.modeling.predictor import load_package, predict_one

    recover(db, project_id)
    token = uuid.uuid4().hex
    with transaction(db) as conn:
        row = conn.execute(
            "SELECT id FROM prediction_job WHERE project_id=? AND status='queued' "
            "ORDER BY created_at,id LIMIT 1",
            (project_id,),
        ).fetchone()
        if not row:
            return None
        ident = row[0]
        conn.execute(
            "UPDATE prediction_job SET status='running',revision=revision+1,lease=?,"
            "pid=?,heartbeat=? WHERE id=?",
            (token, os.getpid(), now(), ident),
        )
        conn.execute(
            "INSERT INTO prediction_event(job_id,created_at,message) VALUES(?,?,?)",
            (ident, now(), "worker claimed job"),
        )
    job = get(db, project_id, ident)
    root = workspace(db, project_id)
    directory = job_dir(root, ident)
    stop = threading.Event()

    def heartbeat():
        while not stop.wait(5):
            with transaction(db) as conn:
                conn.execute(
                    "UPDATE prediction_job SET heartbeat=? WHERE id=? AND lease=? "
                    "AND status='running'",
                    (now(), ident, token),
                )

    def active():
        current = get(db, project_id, ident)
        if current["status"] != "running" or current["lease"] != token:
            raise Conflict("job cancelled or worker lease lost")

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    log = directory / "execution.log"
    try:
        spec = job["payload"]
        if implementation() != spec["implementation"]:
            raise ValueError("prediction implementation changed since submission")
        if sha((directory / "manifest.json").read_bytes()) != spec["version"]:
            raise ValueError("pinned model manifest changed")
        if sha((directory / "input.json").read_bytes()) != spec["input_sha256"]:
            raise ValueError("pinned prediction input changed")
        package = load_package(directory)
        results = []
        with log.open("a", encoding="utf-8") as stream:
            for number, item in enumerate(spec["items"], 1):
                active()
                result = predict_one(package, item)
                results.append({"row": number, **result})
                stream.write(f"row {number}: {result['status']}\n")
                stream.flush()
        active()
        output = dict(
            job_id=ident,
            input_sha256=spec["input_sha256"],
            model_version=spec["version"],
            implementation=implementation(),
            environment={
                "python": platform.python_version(),
                **{n: importlib.metadata.version(n) for n in ("numpy", "scikit-learn")},
            },
            rows=results,
        )
        raw = json.dumps(output, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")
        (directory / "result.json").write_bytes(raw)
        refs = []
        for filename, kind, role in (
            ("manifest.json", "model", "model"),
            ("input.json", "attachment", "other"),
            ("result.json", "attachment", "report"),
            ("execution.log", "attachment", "other"),
        ):
            active()
            artifact_id = ident + "-" + filename
            relative = (directory / filename).relative_to(root).as_posix()
            index.register(
                db,
                project_id,
                artifact_id,
                kind,
                relative,
                request_id=artifact_id,
                actor="prediction worker",
            )
            refs.append(
                dict(id=artifact_id, version=sha((directory / filename).read_bytes()), role=role)
            )
        index.scan(db, project_id)
        active()
        metadata = package[0]
        model_runs.save(
            db,
            project_id,
            ident,
            dict(
                title="Batch prediction " + ident,
                task_id=spec["task_id"],
                execution_status="succeeded",
                research_status="unreviewed",
                target=metadata["target_definition"],
                unit=metadata["target_unit"],
                dataset=metadata["snapshot_id"],
                feature_version=metadata["feature_version"],
                algorithm=metadata["model_name"],
                configuration=_json(spec),
                evaluation_scope="Batch inference; per-row validation; no new model evaluation",
                conclusion="Prediction execution completed; inspect individual row statuses",
                limitations="Source acceptance and training ranges are not scientific validation",
                evidence=refs,
            ),
            0,
            request_id="prediction-run-" + ident,
            actor="prediction worker",
            job_completion=(token, output),
        )
    except Exception as exc:
        with log.open("a", encoding="utf-8") as stream:
            stream.write(type(exc).__name__ + ": " + str(exc) + "\n")
        with transaction(db) as conn:
            conn.execute(
                "UPDATE prediction_job SET status='failed',revision=revision+1,error=?,"
                "lease=NULL WHERE id=? AND lease=? AND status='running'",
                (str(exc), ident, token),
            )
            conn.execute(
                "INSERT INTO prediction_event(job_id,created_at,message) VALUES(?,?,?)",
                (ident, now(), type(exc).__name__ + ": " + str(exc)),
            )
    finally:
        stop.set()
        thread.join(timeout=6)
    return ident


def worker(db, project_id, once=False):
    while True:
        ident = run_once(db, project_id)
        if once:
            return ident
        if ident is None:
            time.sleep(1)
