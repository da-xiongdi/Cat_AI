"""Transactional task, dependency and acceptance operations.

Evidence status is supplied by a trusted indexing adapter; it does not verify files.
"""

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from catalyst_ai.storage.workbench import now, transaction


class Conflict(ValueError):
    """A revision, state, dependency or idempotency conflict."""


class Missing(ValueError):
    """The requested object does not exist."""


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Criterion(Model):
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    required: bool = True


class Result(Model):
    criterion_id: str = Field(min_length=1)
    passed: bool
    evidence_id: str | None = None
    evidence_version: str | None = None
    explanation: str | None = None


class TaskCreate(Model):
    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    deliverables: list[str] = Field(default_factory=list)
    criteria: list[Criterion] = Field(default_factory=list)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    owner: str | None = None
    planned_date: str | None = None
    milestone: str | None = None
    stages: list[Literal["A", "B", "C", "D", "E", "F"]] = Field(default_factory=list)
    primary_stage: Literal["A", "B", "C", "D", "E", "F"] | None = None
    category: Literal["research", "workbench"] | None = None

    @model_validator(mode="after")
    def stage_consistency(self):
        if len(set(self.stages)) != len(self.stages):
            raise ValueError("duplicate stages")
        if (self.primary_stage is None) != (not self.stages) or (
            self.primary_stage is not None and self.primary_stage not in self.stages
        ):
            raise ValueError("primary stage must belong to stages")
        return self


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _task(db, task_id):
    row = db.execute("SELECT * FROM task WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise Missing(f"task not found: {task_id}")
    return row


def _revision(row, expected):
    if row["revision"] != expected:
        raise Conflict("task revision conflict")


def _event(db, row, action, actor, summary):
    db.execute(
        "INSERT INTO activity(project_id,task_id,action,actor,created_at,summary,revision) "
        "VALUES(?,?,?,?,?,?,?)",
        (row["project_id"], row["id"], action, actor, now(), _json(summary), row["revision"]),
    )


def _write(path, request_id, actor, operation, payload, callback):
    request_id, actor = _text(request_id, "request_id"), _text(actor, "actor")
    fingerprint = hashlib.sha256(_json([operation, actor, payload]).encode()).hexdigest()
    with transaction(path) as db:
        previous = db.execute(
            "SELECT * FROM request_log WHERE request_id=?", (request_id,)
        ).fetchone()
        if previous:
            if previous["fingerprint"] != fingerprint:
                raise Conflict("request ID reused with different content")
            return json.loads(previous["response"])
        result = callback(db, actor)
        db.execute(
            "INSERT INTO request_log VALUES(?,?,?)", (request_id, fingerprint, _json(result))
        )
        return result


def create_project(path, project_id, name, *, request_id, actor):
    project_id, name = _text(project_id, "project_id"), _text(name, "name")

    def run(db, actor):
        if db.execute("SELECT 1 FROM project WHERE id=?", (project_id,)).fetchone():
            raise Conflict("project already exists")
        db.execute("INSERT INTO project(id,name) VALUES(?,?)", (project_id, name))
        db.execute(
            "INSERT INTO activity(project_id,action,actor,created_at,summary) VALUES(?,?,?,?,?)",
            (project_id, "project_created", actor, now(), _json({"name": name})),
        )
        return {"id": project_id}

    return _write(path, request_id, actor, "create_project", [project_id, name], run)


def create_task(path, data, *, request_id, actor):
    data = TaskCreate.model_validate(data)
    if len({c.id for c in data.criteria}) != len(data.criteria):
        raise ValueError("duplicate criterion IDs")
    if any(not x.strip() for x in data.deliverables):
        raise ValueError("empty deliverable")

    def run(db, actor):
        if not db.execute("SELECT 1 FROM project WHERE id=?", (data.project_id,)).fetchone():
            raise Missing("project not found")
        if db.execute("SELECT 1 FROM task WHERE id=?", (data.id,)).fetchone():
            raise Conflict("task already exists")
        db.execute(
            "INSERT INTO task(id,project_id,title,goal,deliverables,status,priority,owner,"
            "planned_date,milestone,stages,primary_stage,category) "
            "VALUES(?,?,?,?,?,'planned',?,?,?,?,?,?,?)",
            (
                data.id,
                data.project_id,
                data.title,
                data.goal,
                _json(data.deliverables),
                data.priority,
                data.owner,
                data.planned_date,
                data.milestone,
                _json(data.stages),
                data.primary_stage,
                data.category,
            ),
        )
        for c in data.criteria:
            db.execute(
                "INSERT INTO criterion VALUES(?,?,?,?,?)",
                (data.id, 1, c.id, c.description, c.required),
            )
        row = _task(db, data.id)
        _event(db, row, "created", actor, data.model_dump())
        return {"id": data.id, "revision": 1}

    payload = data.model_dump(mode="json")
    if data.category is None:
        payload.pop("category")
    return _write(path, request_id, actor, "create_task", payload, run)


def add_dependency(path, task_id, prerequisite_id, expected_revision, *, request_id, actor):
    payload = [task_id, prerequisite_id, expected_revision]

    def run(db, actor):
        row, dep = _task(db, task_id), _task(db, prerequisite_id)
        _revision(row, expected_revision)
        if row["project_id"] != dep["project_id"] or task_id == prerequisite_id:
            raise Conflict("dependency must be another task in the same project")
        if row["status"] not in ("planned", "blocked"):
            raise Conflict("dependencies can only be changed while planned or blocked")
        cycle = db.execute(
            """WITH RECURSIVE ancestors(id) AS (
            SELECT prerequisite_id FROM dependency WHERE task_id=?
            UNION SELECT d.prerequisite_id FROM dependency d JOIN ancestors a ON d.task_id=a.id
        ) SELECT 1 FROM ancestors WHERE id=?""",
            (prerequisite_id, task_id),
        ).fetchone()
        if cycle:
            raise Conflict("cyclic dependency")
        if db.execute(
            "SELECT 1 FROM dependency WHERE task_id=? AND prerequisite_id=?",
            (task_id, prerequisite_id),
        ).fetchone():
            raise Conflict("dependency already exists")
        db.execute("INSERT INTO dependency VALUES(?,?)", (task_id, prerequisite_id))
        db.execute("UPDATE task SET revision=revision+1 WHERE id=?", (task_id,))
        row = _task(db, task_id)
        _event(db, row, "dependency_added", actor, {"prerequisite_id": prerequisite_id})
        return {"id": task_id, "revision": row["revision"]}

    return _write(path, request_id, actor, "add_dependency", payload, run)


def update_task(path, task_id, expected_revision, changes, *, request_id, actor):
    allowed = {
        "title",
        "goal",
        "deliverables",
        "priority",
        "owner",
        "planned_date",
        "criteria",
        "milestone",
        "stages",
        "primary_stage",
    }
    if not changes or set(changes) - allowed:
        raise ValueError("unknown or empty changes")
    payload = [task_id, expected_revision, changes]

    def run(db, actor):
        row = _task(db, task_id)
        _revision(row, expected_revision)
        if row["status"] in ("done", "in_review", "cancelled"):
            raise Conflict("reopen task before editing")
        if {"goal", "deliverables"} & changes.keys() and "criteria" not in changes:
            accepted = db.execute(
                "SELECT 1 FROM review WHERE task_id=? AND kind='acceptance' LIMIT 1",
                (task_id,),
            ).fetchone()
            if accepted:
                raise Conflict("scope changes after acceptance require new criteria")
        values = dict(row)
        values["deliverables"] = json.loads(values["deliverables"])
        values["stages"] = json.loads(values["stages"])
        values.update({k: v for k, v in changes.items() if k != "criteria"})
        parsed = TaskCreate.model_validate(
            {k: values[k] for k in TaskCreate.model_fields if k != "criteria"}
        )
        if any(not x.strip() for x in parsed.deliverables):
            raise ValueError("empty deliverable")
        linked_stages = {
            r["stage"]
            for r in db.execute(
                "SELECT n.stage FROM task_node_link l JOIN research_node n ON n.id=l.node_id "
                "WHERE l.task_id=? AND l.active=1",
                (task_id,),
            )
        }
        if not linked_stages.issubset(parsed.stages):
            raise Conflict("remove incompatible node links before changing stages")
        version = row["criteria_version"]
        if "criteria" in changes:
            criteria = [Criterion.model_validate(c) for c in changes["criteria"]]
            if len({c.id for c in criteria}) != len(criteria):
                raise ValueError("duplicate criterion IDs")
            version += 1
            for c in criteria:
                db.execute(
                    "INSERT INTO criterion VALUES(?,?,?,?,?)",
                    (task_id, version, c.id, c.description, c.required),
                )
        db.execute(
            "UPDATE task SET title=?,goal=?,deliverables=?,priority=?,owner=?,planned_date=?,"
            "criteria_version=?,milestone=?,stages=?,primary_stage=?,"
            "revision=revision+1 WHERE id=?",
            (
                parsed.title,
                parsed.goal,
                _json(parsed.deliverables),
                parsed.priority,
                parsed.owner,
                parsed.planned_date,
                version,
                parsed.milestone,
                _json(parsed.stages),
                parsed.primary_stage,
                task_id,
            ),
        )
        row = _task(db, task_id)
        _event(db, row, "updated", actor, changes)
        return {"id": task_id, "revision": row["revision"], "criteria_version": version}

    return _write(path, request_id, actor, "update_task", payload, run)


def set_evidence(path, project_id, evidence_id, version, description, status, *, request_id, actor):
    for value, name in [
        (project_id, "project"),
        (evidence_id, "evidence_id"),
        (version, "version"),
        (description, "description"),
    ]:
        _text(value, name)
    if status not in {"available", "pending", "changed", "missing", "invalid", "read_error"}:
        raise ValueError("invalid evidence status")
    payload = [project_id, evidence_id, version, description, status]

    def run(db, actor):
        if not db.execute("SELECT 1 FROM project WHERE id=?", (project_id,)).fetchone():
            raise Missing("project not found")
        existing = db.execute(
            "SELECT * FROM evidence WHERE id=? AND version=?", (evidence_id, version)
        ).fetchone()
        if existing and (
            existing["project_id"] != project_id or existing["description"] != description
        ):
            raise Conflict("evidence version identity conflict")
        db.execute(
            "INSERT INTO evidence VALUES(?,?,?,?,?,?) ON CONFLICT(id,version) DO UPDATE SET "
            "status=excluded.status,observed_at=excluded.observed_at",
            (evidence_id, version, project_id, description, status, now()),
        )
        db.execute(
            "INSERT INTO activity(project_id,action,actor,created_at,summary) VALUES(?,?,?,?,?)",
            (
                project_id,
                "evidence_observed",
                actor,
                now(),
                _json({"id": evidence_id, "version": version, "status": status}),
            ),
        )
        return {"id": evidence_id, "version": version, "status": status}

    return _write(path, request_id, actor, "set_evidence", payload, run)


def _review_evidence_available(db, review):
    for result in json.loads(review["results"]):
        if result.get("evidence_id"):
            evidence = db.execute(
                "SELECT status FROM evidence WHERE id=? AND version=?",
                (result["evidence_id"], result["evidence_version"]),
            ).fetchone()
            if not evidence or evidence["status"] != "available":
                return False
    return True


def _ready(db, row):
    if not json.loads(row["deliverables"]):
        raise Conflict("deliverables are required")
    if not db.execute(
        "SELECT 1 FROM criterion WHERE task_id=? AND version=?",
        (row["id"], row["criteria_version"]),
    ).fetchone():
        raise Conflict("acceptance criteria are required")
    deps = db.execute(
        "SELECT t.* FROM task t JOIN dependency d ON d.prerequisite_id=t.id WHERE d.task_id=?",
        (row["id"],),
    ).fetchall()
    for dep in deps:
        review = db.execute(
            "SELECT * FROM review WHERE task_id=? AND kind='acceptance' ORDER BY id DESC LIMIT 1",
            (dep["id"],),
        ).fetchone()
        if dep["status"] != "done" or not review or not _review_evidence_available(db, review):
            raise Conflict(f"dependency not complete or evidence unavailable: {dep['id']}")


TRANSITIONS = {
    "planned": {"ready", "cancelled"},
    "ready": {"in_progress", "blocked", "cancelled"},
    "in_progress": {"blocked", "cancelled"},
    "in_review": {"in_progress", "blocked", "cancelled"},
    "blocked": {"ready", "cancelled"},
    "done": {"in_progress"},
    "cancelled": {"planned"},
}


def transition(
    path,
    task_id,
    expected_revision,
    target,
    *,
    request_id,
    actor,
    reason=None,
    recovery_condition=None,
    recovery_date=None,
    resolution=None,
):
    payload = [
        task_id,
        expected_revision,
        target,
        reason,
        recovery_condition,
        recovery_date,
        resolution,
    ]

    def run(db, actor):
        row = _task(db, task_id)
        _revision(row, expected_revision)
        if target not in TRANSITIONS.get(row["status"], set()):
            raise Conflict("invalid state transition; use review operations for acceptance")
        if target in ("ready", "in_progress") and row["status"] in ("planned", "ready", "blocked"):
            _ready(db, row)
        if target in ("blocked", "cancelled") or row["status"] in (
            "done",
            "cancelled",
            "in_review",
        ):
            _text(reason, "reason")
        if target == "blocked":
            _text(recovery_condition, "recovery_condition")
        if row["status"] == "blocked" and target == "ready":
            _text(resolution, "resolution")
        db.execute(
            "UPDATE task SET status=?,blocker=?,recovery_condition=?,recovery_date=?,"
            "revision=revision+1 WHERE id=?",
            (
                target,
                reason if target == "blocked" else None,
                recovery_condition if target == "blocked" else None,
                recovery_date if target == "blocked" else None,
                task_id,
            ),
        )
        row = _task(db, task_id)
        _event(
            db,
            row,
            "transition",
            actor,
            {
                "target": target,
                "reason": reason,
                "recovery_condition": recovery_condition,
                "recovery_date": recovery_date,
                "resolution": resolution,
            },
        )
        return {"id": task_id, "revision": row["revision"], "status": target}

    return _write(path, request_id, actor, "transition", payload, run)


def submit_review(path, task_id, expected_revision, results, conclusion, *, request_id, actor):
    conclusion = _text(conclusion, "conclusion")
    parsed = [Result.model_validate(item) for item in results]
    if len({r.criterion_id for r in parsed}) != len(parsed):
        raise ValueError("duplicate results")
    payload = [task_id, expected_revision, [r.model_dump() for r in parsed], conclusion]

    def run(db, actor):
        row = _task(db, task_id)
        _revision(row, expected_revision)
        if row["status"] != "in_progress":
            raise Conflict("task must be in progress")
        criteria = db.execute(
            "SELECT * FROM criterion WHERE task_id=? AND version=?",
            (task_id, row["criteria_version"]),
        ).fetchall()
        known = {c["criterion_id"] for c in criteria}
        supplied = {r.criterion_id for r in parsed}
        required = {c["criterion_id"] for c in criteria if c["required"]}
        if not criteria or not required <= supplied or not supplied <= known:
            raise Conflict("results must cover required criteria and refer to current criteria")
        for r in parsed:
            if bool(r.evidence_id) != bool(r.evidence_version):
                raise ValueError("evidence ID and version must be supplied together")
            if not r.evidence_id and not (r.explanation and r.explanation.strip()):
                raise ValueError("each result needs evidence or an explanation")
            if r.evidence_id:
                ev = db.execute(
                    "SELECT * FROM evidence WHERE id=? AND version=?",
                    (r.evidence_id, r.evidence_version),
                ).fetchone()
                if not ev or ev["project_id"] != row["project_id"]:
                    raise Missing("evidence version not found in project")
        db.execute(
            "INSERT INTO review(task_id,criteria_version,kind,conclusion,actor,created_at,results) "
            "VALUES(?,?,'submission',?,?,?,?)",
            (
                task_id,
                row["criteria_version"],
                conclusion,
                actor,
                now(),
                _json([r.model_dump() for r in parsed]),
            ),
        )
        db.execute("UPDATE task SET status='in_review',revision=revision+1 WHERE id=?", (task_id,))
        row = _task(db, task_id)
        _event(db, row, "review_submitted", actor, {"conclusion": conclusion})
        return {"id": task_id, "status": "in_review", "revision": row["revision"]}

    return _write(path, request_id, actor, "submit_review", payload, run)


def accept_review(path, task_id, expected_revision, conclusion, *, request_id, actor):
    conclusion = _text(conclusion, "conclusion")
    payload = [task_id, expected_revision, conclusion]

    def run(db, actor):
        row = _task(db, task_id)
        _revision(row, expected_revision)
        if row["status"] != "in_review":
            raise Conflict("task must be in review")
        submission = db.execute(
            "SELECT * FROM review WHERE task_id=? AND kind='submission' ORDER BY id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        if not submission or submission["criteria_version"] != row["criteria_version"]:
            raise Conflict("no submission for current criteria")
        results = {r["criterion_id"]: r for r in json.loads(submission["results"])}
        required = db.execute(
            "SELECT criterion_id FROM criterion WHERE task_id=? AND version=? AND required=1",
            (task_id, row["criteria_version"]),
        ).fetchall()
        if any(not results[c["criterion_id"]]["passed"] for c in required):
            raise Conflict("required criteria have not passed")
        if not _review_evidence_available(db, submission):
            raise Conflict("review evidence is unavailable")
        db.execute(
            "INSERT INTO review(task_id,criteria_version,kind,conclusion,actor,created_at,results) "
            "VALUES(?,?,'acceptance',?,?,?,?)",
            (task_id, row["criteria_version"], conclusion, actor, now(), submission["results"]),
        )
        db.execute("UPDATE task SET status='done',revision=revision+1 WHERE id=?", (task_id,))
        row = _task(db, task_id)
        _event(db, row, "accepted", actor, {"conclusion": conclusion})
        return {"id": task_id, "status": "done", "revision": row["revision"]}

    return _write(path, request_id, actor, "accept_review", payload, run)


def get_task(path: Path, task_id: str):
    with transaction(path) as db:
        row = _task(db, task_id)
        data = dict(row)
        data["deliverables"] = json.loads(data["deliverables"])
        data["stages"] = json.loads(data["stages"])
        data["criteria"] = [
            dict(c)
            for c in db.execute(
                "SELECT * FROM criterion WHERE task_id=? AND version=? ORDER BY rowid",
                (task_id, row["criteria_version"]),
            )
        ]
        data["dependencies"] = [
            d[0]
            for d in db.execute(
                "SELECT prerequisite_id FROM dependency WHERE task_id=? ORDER BY prerequisite_id",
                (task_id,),
            )
        ]
        data["dependents"] = [
            d[0]
            for d in db.execute(
                "SELECT task_id FROM dependency WHERE prerequisite_id=? ORDER BY task_id",
                (task_id,),
            )
        ]
        data["reviews"] = [
            dict(r)
            for r in db.execute("SELECT * FROM review WHERE task_id=? ORDER BY id", (task_id,))
        ]
        for review in data["reviews"]:
            review["results"] = json.loads(review["results"])
        acceptance = db.execute(
            "SELECT * FROM review WHERE task_id=? AND kind='acceptance' ORDER BY id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        data["evidence_needs_review"] = bool(
            row["status"] == "done"
            and (not acceptance or not _review_evidence_available(db, acceptance))
        )
        data["activity"] = [
            dict(e)
            for e in db.execute("SELECT * FROM activity WHERE task_id=? ORDER BY id", (task_id,))
        ]
        return data


def remove_dependency(path, task_id, prerequisite_id, expected_revision, *, request_id, actor):
    payload = [task_id, prerequisite_id, expected_revision]

    def run(db, actor):
        row = _task(db, task_id)
        _revision(row, expected_revision)
        if row["status"] not in ("planned", "blocked"):
            raise Conflict("dependencies can only be changed while planned or blocked")
        deleted = db.execute(
            "DELETE FROM dependency WHERE task_id=? AND prerequisite_id=?",
            (task_id, prerequisite_id),
        )
        if not deleted.rowcount:
            raise Missing("dependency not found")
        db.execute("UPDATE task SET revision=revision+1 WHERE id=?", (task_id,))
        row = _task(db, task_id)
        _event(db, row, "dependency_removed", actor, {"prerequisite_id": prerequisite_id})
        return {"id": task_id, "revision": row["revision"]}

    return _write(path, request_id, actor, "remove_dependency", payload, run)


def list_tasks(path: Path, project_id: str):
    with transaction(path) as db:
        if not db.execute("SELECT 1 FROM project WHERE id=?", (project_id,)).fetchone():
            raise Missing("project not found")
        return [
            dict(row)
            for row in db.execute(
                "SELECT id,title,status,priority,owner,planned_date,milestone,revision "
                "FROM task WHERE project_id=? ORDER BY id",
                (project_id,),
            )
        ]


def preview_task_categories(path, project_id, proposals):
    """Review explicit evidence-based proposals without inferring from task IDs."""
    with transaction(path) as db:
        if not db.execute("SELECT 1 FROM project WHERE id=?", (project_id,)).fetchone():
            raise Missing("project not found")
        result = []
        for row in db.execute("SELECT * FROM task WHERE project_id=? ORDER BY id", (project_id,)):
            proposal = proposals.get(row["id"], {})
            category = proposal.get("category")
            evidence = proposal.get("evidence", "")
            conflict = None
            if category not in (None, "research", "workbench"):
                conflict = "invalid category"
            elif category is not None and not str(evidence).strip():
                conflict = "evidence required"
            elif row["category"] is not None and category not in (None, row["category"]):
                conflict = "existing category differs"
            result.append(
                {
                    "task_id": row["id"],
                    "goal": row["goal"],
                    "old_category": row["category"],
                    "category": category,
                    "evidence": evidence,
                    "expected_revision": row["revision"],
                    "conflict": conflict,
                }
            )
        return result


def set_task_category(
    path, project_id, task_id, category, expected_revision, reason, *, request_id, actor
):
    if category not in (None, "research", "workbench"):
        raise ValueError("invalid category")
    reason = _text(reason, "reason")
    payload = [project_id, task_id, category, expected_revision, reason]

    def run(db, actor):
        row = _task(db, task_id)
        if row["project_id"] != project_id:
            raise ValueError("task belongs to another project")
        _revision(row, expected_revision)
        if row["category"] == category:
            return {"id": task_id, "revision": row["revision"], "changed": False}
        if (
            category != "research"
            and db.execute(
                "SELECT 1 FROM task_node_link WHERE task_id=? AND active=1", (task_id,)
            ).fetchone()
        ):
            raise Conflict("remove node links before changing category")
        db.execute(
            "UPDATE task SET category=?, revision=revision+1 WHERE id=?", (category, task_id)
        )
        updated = _task(db, task_id)
        db.execute(
            "INSERT INTO task_category_revision VALUES(?,?,?,?,?,?,?,?)",
            (
                task_id,
                project_id,
                updated["revision"],
                row["category"],
                category,
                reason,
                actor,
                now(),
            ),
        )
        _event(
            db,
            updated,
            "category_changed",
            actor,
            {"old": row["category"], "new": category, "reason": reason},
        )
        return {"id": task_id, "revision": updated["revision"], "changed": True}

    return _write(path, request_id, actor, "set_task_category", payload, run)


def list_tasks_by_category(path, project_id, category="all"):
    if category not in ("all", "research", "workbench", "unclassified"):
        raise ValueError("invalid category")
    with transaction(path) as db:
        if not db.execute("SELECT 1 FROM project WHERE id=?", (project_id,)).fetchone():
            raise Missing("project not found")
        rows = db.execute("SELECT * FROM task WHERE project_id=? ORDER BY id", (project_id,))
        return [
            dict(row)
            for row in rows
            if category == "all"
            or (category == "unclassified" and row["category"] is None)
            or row["category"] == category
        ]


def apply_task_categories(path, project_id, proposals, *, request_id, actor):
    """Apply an explicitly reviewed batch atomically, after checking every revision."""
    if len({p["task_id"] for p in proposals}) != len(proposals):
        raise ValueError("duplicate task")
    for item in proposals:
        if item["category"] not in ("research", "workbench"):
            raise ValueError("invalid category")
        _text(item["evidence"], "evidence")

    def run(db, actor):
        rows = []
        for item in proposals:
            row = _task(db, item["task_id"])
            if row["project_id"] != project_id:
                raise ValueError("task belongs to another project")
            _revision(row, item["expected_revision"])
            if row["category"] not in (None, item["category"]):
                raise Conflict("existing category differs")
            rows.append(row)
        results = []
        for item, row in zip(proposals, rows, strict=True):
            if row["category"] != item["category"]:
                db.execute(
                    "UPDATE task SET category=?,revision=revision+1 WHERE id=?",
                    (item["category"], row["id"]),
                )
                updated = _task(db, row["id"])
                db.execute(
                    "INSERT INTO task_category_revision VALUES(?,?,?,?,?,?,?,?)",
                    (
                        row["id"],
                        project_id,
                        updated["revision"],
                        row["category"],
                        item["category"],
                        item["evidence"],
                        actor,
                        now(),
                    ),
                )
                _event(
                    db,
                    updated,
                    "category_changed",
                    actor,
                    {"old": row["category"], "new": item["category"], "reason": item["evidence"]},
                )
                results.append({"id": row["id"], "revision": updated["revision"], "changed": True})
            else:
                results.append({"id": row["id"], "revision": row["revision"], "changed": False})
        return results

    return _write(path, request_id, actor, "apply_task_categories", [project_id, proposals], run)
