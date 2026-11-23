"""Read models for the workbench's category-filtered lists."""

import hashlib
import json
from collections import Counter
from contextlib import closing

from catalyst_ai.storage.workbench import connect, now
from catalyst_ai.workbench import adapters, index, plans, queries, service

PURPOSE_SCOPES = {"research_plan": "research", "construction_plan": "workbench"}


def _page(rows, memberships, scope, offset, limit):
    if scope not in queries.SCOPES:
        raise ValueError("invalid category scope")
    counts = Counter()
    selected = []
    for row, categories in zip(rows, memberships, strict=True):
        counts.update(categories)
        if scope == "all" or scope in categories:
            selected.append(row)
    selected.sort(key=lambda row: row["id"])
    return {
        "items": selected[offset : offset + limit if limit else None],
        "total": len(selected),
        "counts": {category: counts[category] for category in queries.CATEGORIES},
        "observed_at": now(),
    }


def tasks(path, project_id, scope, *, status="", stage="", q="", offset=0, limit=None):
    with closing(connect(path)) as db:
        db.execute("BEGIN")
        rows = [
            dict(row) for row in db.execute("SELECT * FROM task WHERE project_id=?", (project_id,))
        ]
        matches = []
        for task in rows:
            task["stages"] = json.loads(task["stages"])
            if (
                (not status or task["status"] == status)
                and (not stage or stage in task["stages"])
                and (not q or q.casefold() in (task["title"] + " " + task["id"]).casefold())
            ):
                matches.append(task)
        page = _page(matches, ({queries.task_category(t)} for t in matches), scope, offset, limit)
        effective, needs_review, states = Counter(), Counter(), Counter()
        for task in matches:
            category = queries.task_category(task)
            if scope != "all" and scope != category:
                continue
            task["evidence_needs_review"] = service._task_evidence_needs_review(db, task)
            states[task["status"]] += 1
            if task["status"] == "done":
                (needs_review if task["evidence_needs_review"] else effective)[category] += 1
        for task in page["items"]:
            task["dependency_count"] = db.execute(
                "SELECT count(*) FROM dependency WHERE task_id=?", (task["id"],)
            ).fetchone()[0]
        page.update(effective=effective, needs_review=needs_review, states=states)
        return page


def _document_bases(db, project_id, items, task_info):
    for row in db.execute(
        "SELECT * FROM document_purpose WHERE project_id=? AND active=1 ORDER BY id",
        (project_id,),
    ):
        if item := items.get(row["document_id"]):
            purpose = dict(row)
            named_scope = PURPOSE_SCOPES.get(purpose["purpose"])
            category = purpose["category"] or named_scope
            purpose["needs_review"] = not category or bool(named_scope and named_scope != category)
            item["purposes"].append(purpose)
            item["categories"].add("unclassified" if purpose["needs_review"] else category)
    for row in db.execute(
        "SELECT * FROM task_plan_reference WHERE project_id=? AND active=1 ORDER BY id",
        (project_id,),
    ):
        item = items.get(row["document_id"])
        if not item:
            continue
        task = task_info.get(row["task_id"])
        linkable = bool(task and row["path"] in item["locations"])
        status = plans._detection(db, row)["status"] if linkable else "invalid_reference"
        category = queries.task_category(task) if task else "unclassified"
        named_scope = PURPOSE_SCOPES.get(row["purpose"])
        mismatch = bool(named_scope and named_scope != category)
        item["plans"].append(
            {
                "reference": dict(row),
                "category": category,
                "status": status,
                "linkable": linkable,
                "purpose_mismatch": mismatch,
            }
        )
        item["categories"].add(category if status == "valid" and not mismatch else "unclassified")


def _evidence_links(db, project_id):
    for row in db.execute(
        "SELECT r.* FROM review r JOIN task t ON t.id=r.task_id "
        "WHERE t.project_id=? ORDER BY r.id DESC",
        (project_id,),
    ):
        for result in json.loads(row["results"]):
            if result.get("evidence_id"):
                yield (
                    result["evidence_id"],
                    result.get("evidence_version"),
                    row["task_id"],
                    row["kind"],
                    row["id"],
                    result["criterion_id"],
                )
    for row in db.execute(
        "SELECT id, 'model_run' AS kind, r.content FROM model_run m JOIN model_run_revision r "
        "ON r.run_id=m.id AND r.revision=m.revision WHERE m.project_id=? "
        "UNION ALL SELECT id, kind, content FROM research_record current "
        "WHERE project_id=? AND revision=(SELECT max(revision) FROM research_record "
        "WHERE project_id=current.project_id AND kind=current.kind AND id=current.id) "
        "ORDER BY kind,id",
        (project_id, project_id),
    ):
        content = json.loads(row["content"])
        if task_id := content.get("task_id"):
            for ref in content["evidence"]:
                yield ref["id"], ref["version"], task_id, row["kind"], row["id"], ref["role"]


def _artifact_bases(db, project_id, items, task_info):
    versions = {
        (row["id"], row["version"]): row["status"]
        for row in db.execute(
            "SELECT e.id,e.version,e.status FROM evidence e JOIN artifact_revision r "
            "ON r.artifact_id=e.id AND r.file_sha256=e.version WHERE e.project_id=?",
            (project_id,),
        )
    }
    for artifact_id, version, task_id, kind, source_id, role in _evidence_links(db, project_id):
        item, task = items.get(artifact_id), task_info.get(task_id)
        if not item or not task:
            continue
        category = queries.task_category(task)
        status = versions.get((artifact_id, version))
        item["categories"].add(category if status else "unclassified")
        item["links"].append(
            {
                "task": task,
                "category": category,
                "version": version or "",
                "matched": status is not None,
                "status": status or "missing",
                "kind": kind,
                "source_id": source_id,
                "role": role,
            }
        )


def _check_visible_evidence(db, project_id, items):
    scan_id = index._published(db, project_id)
    if not scan_id:
        return
    root = db.execute(
        "SELECT root FROM index_workspace WHERE project_id=?", (project_id,)
    ).fetchone()
    for item in items:
        versions = {link["version"] for link in item["links"] if link["status"] == "available"}
        if not versions:
            continue
        observed = {}
        for row in db.execute(
            "SELECT path,file_sha256 FROM index_observation "
            "WHERE scan_id=? AND artifact_id=? AND status='available'",
            (scan_id, item["id"]),
        ):
            if row["file_sha256"] not in versions:
                continue
            try:
                file = adapters.safe_path(root["root"], row["path"])
                digest = hashlib.sha256(adapters.read_limited(file, 64 * 1024 * 1024)).hexdigest()
                status = "available" if digest == row["file_sha256"] else "changed"
            except FileNotFoundError:
                status = "missing"
            except (OSError, ValueError):
                status = "read_error"
            observed.setdefault(row["file_sha256"], set()).add(status)
        for link in item["links"]:
            if link["status"] == "available":
                statuses = observed.get(link["version"], set())
                link["status"] = next(
                    (s for s in ("available", "changed", "read_error") if s in statuses), "missing"
                )


def assets(path, project_id, scope, *, documents=False, q="", offset=0, limit=None):
    with closing(connect(path)) as db:
        db.execute("BEGIN")
        items = {}
        for row in db.execute(
            "SELECT * FROM artifact WHERE project_id=? AND (NOT ? OR kind='document')",
            (project_id, documents),
        ):
            items[row["id"]] = dict(
                row, categories=set(), locations=[], purposes=[], plans=[], links=[]
            )
        for row in db.execute(
            "SELECT l.* FROM artifact_location l JOIN artifact a ON a.id=l.artifact_id "
            "WHERE a.project_id=? ORDER BY l.path",
            (project_id,),
        ):
            if row["artifact_id"] in items:
                items[row["artifact_id"]]["locations"].append(row["path"])
        word = q.casefold().strip()
        items = {
            key: item
            for key, item in items.items()
            if word in key.casefold() or any(word in loc.casefold() for loc in item["locations"])
        }
        task_info = {
            row["id"]: dict(row, deliverables=json.loads(row["deliverables"]))
            for row in db.execute(
                "SELECT id,category,deliverables FROM task WHERE project_id=?", (project_id,)
            )
        }
        if documents:
            _document_bases(db, project_id, items, task_info)
        else:
            _artifact_bases(db, project_id, items, task_info)
        for item in items.values():
            if not item["categories"]:
                item["categories"].add("unclassified")
        page = _page(
            items.values(), (a["categories"] for a in items.values()), scope, offset, limit
        )
        for item in page["items"]:
            latest = db.execute(
                "SELECT e.status FROM artifact_revision r LEFT JOIN evidence e "
                "ON e.project_id=? AND e.id=r.artifact_id AND e.version=r.file_sha256 "
                "WHERE r.artifact_id=? ORDER BY r.created_at DESC, r.rowid DESC LIMIT 1",
                (project_id, item["id"]),
            ).fetchone()
            item["status"] = latest["status"] if latest and latest["status"] else "pending"
        if not documents:
            _check_visible_evidence(db, project_id, page["items"])
        return page
