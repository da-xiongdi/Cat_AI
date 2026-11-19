"""Category focus and manually ordered recent task references."""

from uuid import uuid4

from catalyst_ai.storage.workbench import transaction
from catalyst_ai.workbench.research_nodes import _save
from catalyst_ai.workbench.service import Conflict, Missing, _text, _write


def _category(value):
    if value not in ("research", "workbench"):
        raise ValueError("invalid category")


def _task(db, project, category, task_id):
    row = db.execute(
        "SELECT * FROM task WHERE id=? AND project_id=?", (task_id, project)
    ).fetchone()
    if not row:
        raise Missing("task not found in project")
    if row["category"] != category:
        raise ValueError("task category mismatch")
    return row


def _context(db, project, category):
    if not db.execute("SELECT 1 FROM project WHERE id=?", (project,)).fetchone():
        raise Missing("project not found")
    return db.execute(
        "SELECT * FROM category_context WHERE project_id=? AND category=?", (project, category)
    ).fetchone()


def _set_focus(db, project, category, task_id, expected, reason, actor):
    context = _context(db, project, category)
    if task_id:
        _task(db, project, category, task_id)
    # The legacy field is a pointer to the most recently selected focus, not a second copy.
    legacy = db.execute("SELECT focus_task_id FROM project WHERE id=?", (project,)).fetchone()[0]
    legacy_category = db.execute(
        "SELECT category FROM task WHERE id=? AND project_id=?", (legacy, project)
    ).fetchone()
    legacy_context = (
        _context(db, project, legacy_category[0])
        if legacy_category and legacy_category[0]
        else None
    )
    unresolved = bool(
        legacy
        and (not legacy_context or legacy_context["focus_task_id"] != legacy)
        and legacy != task_id
    )
    entity_id = context["id"] if context else uuid4().hex
    result = _save(
        db,
        "category_context",
        project,
        entity_id,
        {"category": category, "focus_task_id": task_id or None},
        expected,
        reason,
        actor,
    )
    if not unresolved and (task_id or (context and legacy == context["focus_task_id"])):
        db.execute("UPDATE project SET focus_task_id=? WHERE id=?", (task_id or None, project))
    return result


def set_category_focus(
    path, project_id, category, task_id, expected_revision, reason, *, request_id, actor
):
    _category(category)
    reason = _text(reason, "reason")
    return _write(
        path,
        request_id,
        actor,
        "category_focus",
        [project_id, category, task_id, expected_revision, reason],
        lambda db, actor: _set_focus(
            db, project_id, category, task_id, expected_revision, reason, actor
        ),
    )


def migrate_legacy_focus(path, project_id, expected_revision, *, request_id, actor):
    def run(db, actor):
        project = db.execute(
            "SELECT focus_task_id FROM project WHERE id=?", (project_id,)
        ).fetchone()
        if not project:
            raise Missing("project not found")
        task_id = project[0]
        task = db.execute(
            "SELECT category FROM task WHERE id=? AND project_id=?", (task_id, project_id)
        ).fetchone()
        if not task or not task[0]:
            return {"focus_task_id": task_id, "needs_review": bool(task_id)}
        category = task[0]
        context = _context(db, project_id, category)
        if context and context["focus_task_id"] != task_id:
            raise Conflict("category focus already differs from legacy focus")
        result = _set_focus(
            db, project_id, category, task_id, expected_revision, "legacy focus migration", actor
        )
        return {"focus_task_id": task_id, "needs_review": False, "context": result}

    return _write(
        path, request_id, actor, "migrate_legacy_focus", [project_id, expected_revision], run
    )


def save_recent_task(
    path,
    project_id,
    category,
    task_id,
    sort_order,
    active,
    expected_revision,
    reason,
    *,
    request_id,
    actor,
):
    _category(category)
    reason = _text(reason, "reason")
    if type(sort_order) is not int or active not in (0, 1):
        raise ValueError("invalid recent task fields")

    def run(db, actor):
        context = _context(db, project_id, category)
        if not context:
            raise Missing("category context not found")
        row = db.execute(
            "SELECT * FROM category_recent_task WHERE context_id=? AND task_id=? AND active=1",
            (context["id"], task_id),
        ).fetchone()
        if active:
            _task(db, project_id, category, task_id)
        elif not row:
            raise Missing("active arrangement not found")
        entity_id = row["id"] if row else uuid4().hex
        return _save(
            db,
            "category_recent_task",
            project_id,
            entity_id,
            {
                "context_id": context["id"],
                "task_id": task_id,
                "sort_order": sort_order,
                "active": int(active),
            },
            expected_revision,
            reason,
            actor,
        )

    return _write(
        path,
        request_id,
        actor,
        "recent_task",
        [project_id, category, task_id, sort_order, active, expected_revision, reason],
        run,
    )


def get_category_context(path, project_id, category):
    _category(category)
    with transaction(path) as db:
        context = _context(db, project_id, category)
        legacy = db.execute(
            "SELECT focus_task_id FROM project WHERE id=?", (project_id,)
        ).fetchone()[0]
        legacy_task = db.execute(
            "SELECT category FROM task WHERE id=? AND project_id=?", (legacy, project_id)
        ).fetchone()
        recent = (
            []
            if not context
            else [
                dict(row)
                for row in db.execute(
                    "SELECT r.*,t.title,t.status,t.category,t.priority,t.planned_date "
                    "FROM category_recent_task r JOIN task t ON t.id=r.task_id "
                    "WHERE r.context_id=? ORDER BY r.active DESC,r.sort_order,t.id",
                    (context["id"],),
                )
            ]
        )
        for item in recent:
            item["needs_review"] = item["category"] != category or item["status"] in (
                "done",
                "cancelled",
            )
        fallback = [
            dict(row)
            for row in db.execute(
                "SELECT id,title,status,priority,planned_date FROM task "
                "WHERE project_id=? AND category=? "
                "ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 "
                "WHEN 'normal' THEN 2 ELSE 3 END, "
                "planned_date IS NULL, planned_date, id",
                (project_id, category),
            )
        ]
        focus = None if not context else context["focus_task_id"]
        focus_task = db.execute("SELECT status,category FROM task WHERE id=?", (focus,)).fetchone()
        return {
            "context": dict(context) if context else None,
            "recent": recent,
            "default_order": fallback,
            "focus_needs_review": bool(
                focus
                and (
                    not focus_task
                    or focus_task["category"] != category
                    or focus_task["status"] in ("done", "cancelled")
                )
            ),
            "legacy_focus_task_id": legacy,
            "legacy_needs_review": bool(legacy and (not legacy_task or not legacy_task[0])),
            "legacy_needs_migration": bool(
                legacy
                and legacy_task
                and legacy_task[0]
                and (
                    not _context(db, project_id, legacy_task[0])
                    or _context(db, project_id, legacy_task[0])["focus_task_id"] != legacy
                )
            ),
        }
