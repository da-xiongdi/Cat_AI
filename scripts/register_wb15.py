"""Rehearse and atomically register WB-15 and accept its baseline task."""

import hashlib
import sqlite3
from pathlib import Path

from close_wb13 import observation, snapshot

from catalyst_ai.storage.workbench import atomic_operations
from catalyst_ai.web.config import load
from catalyst_ai.workbench import index, plans, service

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/wb15-01-samples"
PLAN = "docs/workbench/wb15_implementation_plan.md"
REPORT = "docs/workbench/wb15_01_baseline.md"
SAMPLES = "artifacts/wb15-01-samples/sample-results.json"
PROJECT = "cat-ai"
CHILDREN = [f"WB-15-{i:02d}" for i in range(1, 6)]
NAMES = [
    "基线与展示规则",
    "分类近期任务视图",
    "任务节点与计划章节关联",
    "页面联调与异常复核",
    "专项验收与交付",
]
DEPS = [("WB-13", "WB-14"), ("WB-15-01",), ("WB-15-01",), ("WB-15-02", "WB-15-03"), ("WB-15-04",)]


def auth(key):
    return {"request_id": "wb15-registration:" + key, "actor": "Codex"}


def digest(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def register(db, expected, hashes):
    with atomic_operations(db) as conn:
        if observation(conn) != expected or any(
            digest(path) != sha for path, sha in hashes.items()
        ):
            raise RuntimeError("database or evidence changed since baseline")
        for ident, kind, path in (
            ("WB-15-plan", "document", PLAN),
            ("WB-15-01-report", "document", REPORT),
            ("WB-15-01-samples", "attachment", SAMPLES),
        ):
            index.register(db, PROJECT, ident, kind, path, **auth(ident))
        index.scan(db, PROJECT, document_ids=["WB-15-plan", "WB-15-01-report", "WB-15-01-samples"])
        plans.save_document_purpose(
            db,
            PROJECT,
            "WB-15-plan-purpose",
            {"document_id": "WB-15-plan", "purpose": "execution_plan", "category": "workbench"},
            0,
            "登记 WB-15 实施计划",
            **auth("purpose"),
        )
        for pos, task in enumerate([*CHILDREN, "WB-15"]):
            parent = task == "WB-15"
            title = "下一步工作与计划交接" if parent else NAMES[pos]
            heading = "1. 目标与范围" if parent else f"{task} {title}"
            checks = (
                [
                    {"id": "report", "description": "基线、入口与展示规则已核对"},
                    {"id": "samples", "description": "两类及异常隔离样本已验证"},
                ]
                if pos == 0
                else [{"id": "delivery", "description": title + "交付及验证"}]
            )
            created = service.create_task(
                db,
                {
                    "id": task,
                    "project_id": PROJECT,
                    "title": title,
                    "goal": "完成 WB-15 " + title + "并保留可复核证据",
                    "deliverables": [PLAN + " · " + heading]
                    + ([REPORT, SAMPLES] if pos == 0 else []),
                    "criteria": checks,
                    "category": "workbench",
                    "owner": "Codex",
                },
                **auth(task),
            )
            revision = created["revision"]
            for dependency in ("WB-15-05",) if parent else DEPS[pos]:
                revision = service.add_dependency(
                    db, task, dependency, revision, **auth(task + ":dep:" + dependency)
                )["revision"]
            ref = task + "-primary-plan"
            saved = plans.save_task_plan_reference(
                db,
                PROJECT,
                ref,
                {
                    "task_id": task,
                    "document_id": "WB-15-plan",
                    "path": PLAN,
                    "section_locator": heading,
                    "purpose": "execution_plan",
                    "is_primary": 1,
                },
                0,
                "登记任务对应方案章节",
                **auth(ref),
            )
            plans.verify_task_plan_reference(
                db, PROJECT, ref, saved["revision"], hashes[PLAN], **auth(ref + ":verify")
            )
        task = CHILDREN[0]
        revision = service.get_task(db, task)["revision"]
        revision = service.transition(db, task, revision, "ready", **auth("01:ready"))["revision"]
        revision = service.transition(db, task, revision, "in_progress", **auth("01:start"))[
            "revision"
        ]
        results = [
            {
                "criterion_id": key,
                "passed": True,
                "evidence_id": ident,
                "evidence_version": hashes[path],
                "explanation": "已核对固定证据",
            }
            for key, ident, path in (
                ("report", "WB-15-01-report", REPORT),
                ("samples", "WB-15-01-samples", SAMPLES),
            )
        ]
        revision = service.submit_review(
            db, task, revision, results, "基线和隔离样本通过", **auth("01:submit")
        )["revision"]
        service.accept_review(db, task, revision, "固定证据可用，验收通过", **auth("01:accept"))
        if any(digest(path) != sha for path, sha in hashes.items()):
            raise RuntimeError("evidence changed during registration")


def main():
    _, _, db = load(ROOT / "configs/workbench.yaml")
    baseline = OUT / "baseline.sqlite"
    expected = snapshot(baseline)
    hashes = {path: digest(path) for path in (PLAN, REPORT, SAMPLES)}
    rehearsal = OUT / "registration-rehearsal.sqlite"
    if rehearsal.exists():
        raise RuntimeError("rehearsal already exists")
    with sqlite3.connect(baseline) as src, sqlite3.connect(rehearsal) as dst:
        src.backup(dst)
    register(rehearsal, expected, hashes)
    assert service.get_task(rehearsal, "WB-15-01")["status"] == "done"
    register(db, expected, hashes)
    assert service.get_task(db, "WB-15-01")["status"] == "done"
    print("WB-15 registered; WB-15-01 accepted; rehearsal and baseline retained")


if __name__ == "__main__":
    main()
