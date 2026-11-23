"""Consistent, read-only management query shared by Web and CLI."""

import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from pathlib import Path

from catalyst_ai.storage.workbench import connect, now
from catalyst_ai.workbench import category_context, deliveries, plans, research_nodes, service

CATEGORIES = ("research", "workbench", "unclassified")
SCOPES = ("all", *CATEGORIES)


def task_category(task):
    return task["category"] or "unclassified"


def query(path, project_id, scope="all"):
    """Return a project-scoped snapshot; file checks reflect the observation time.

    Task totals count each task ID once. The current schema has no task parent
    relation, so no inferred parent/child progress is calculated.
    """
    if scope not in SCOPES:
        raise ValueError("invalid category scope")
    with tempfile.TemporaryDirectory(prefix="wb-query-") as directory:
        snapshot = Path(directory) / "snapshot.sqlite"
        # mode=ro prevents a misspelled database path from creating an empty database.
        source = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
        try:
            with closing(sqlite3.connect(snapshot)) as target:
                source.backup(target)
        finally:
            source.close()
        observed_at = now()
        all_tasks = service.list_tasks_by_category(snapshot, project_id, "all")
        selected = [task for task in all_tasks if scope == "all" or task_category(task) == scope]
        ids = {task["id"] for task in selected}
        counts = {}
        for category in CATEGORIES:
            rows = [t for t in selected if task_category(t) == category]
            counts[category] = {
                "total": len(rows),
                "by_status": dict(Counter(t["status"] for t in rows)),
            }
        nodes = research_nodes.list_research_nodes(snapshot, project_id)
        if scope not in ("all", "research"):
            nodes = {"nodes": [], "links": [], "pending": []}
        else:
            nodes["links"] = [link for link in nodes["links"] if link["task_id"] in ids]
            nodes["pending"] = [task for task in nodes["pending"] if task["id"] in ids]
        contexts = {
            category: category_context.get_category_context(snapshot, project_id, category)
            for category in ("research", "workbench")
            if scope in ("all", category)
        }
        references = {}
        missing = []

        def primary_plan(task_id):
            primary = [
                r
                for r in plans.list_task_plan_references(snapshot, project_id, task_id)
                if r["reference"]["active"] and r["reference"]["is_primary"]
            ]
            return primary[0] if primary else None

        for task in selected:
            reference = references[task["id"]] = primary_plan(task["id"])
            if reference is None:
                missing.append({"task_id": task["id"], "kind": "primary_plan"})
        historical_deliveries = (
            deliveries.list_historical_deliveries(snapshot, project_id)
            if scope in ("all", "workbench")
            else []
        )
        next_work = {}
        with closing(connect(snapshot)) as db:
            for category, context in contexts.items():
                category_tasks = {t["id"]: t for t in all_tasks if t["category"] == category}
                manual = [r for r in context["recent"] if r["active"]]
                ids_manual = {r["task_id"] for r in manual}

                def enrich(task_id, manual_item=None, context=context):
                    task = service.get_task(snapshot, task_id)
                    row = db.execute("SELECT * FROM task WHERE id=?", (task_id,)).fetchone()
                    try:
                        service._ready(db, row)
                        reason = None
                    except service.Conflict as exc:
                        reason = str(exc)
                    task["ready_reason"] = reason
                    task["dependency_warnings"] = []
                    for dep_id in task["dependencies"]:
                        dep = service.get_task(snapshot, dep_id)
                        if dep["status"] != "done" or dep["evidence_needs_review"]:
                            task["dependency_warnings"].append(dep_id)
                    task["focus"] = bool(
                        context["context"] and context["context"]["focus_task_id"] == task_id
                    )
                    task["needs_review"] = bool(manual_item and manual_item["needs_review"]) or (
                        task["focus"] and context["focus_needs_review"]
                    )
                    task["manual"] = manual_item is not None
                    task["plan"] = (
                        references[task_id] if task_id in references else primary_plan(task_id)
                    )
                    return task

                entries = [enrich(r["task_id"], r) for r in manual]
                candidates = [
                    enrich(tid)
                    for tid, t in category_tasks.items()
                    if tid not in ids_manual and t["status"] not in ("done", "cancelled")
                ]
                priority = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
                candidates.sort(
                    key=lambda t: (
                        bool(t["ready_reason"]) or t["status"] == "blocked",
                        priority.get(t["priority"], 4),
                        not bool(t["planned_date"]),
                        t["planned_date"] or "",
                        t["id"],
                    )
                )
                active = [
                    t for t in entries if t["status"] not in ("done", "cancelled")
                ] + candidates
                history = [t for t in entries if t["status"] in ("done", "cancelled")]
                history += [
                    enrich(tid)
                    for tid, t in category_tasks.items()
                    if tid not in ids_manual and t["status"] in ("done", "cancelled")
                ]
                next_work[category] = {
                    "active": active,
                    "history": history,
                    "focus_needs_review": context["focus_needs_review"],
                    "focus_id": context["context"]["focus_task_id"] if context["context"] else None,
                }
            schema = db.execute("PRAGMA user_version").fetchone()[0]
        return {
            "scope": {"project_id": project_id, "category": scope},
            "observed_at": observed_at,
            "source": {
                "schema_version": schema,
                "file_detection": "live filesystem at observation time",
            },
            "tasks": selected,
            "counts": counts,
            "total": len(ids),
            "historical_deliveries": historical_deliveries,
            "research_nodes": nodes,
            "contexts": contexts,
            "next_work": next_work,
            "primary_plans": references,
            "missing": missing,
        }
