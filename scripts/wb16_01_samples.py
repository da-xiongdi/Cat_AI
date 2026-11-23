"""Capture a read-only baseline and exercise plan handoff on an isolated copy."""

import json
import sqlite3
from pathlib import Path

from catalyst_ai.web.config import load
from catalyst_ai.workbench import category_context, index, plans, queries, service

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/wb16-01-samples"
PROJECT = "cat-ai"


def auth(key):
    return {"request_id": "wb16-sample:" + key, "actor": "Codex"}


def main():
    _, _, source = load(ROOT / "configs/workbench.yaml")
    OUT.mkdir(parents=True, exist_ok=False)
    original = OUT / "baseline.sqlite"
    with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as src:
        with sqlite3.connect(original) as dst:
            src.backup(dst)
    baseline = queries.query(original, PROJECT)
    (OUT / "baseline-query.json").write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    workspace = OUT / "sample-workspace"
    workspace.mkdir()
    db = workspace / "management.sqlite"
    with sqlite3.connect(original) as src, sqlite3.connect(db) as dst:
        src.backup(dst)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE index_workspace SET root=? WHERE project_id=?", (str(workspace), PROJECT)
        )

    for ident, category in (
        ("WB16-SAMPLE-R", "research"),
        ("WB16-SAMPLE-W", "workbench"),
        ("WB16-SAMPLE-NONE", "research"),
    ):
        service.create_task(
            db,
            {
                "id": ident,
                "project_id": PROJECT,
                "title": ident,
                "goal": "隔离样本",
                "category": category,
                "deliverables": ["样本结果"],
                "criteria": [{"id": "check", "description": "检查样本"}],
            },
            **auth(ident),
        )
    service.transition(db, "WB16-SAMPLE-W", 1, "ready", **auth("ready"))
    service.transition(
        db,
        "WB16-SAMPLE-W",
        2,
        "blocked",
        reason="科研前置任务尚未完成",
        recovery_condition="完成科研前置任务",
        **auth("blocked"),
    )
    service.add_dependency(db, "WB16-SAMPLE-W", "WB16-SAMPLE-R", 3, **auth("dependency"))

    entries = (
        ("R", "research", "WB16-SAMPLE-R", "科研计划"),
        ("W", "workbench", "WB16-SAMPLE-W", "建设计划"),
    )
    for suffix, category, task, heading in entries:
        name = f"{suffix}.md"
        (workspace / name).write_text(f"# {heading}\n原始内容\n", encoding="utf-8")
        index.register(
            db, PROJECT, "WB16-SAMPLE-DOC-" + suffix, "document", name, **auth("doc-" + suffix)
        )
        ref = "WB16-SAMPLE-REF-" + suffix
        plans.save_task_plan_reference(
            db,
            PROJECT,
            ref,
            {
                "task_id": task,
                "document_id": "WB16-SAMPLE-DOC-" + suffix,
                "path": name,
                "section_locator": heading,
                "purpose": "execution_plan",
                "is_primary": 1,
            },
            0,
            "隔离样本",
            **auth("ref-" + suffix),
        )
        check = plans.inspect_task_plan_reference(db, PROJECT, ref)
        plans.verify_task_plan_reference(
            db, PROJECT, ref, 1, check["current_sha256"], **auth("verify-" + suffix)
        )
        context = category_context.get_category_context(db, PROJECT, category)["context"]
        category_context.set_category_focus(
            db,
            PROJECT,
            category,
            task,
            context["revision"] if context else 0,
            "隔离样本",
            **auth("focus-" + suffix),
        )
        category_context.save_recent_task(
            db, PROJECT, category, task, 0, 1, 0, "隔离样本", **auth("recent-" + suffix)
        )

    view = queries.query(db, PROJECT)
    assert view["primary_plans"]["WB16-SAMPLE-R"]["status"] == "valid"
    assert view["primary_plans"]["WB16-SAMPLE-W"]["status"] == "valid"
    assert view["primary_plans"]["WB16-SAMPLE-NONE"] is None
    for _suffix, category, task, _ in entries:
        ctx = view["contexts"][category]
        assert ctx["context"]["focus_task_id"] == task
        assert any(item["task_id"] == task and item["active"] for item in ctx["recent"])
    task = service.get_task(db, "WB16-SAMPLE-W")
    assert task["status"] == "blocked" and task["dependencies"] == ["WB16-SAMPLE-R"]
    assert task["blocker"] == "科研前置任务尚未完成"
    (workspace / "R.md").write_text("# 科研计划\n修改后的内容\n", encoding="utf-8")
    changed = plans.inspect_task_plan_reference(db, PROJECT, "WB16-SAMPLE-REF-R")
    assert changed["status"] == "changed" and changed["last_verification"]
    (workspace / "R.md").write_text("# 已改名\n修改后的内容\n", encoding="utf-8")
    missing = plans.inspect_task_plan_reference(db, PROJECT, "WB16-SAMPLE-REF-R")
    assert missing["status"] == "section_missing" and missing["last_verification"]
    output = {
        "valid": {t: view["primary_plans"][t] for _, _, t, _ in entries},
        "no_primary": view["primary_plans"]["WB16-SAMPLE-NONE"],
        "changed": changed,
        "section_missing": missing,
        "blocked_task": task,
        "contexts": view["contexts"],
    }
    (OUT / "sample-results.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("baseline and isolated samples verified:", OUT)


if __name__ == "__main__":
    main()
