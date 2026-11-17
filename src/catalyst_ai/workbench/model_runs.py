"""Versioned model-run ledger with fixed evidence and task links."""

import json
from typing import Literal

from pydantic import Field

from catalyst_ai.storage.workbench import now, transaction
from catalyst_ai.workbench.service import Conflict, Missing, Model, _json, _text, _write


class EvidenceRef(Model):
    id: str = Field(min_length=1)
    version: str = Field(pattern=r"^[0-9a-f]{64}$")
    role: Literal["model", "report", "shap", "domain", "snapshot", "split", "other"]


class RunContent(Model):
    title: str = Field(min_length=1)
    task_id: str | None = None
    execution_status: Literal[
        "historical", "queued", "running", "succeeded", "failed", "interrupted", "cancelled"
    ]
    research_status: Literal["unreviewed", "reviewed", "limited"]
    target: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    feature_version: str = Field(min_length=1)
    algorithm: str = Field(min_length=1)
    configuration: str = Field(min_length=1)
    evaluation_scope: str = Field(min_length=1)
    conclusion: str = Field(min_length=1)
    limitations: str = Field(min_length=1)
    evidence: list[EvidenceRef] = Field(min_length=1)


def save(
    path, project_id, run_id, content, expected_revision, *, request_id, actor, job_completion=None
):
    run_id = _text(run_id, "run_id")
    value = RunContent.model_validate(content).model_dump()
    payload = [project_id, run_id, value, expected_revision]

    def run(db, actor):
        if job_completion:
            token, output = job_completion
            lease = db.execute(
                "SELECT lease,status FROM prediction_job WHERE id=? AND project_id=?",
                (run_id, project_id),
            ).fetchone()
            if not lease or lease[0] != token or lease[1] != "running":
                raise Conflict("prediction worker lease lost")
        if not db.execute("SELECT 1 FROM project WHERE id=?", (project_id,)).fetchone():
            raise Missing("project not found")
        row = db.execute("SELECT * FROM model_run WHERE id=?", (run_id,)).fetchone()
        if row and row["project_id"] != project_id:
            raise Conflict("run identity conflict")
        revision = row["revision"] if row else 0
        if revision != expected_revision:
            raise Conflict("model run revision conflict")
        if (
            value["task_id"]
            and not db.execute(
                "SELECT 1 FROM task WHERE id=? AND project_id=?", (value["task_id"], project_id)
            ).fetchone()
        ):
            raise Missing("task not found in project")
        seen = set()
        for ref in value["evidence"]:
            key = (ref["id"], ref["version"], ref["role"])
            if key in seen:
                raise ValueError("duplicate evidence reference")
            seen.add(key)
            evidence = db.execute(
                "SELECT status FROM evidence WHERE id=? AND version=? AND project_id=?",
                (ref["id"], ref["version"], project_id),
            ).fetchone()
            if not evidence:
                raise Missing("evidence version not found in project: " + ref["id"])
            if evidence["status"] != "available":
                raise Conflict("evidence unavailable: " + ref["id"])
        if not row:
            db.execute("INSERT INTO model_run VALUES(?,?,?,?)", (run_id, project_id, 1, now()))
        else:
            db.execute("UPDATE model_run SET revision=? WHERE id=?", (revision + 1, run_id))
        db.execute(
            "INSERT INTO model_run_revision VALUES(?,?,?,?,?)",
            (run_id, revision + 1, _json(value), actor, now()),
        )
        db.execute(
            "INSERT INTO activity(project_id,task_id,action,actor,created_at,summary,revision) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                project_id,
                value["task_id"],
                "model_run_saved",
                actor,
                now(),
                _json({"id": run_id}),
                revision + 1,
            ),
        )
        if job_completion:
            db.execute(
                "UPDATE prediction_job SET status='succeeded',revision=revision+1,"
                "result=?,lease=NULL WHERE id=?",
                (_json(output), run_id),
            )
            db.execute(
                "INSERT INTO prediction_event(job_id,created_at,message) VALUES(?,?,?)",
                (run_id, now(), "outputs indexed; execution completed"),
            )
        return {"id": run_id, "revision": revision + 1}

    return _write(path, request_id, actor, "save_model_run", payload, run)


def get(path, project_id, run_id):
    with transaction(path) as db:
        row = db.execute(
            "SELECT * FROM model_run WHERE id=? AND project_id=?", (run_id, project_id)
        ).fetchone()
        if not row:
            raise Missing("model run not found")
        result = dict(row)
        result["history"] = []
        for revision in db.execute(
            "SELECT * FROM model_run_revision WHERE run_id=? ORDER BY revision DESC", (run_id,)
        ):
            item = dict(revision)
            item["content"] = json.loads(item["content"])
            for ref in item["content"]["evidence"]:
                status = db.execute(
                    "SELECT status FROM evidence WHERE id=? AND version=? AND project_id=?",
                    (ref["id"], ref["version"], project_id),
                ).fetchone()
                ref["status"] = status[0] if status else "missing"
            result["history"].append(item)
        return result


def list_runs(path, project_id):
    with transaction(path) as db:
        ids = [
            r[0]
            for r in db.execute(
                "SELECT id FROM model_run WHERE project_id=? ORDER BY id", (project_id,)
            )
        ]
    return [get(path, project_id, run_id) for run_id in ids]


def register_r1(path, project_id, task_id, *, request_id, actor):
    """Create a historical ledger entry from the indexed, bound R1 files."""
    from catalyst_ai.workbench import index

    refs = []
    metadata = {}
    for artifact_id, role in (("R1-model", "model"), ("R1-prediction-report", "report")):
        artifact = index.get_artifact(path, artifact_id)
        if artifact["project_id"] != project_id:
            raise Missing("artifact not found in project")
        observations = [o for o in artifact["observations"] if o["status"] == "available"]
        if len(observations) != 1:
            raise Conflict("refresh index and check R1 evidence: " + artifact_id)
        version = observations[0]["file_sha256"]
        revision = next((r for r in artifact["revisions"] if r["file_sha256"] == version), None)
        if not revision:
            raise Conflict("indexed revision unavailable: " + artifact_id)
        refs.append({"id": artifact_id, "version": version, "role": role})
        metadata[role] = revision
    model = metadata["model"]["metadata"]
    if model.get("report_sha256") != metadata["report"]["content_sha256"]:
        raise Conflict("R1 model and report do not match")
    summary = metadata["report"]["metadata"].get("r1_summary")
    if not summary:
        raise Conflict("R1 report summary unavailable")
    content = {
        "title": "历史 R1 预测模型",
        "task_id": task_id or None,
        "execution_status": "historical",
        "research_status": "limited",
        "target": model.get("target_definition") or "待核对",
        "unit": model.get("target_unit") or "待核对",
        "dataset": model.get("snapshot_id") or "待核对",
        "feature_version": model.get("feature_version") or "待核对",
        "algorithm": model.get("model_name") or "待核对",
        "configuration": _json(summary["configuration"]),
        "evaluation_scope": (
            "原训练集 DOI 分组三折；验证集开发评价；已查看测试集仅作历史对照。"
            "详细指标及分母见固定报告。"
        ),
        "conclusion": "模型及报告为历史运行证据；不代表平台最终选型。",
        "limitations": "来源接受不等于逐条原文核验；适用域未独立验证；R1 的 SHAP 尚未登记。",
        "evidence": refs,
    }
    return save(path, project_id, "R1-prediction", content, 0, request_id=request_id, actor=actor)
