"""Versioned project decisions and focus selection."""

from catalyst_ai.storage.workbench import now, transaction
from catalyst_ai.workbench.service import Conflict, Missing, _json, _text, _write


def save_decision(path, project_id, decision_id, fields, expected_revision, *, request_id, actor):
    allowed = {"title", "background", "conclusion", "rationale", "impact", "source", "supersedes"}
    if set(fields) != allowed:
        raise ValueError("invalid decision fields")
    decision_id = _text(decision_id, "decision_id")
    for key in ("title", "background", "conclusion"):
        _text(fields[key], key)

    def run(db, actor):
        if not db.execute("SELECT 1 FROM project WHERE id=?", (project_id,)).fetchone():
            raise Missing("project not found")
        old = db.execute("SELECT * FROM decision WHERE id=?", (decision_id,)).fetchone()
        if old and (old["project_id"] != project_id or old["revision"] != expected_revision):
            raise Conflict("decision revision conflict")
        if not old and expected_revision != 0:
            raise Conflict("decision revision conflict")
        if fields["supersedes"]:
            predecessor = db.execute(
                "SELECT project_id FROM decision WHERE id=?", (fields["supersedes"],)
            ).fetchone()
            if (
                not predecessor
                or predecessor[0] != project_id
                or fields["supersedes"] == decision_id
            ):
                raise ValueError("invalid superseded decision")
            ancestor = fields["supersedes"]
            seen = set()
            while ancestor:
                if ancestor == decision_id or ancestor in seen:
                    raise Conflict("cyclic decision replacement")
                seen.add(ancestor)
                row = db.execute(
                    "SELECT r.supersedes FROM decision d JOIN decision_revision r "
                    "ON r.decision_id=d.id AND r.revision=d.revision WHERE d.id=?",
                    (ancestor,),
                ).fetchone()
                ancestor = row[0] if row else None
        revision = expected_revision + 1
        if old:
            db.execute("UPDATE decision SET revision=? WHERE id=?", (revision, decision_id))
        else:
            db.execute(
                "INSERT INTO decision VALUES(?,?,?,?)", (decision_id, project_id, revision, now())
            )
        db.execute(
            "INSERT INTO decision_revision VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                decision_id,
                revision,
                fields["title"],
                fields["background"],
                fields["conclusion"],
                fields["rationale"],
                fields["impact"],
                fields["source"],
                fields["supersedes"] or None,
                actor,
                now(),
            ),
        )
        db.execute(
            "INSERT INTO activity(project_id,action,actor,created_at,summary,revision) "
            "VALUES(?,?,?,?,?,?)",
            (
                project_id,
                "decision_saved",
                actor,
                now(),
                _json({"decision_id": decision_id, "title": fields["title"]}),
                revision,
            ),
        )
        return {"id": decision_id, "revision": revision}

    return _write(
        path,
        request_id,
        actor,
        "save_decision",
        [project_id, decision_id, fields, expected_revision],
        run,
    )


def list_decisions(path, project_id):
    with transaction(path) as db:
        return [
            dict(row)
            for row in db.execute(
                "SELECT d.id,d.revision,r.title,r.conclusion,r.created_at FROM decision d "
                "JOIN decision_revision r ON r.decision_id=d.id AND r.revision=d.revision "
                "WHERE d.project_id=? ORDER BY r.created_at DESC",
                (project_id,),
            )
        ]


def get_decision(path, project_id, decision_id):
    with transaction(path) as db:
        decision = db.execute(
            "SELECT * FROM decision WHERE id=? AND project_id=?", (decision_id, project_id)
        ).fetchone()
        if not decision:
            raise Missing("decision not found")
        result = dict(decision)
        result["history"] = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM decision_revision WHERE decision_id=? ORDER BY revision DESC",
                (decision_id,),
            )
        ]
        result["tasks"] = [
            dict(row)
            for row in db.execute("SELECT * FROM task_decision WHERE decision_id=?", (decision_id,))
        ]
        return result


def link_task(path, project_id, decision_id, task_id, impact, *, request_id, actor):
    def run(db, actor):
        task = db.execute("SELECT project_id FROM task WHERE id=?", (task_id,)).fetchone()
        decision = db.execute(
            "SELECT project_id FROM decision WHERE id=?", (decision_id,)
        ).fetchone()
        if not task or not decision or task[0] != project_id or decision[0] != project_id:
            raise Missing("task or decision not found in project")
        db.execute(
            "INSERT INTO task_decision VALUES(?,?,?) ON CONFLICT(task_id,decision_id) "
            "DO UPDATE SET impact=excluded.impact",
            (task_id, decision_id, impact),
        )
        db.execute(
            "INSERT INTO activity(project_id,task_id,action,actor,created_at,summary) "
            "VALUES(?,?,?,?,?,?)",
            (
                project_id,
                task_id,
                "decision_linked",
                actor,
                now(),
                _json({"decision_id": decision_id, "impact": impact}),
            ),
        )
        return {"task_id": task_id, "decision_id": decision_id}

    return _write(
        path, request_id, actor, "decision_link", [project_id, decision_id, task_id, impact], run
    )


def set_focus(path, project_id, task_id, *, request_id, actor):
    def run(db, actor):
        if (
            task_id
            and not db.execute(
                "SELECT 1 FROM task WHERE id=? AND project_id=?", (task_id, project_id)
            ).fetchone()
        ):
            raise Missing("task not found in project")
        if not db.execute("SELECT 1 FROM project WHERE id=?", (project_id,)).fetchone():
            raise Missing("project not found")
        # Categorized legacy writes update the same context used by the new service.
        from catalyst_ai.workbench.category_context import _context, _set_focus

        previous = db.execute(
            "SELECT focus_task_id FROM project WHERE id=?", (project_id,)
        ).fetchone()[0]
        # Preserve a categorized pre-migration focus before the legacy pointer changes.
        prior = db.execute(
            "SELECT category FROM task WHERE id=? AND project_id=?", (previous, project_id)
        ).fetchone()
        if previous and previous != task_id and prior and prior[0]:
            prior_context = _context(db, project_id, prior[0])
            if not prior_context:
                _set_focus(db, project_id, prior[0], previous, 0, "legacy focus migration", actor)
        selected = task_id or previous
        task = db.execute(
            "SELECT category FROM task WHERE id=? AND project_id=?", (selected, project_id)
        ).fetchone()
        if task and task[0]:
            context = _context(db, project_id, task[0])
            if task_id or (context and context["focus_task_id"] == previous):
                _set_focus(
                    db,
                    project_id,
                    task[0],
                    task_id or None,
                    context["revision"] if context else 0,
                    "legacy focus entry",
                    actor,
                )
        db.execute("UPDATE project SET focus_task_id=? WHERE id=?", (task_id or None, project_id))
        db.execute(
            "INSERT INTO activity(project_id,task_id,action,actor,created_at,summary) "
            "VALUES(?,?,?,?,?,?)",
            (
                project_id,
                task_id or None,
                "focus_changed",
                actor,
                now(),
                _json({"task_id": task_id}),
            ),
        )
        return {"focus_task_id": task_id or None}

    return _write(path, request_id, actor, "set_focus", [project_id, task_id], run)
