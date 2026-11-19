"""Consistent, read-only management query shared by Web and CLI."""

import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from pathlib import Path

from catalyst_ai.storage.workbench import connect, now
from catalyst_ai.workbench import category_context, deliveries, plans, research_nodes, service

SCOPES = ("all", "research", "workbench", "unclassified")


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
        selected = [
            task
            for task in all_tasks
            if scope == "all" or (task["category"] or "unclassified") == scope
        ]
        ids = {task["id"] for task in selected}
        counts = {}
        for category in ("research", "workbench", "unclassified"):
            rows = [t for t in selected if (t["category"] or "unclassified") == category]
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
        for task in selected:
            primary = [
                r
                for r in plans.list_task_plan_references(snapshot, project_id, task["id"])
                if r["reference"]["active"] and r["reference"]["is_primary"]
            ]
            references[task["id"]] = primary[0] if primary else None
            if not primary:
                missing.append({"task_id": task["id"], "kind": "primary_plan"})
        history = (
            deliveries.list_historical_deliveries(snapshot, project_id)
            if scope in ("all", "workbench")
            else []
        )
        with closing(connect(snapshot)) as db:
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
            "historical_deliveries": history,
            "research_nodes": nodes,
            "contexts": contexts,
            "primary_plans": references,
            "missing": missing,
        }
