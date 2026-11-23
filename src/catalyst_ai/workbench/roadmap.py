"""Read-only, evidence-aware research roadmap snapshot."""

import json
import sqlite3
import tempfile
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

from catalyst_ai.storage.workbench import connect
from catalyst_ai.workbench import queries, service

STAGES = (
    ("A", "工程骨架"),
    ("B", "治理"),
    ("C", "预测"),
    ("D", "诊断"),
    ("E", "推荐"),
    ("F", "实验反馈"),
)
PRIORITY = ("blocked", "in_progress", "in_review", "ready", "planned")


def summary_labels(summary, status_labels, empty_state=None):
    labels = [f"已验收有效 {summary['valid_completed']}/{summary['valid_total']}"]
    if summary["status"]:
        labels.append(status_labels[summary["status"]])
    labels.extend(f"{status_labels[status]} {count}" for status, count in summary["counts"].items())
    if summary["cancelled_task_ids"]:
        labels.append(f"已取消 {len(summary['cancelled_task_ids'])}")
    for show, label in (
        (empty_state == "undecomposed", "尚未拆分"),
        (empty_state == "cancelled_only", "仅含已取消任务"),
        (summary["scope_incomplete"], "范围待补充"),
        (summary["source_needs_review"], "来源待复核"),
        (summary["evidence_review_task_ids"], "验收证据待复核"),
        (summary["included_scope_complete"], "已纳入范围完成"),
    ):
        if show:
            labels.append(label)
    return labels


def snapshot(path, project_id):
    """Return one project snapshot shared by roadmap views; never write to the source."""
    with tempfile.TemporaryDirectory(prefix="wb-roadmap-") as directory:
        copy = Path(directory) / "management.sqlite"
        with closing(
            sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
        ) as source:
            with closing(sqlite3.connect(copy)) as target:
                source.backup(target)
        view = queries.query(copy, project_id, "all")
        tasks = {t["id"]: t for t in view["tasks"] if t["category"] == "research"}
        with closing(connect(copy)) as db:
            for task in tasks.values():
                acceptance = (
                    db.execute(
                        "SELECT * FROM review WHERE task_id=? AND kind='acceptance' "
                        "ORDER BY id DESC LIMIT 1",
                        (task["id"],),
                    ).fetchone()
                    if task["status"] == "done"
                    else None
                )
                task["evidence_needs_review"] = task["status"] == "done" and (
                    acceptance is None or not service._review_evidence_available(db, acceptance)
                )
                task["acceptance_id"] = acceptance["id"] if acceptance else None
        nodes = {n["id"]: n for n in view["research_nodes"]["nodes"]}
        children = defaultdict(list)
        stage_names = dict(STAGES)
        for n in nodes.values():
            for legacy in ("task_count", "done_count", "complete"):
                n.pop(legacy, None)
            n["display_name"] = (
                stage_names[n["stage"]] if n["parent_id"] is None else n["source_section"]
            )
            n["source_observed_at"] = view["observed_at"]
            children[n["parent_id"]].append(n["id"])
        for ids in children.values():
            ids.sort(key=lambda i: (nodes[i]["sort_order"], i))
        direct = defaultdict(set)
        links = []
        for link in view["research_nodes"]["links"]:
            if link["task_id"] in tasks and link["node_id"] in nodes:
                direct[link["node_id"]].add(link["task_id"])
                links.append(link)
        primary = {link["task_id"] for link in links if link["role"] == "primary"}
        pending = sorted(set(tasks) - primary)
        pending_stages = set()
        for task_id in pending:
            stages = tasks[task_id]["stages"]
            pending_stages.update(json.loads(stages) if isinstance(stages, str) else stages)

        def summarize(ids, incomplete, source_review):
            cancelled = sorted(i for i in ids if tasks[i]["status"] == "cancelled")
            active = sorted(set(ids) - set(cancelled))
            counts = Counter(tasks[i]["status"] for i in active)
            review = sorted(i for i in active if tasks[i]["evidence_needs_review"])
            complete = sorted(i for i in active if tasks[i]["status"] == "done" and i not in review)
            return {
                "task_ids": sorted(ids),
                "active_task_ids": active,
                "cancelled_task_ids": cancelled,
                "counts": dict(counts),
                "status": next((s for s in PRIORITY if counts[s]), None),
                "valid_completed_task_ids": complete,
                "evidence_review_task_ids": review,
                "valid_total": len(active),
                "valid_completed": len(complete),
                "scope_incomplete": incomplete,
                "source_needs_review": source_review,
                "included_scope_complete": bool(active)
                and len(complete) == len(active)
                and not incomplete
                and not source_review,
            }

        def visit(node_id):
            node = nodes[node_id]
            ids = set(direct[node_id])
            incomplete = not children[node_id] and not ids
            source_review = node["source_status"] != "valid"
            for child in children[node_id]:
                sub_ids, sub_incomplete, sub_review = visit(child)
                ids.update(sub_ids)
                incomplete |= sub_incomplete
                source_review |= sub_review
            incomplete |= node["stage"] in pending_stages
            node["child_ids"] = children[node_id]
            node["direct_task_ids"] = sorted(direct[node_id])
            node["summary"] = summarize(ids, incomplete, source_review)
            node["empty_state"] = (
                "undecomposed"
                if not children[node_id] and not ids
                else "cancelled_only"
                if ids and all(tasks[i]["status"] == "cancelled" for i in ids)
                else None
            )
            return ids, incomplete, source_review

        all_ids, incomplete, source_review = set(), False, False
        stages = []
        for stage, name in STAGES:
            roots = [i for i in children[None] if nodes[i]["stage"] == stage]
            stages.append(
                {"stage": stage, "name": name, "root_ids": roots, "registered": bool(roots)}
            )
            if not roots:
                incomplete = True
            for root in roots:
                ids, inc, src = visit(root)
                all_ids.update(ids)
                incomplete |= inc
                source_review |= src
        return {
            "scope": {"project_id": project_id, "category": "research"},
            "observed_at": view["observed_at"],
            "source": view["source"],
            "stages": stages,
            "nodes": nodes,
            "links": links,
            "tasks": tasks,
            "pending_task_ids": pending,
            "unclassified_tasks": [t for t in view["tasks"] if not t["category"]],
            "focus": view["contexts"]["research"],
            "summary": summarize(all_ids, incomplete or bool(pending), source_review),
        }
