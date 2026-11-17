"""Independent research classifications and technical issues with immutable reviews."""

import json
from typing import Literal

from pydantic import Field

from catalyst_ai.storage.workbench import now, transaction
from catalyst_ai.workbench.service import Conflict, Missing, Model, _json, _text, _write


class Ref(Model):
    id: str = Field(min_length=1)
    version: str = Field(pattern=r"^[0-9a-f]{64}$")
    role: str = Field(min_length=1)


class Claim(Model):
    title: str = Field(min_length=1)
    object_type: Literal["software", "governance", "model", "screening", "candidate", "feedback"]
    classification: Literal["planned", "implemented", "validated"]
    task_id: str | None = None
    scope: str = Field(min_length=1)
    conclusion: str = Field(min_length=1)
    limitations: str = Field(min_length=1)
    evidence: list[Ref] = Field(default_factory=list)


class Issue(Model):
    title: str = Field(min_length=1)
    status: Literal["researching", "proposed", "resolved"]
    task_id: str | None = None
    decision_id: str | None = None
    scope: str = Field(min_length=1)
    conclusion: str = Field(min_length=1)
    evidence: list[Ref] = Field(default_factory=list)


REQUIRED = {
    "software": {"code", "test"},
    "governance": {"source", "rules", "report", "snapshot"},
    "model": {
        "snapshot",
        "features",
        "target",
        "split",
        "metrics",
        "run",
        "reproduction",
        "domain",
    },
    "screening": {"model", "space", "constraints", "output", "review"},
    "candidate": {
        "candidate",
        "preparation",
        "experiment",
        "raw",
        "conditions",
        "metrics",
        "review",
    },
    "feedback": {
        "experiment_review",
        "snapshot",
        "old_model",
        "new_model",
        "training",
        "paired_review",
    },
}


def save(path, project_id, kind, record_id, content, expected_revision, *, request_id, actor):
    if kind not in {"claims", "issues"}:
        raise ValueError("unknown record kind")
    record_id = _text(record_id, "id")
    value = (Claim if kind == "claims" else Issue).model_validate(content).model_dump()
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("invalid expected revision")

    def run(db, actor):
        revision = (
            db.execute(
                "SELECT max(revision) FROM research_record WHERE project_id=? AND kind=? AND id=?",
                (project_id, kind, record_id),
            ).fetchone()[0]
            or 0
        )
        if revision != expected_revision:
            raise Conflict("research revision conflict")
        for field, table in (("task_id", "task"), ("decision_id", "decision")):
            if (
                value.get(field)
                and not db.execute(
                    f"SELECT 1 FROM {table} WHERE id=? AND project_id=?", (value[field], project_id)
                ).fetchone()
            ):
                raise Missing(field + " not found in project")
        roles = {e["role"] for e in value["evidence"]}
        if kind == "claims" and value["classification"] != "planned":
            needed = (
                REQUIRED[value["object_type"]]
                if value["classification"] == "validated"
                else {"code", "test"}
            )
            if missing := needed - roles:
                raise Conflict("missing evidence roles: " + ", ".join(sorted(missing)))
        if kind == "issues" and value["status"] == "resolved" and not roles:
            raise Conflict("resolved issue needs fixed evidence")
        for ref in value["evidence"]:
            row = db.execute(
                "SELECT status FROM evidence WHERE project_id=? AND id=? AND version=?",
                (project_id, ref["id"], ref["version"]),
            ).fetchone()
            if not row or row[0] != "available":
                raise Conflict("evidence unavailable: " + ref["id"])
        db.execute(
            "INSERT INTO research_record VALUES(?,?,?,?,?,?,?)",
            (project_id, kind, record_id, revision + 1, _json(value), actor, now()),
        )
        db.execute(
            "INSERT INTO activity(project_id,task_id,action,actor,created_at,summary,revision) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                project_id,
                value.get("task_id"),
                kind + "_review",
                actor,
                now(),
                record_id,
                revision + 1,
            ),
        )
        return {"id": record_id, "revision": revision + 1}

    return _write(
        path, request_id, actor, kind, [project_id, record_id, value, expected_revision], run
    )


def list_records(path, project_id, kind):
    with transaction(path) as db:
        result = []
        for row in db.execute(
            "SELECT * FROM research_record WHERE project_id=? AND kind=? ORDER BY id,revision DESC",
            (project_id, kind),
        ):
            item = dict(row)
            item["content"] = json.loads(item["content"])
            item["needs_review"] = False
            for ref in item["content"]["evidence"]:
                status = db.execute(
                    "SELECT status FROM evidence WHERE project_id=? AND id=? AND version=?",
                    (project_id, ref["id"], ref["version"]),
                ).fetchone()
                ref["status"] = status[0] if status else "missing"
                item["needs_review"] |= ref["status"] != "available"
            result.append(item)
        return result
