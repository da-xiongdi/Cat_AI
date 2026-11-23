"""Exercise WB-16 classification evidence on a fresh isolated project."""

import hashlib
import json
from pathlib import Path

from catalyst_ai.storage.workbench import migrate
from catalyst_ai.workbench import deliveries, index, plans, queries, service

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/wb16-01-edge-samples"


def auth(key):
    return {"request_id": "wb16-edge:" + key, "actor": "Codex"}


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    db = OUT / "management.sqlite"
    migrate(db)
    service.create_project(db, "sample", "Sample", **auth("project"))
    index.configure_workspace(db, "sample", OUT, **auth("workspace"))
    empty = queries.query(db, "sample")
    assert empty["total"] == 0 and not empty["historical_deliveries"]
    for task, category in (("r", "research"), ("w", "workbench"), ("u", None)):
        service.create_task(
            db,
            {
                "id": task,
                "project_id": "sample",
                "title": task,
                "goal": "sample",
                "category": category,
                "deliverables": ["report"],
                "criteria": [{"id": "check", "description": "sample"}],
            },
            **auth(task),
        )
    assert [t["id"] for t in queries.query(db, "sample", "unclassified")["tasks"]] == ["u"]
    source = OUT / "shared.md"
    source.write_text("# Shared\nOriginal\n", encoding="utf-8")
    index.register(db, "sample", "shared", "document", "shared.md", **auth("document"))
    for category in ("research", "workbench"):
        plans.save_document_purpose(
            db,
            "sample",
            "purpose-" + category,
            {"document_id": "shared", "purpose": "execution_plan", "category": category},
            0,
            "sample",
            **auth("purpose-" + category),
        )
        task = "r" if category == "research" else "w"
        ref = "ref-" + task
        plans.save_task_plan_reference(
            db,
            "sample",
            ref,
            {
                "task_id": task,
                "document_id": "shared",
                "path": "shared.md",
                "section_locator": "Shared",
                "purpose": "execution_plan",
                "is_primary": 1,
            },
            0,
            "sample",
            **auth(ref),
        )
        inspection = plans.inspect_task_plan_reference(db, "sample", ref)
        plans.verify_task_plan_reference(
            db, "sample", ref, 1, inspection["current_sha256"], **auth("verify-" + task)
        )
    index.scan(db, "sample")
    version = index.get_artifact(db, "shared")["revisions"][0]["file_sha256"]
    for task in ("r", "w"):
        service.transition(db, task, 1, "ready", **auth(task + "-ready"))
        service.transition(db, task, 2, "in_progress", **auth(task + "-start"))
        service.submit_review(
            db,
            task,
            3,
            [
                {
                    "criterion_id": "check",
                    "passed": True,
                    "evidence_id": "shared",
                    "evidence_version": version,
                }
            ],
            "sample",
            **auth(task + "-review"),
        )
        service.accept_review(db, task, 4, "sample", **auth(task + "-accept"))
        assert not service.get_task(db, task)["evidence_needs_review"]
    entry = {
        "original_wb_id": "WB-01",
        "delivered_scope": "delivered",
        "remaining_scope": "remaining",
        "source_path": "shared.md",
        "source_section": "Shared",
        "source_sha256": version,
    }
    deliveries.upsert_workbench_delivery(db, "sample", entry, 0, "sample", **auth("delivery"))
    pending = queries.query(db, "sample")["historical_deliveries"]
    assert pending[0]["registration_status"] == "historical_pending_task_registration"
    deliveries.upsert_workbench_delivery(
        db, "sample", {**entry, "task_id": "w"}, 1, "link", **auth("link")
    )
    linked = queries.query(db, "sample")["historical_deliveries"]
    assert linked[0]["task_id"] == "w" and linked[0]["registration_status"] == "registered"
    source.write_text("# Shared\nChanged\n", encoding="utf-8")
    index.scan(db, "sample")
    changed = queries.query(db, "sample")
    assert changed["historical_deliveries"][0]["source_status"] == "changed"
    assert all(service.get_task(db, task)["evidence_needs_review"] for task in ("r", "w"))
    assert all(changed["primary_plans"][task]["status"] == "changed" for task in ("r", "w"))
    purposes = plans.list_document_purposes(db, "sample")
    assert {p["category"] for p in purposes} == {"research", "workbench"}
    assert len(index.list_artifacts(db, "sample")["items"]) == 1
    result = {
        "empty_total": empty["total"],
        "unclassified": ["u"],
        "shared_document": "shared",
        "purpose_categories": ["research", "workbench"],
        "shared_evidence_sha256": version,
        "evidence_review_tasks": ["r", "w"],
        "pending_delivery": pending,
        "linked_delivery": linked,
        "changed_delivery": changed["historical_deliveries"],
        "changed_plans": {t: changed["primary_plans"][t]["status"] for t in ("r", "w")},
        "changed_file_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }
    (OUT / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("isolated edge samples passed", OUT)


if __name__ == "__main__":
    main()
