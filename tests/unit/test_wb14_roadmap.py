import hashlib
import json

from catalyst_ai.storage.workbench import connect, migrate
from catalyst_ai.workbench.index import configure_workspace
from catalyst_ai.workbench.research_nodes import save_research_node, save_task_node_link
from catalyst_ai.workbench.roadmap import snapshot
from catalyst_ai.workbench.service import create_project, create_task


def test_roadmap_snapshot_deduplicates_and_tracks_evidence(tmp_path):
    db = tmp_path / "db.sqlite"
    migrate(db)
    create_project(db, "p", "P", request_id="p", actor="a")
    configure_workspace(db, "p", tmp_path, request_id="workspace", actor="a")
    source = tmp_path / "source.md"
    source.write_text("# Stage\n", encoding="utf-8")
    node = {
        "stage": "A",
        "parent_id": None,
        "sort_order": 0,
        "source_path": "source.md",
        "source_section": "Stage",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }
    for id, parent in (
        ("root", None),
        ("child", "root"),
        ("deep", "child"),
        ("empty", "root"),
        ("cancel", "root"),
    ):
        save_research_node(
            db, "p", id, {**node, "parent_id": parent}, 0, "test", request_id=id, actor="a"
        )
    for id, category in (
        ("done", "research"),
        ("cancelled", "research"),
        ("pending", "research"),
        ("wb", "workbench"),
        ("unknown", None),
    ):
        create_task(
            db,
            {
                "id": id,
                "project_id": "p",
                "title": id,
                "goal": "g",
                "category": category,
                "stages": ["A"],
                "primary_stage": "A",
            },
            request_id="t-" + id,
            actor="a",
        )
    for id, task, target, role in (
        ("l1", "done", "child", "primary"),
        ("l2", "done", "deep", "reference"),
        ("l3", "cancelled", "cancel", "primary"),
    ):
        save_task_node_link(
            db,
            "p",
            id,
            {"task_id": task, "node_id": target, "role": role},
            0,
            "test",
            request_id=id,
            actor="a",
        )
    with connect(db) as conn:
        conn.execute("UPDATE task SET status='done' WHERE id='done'")
        conn.execute("UPDATE task SET status='cancelled' WHERE id='cancelled'")
        conn.execute("INSERT INTO evidence VALUES('e','v','p','e','available','now')")
        conn.execute(
            "INSERT INTO review(task_id,criteria_version,kind,conclusion,actor,created_at,results) "
            "VALUES(?,1,'acceptance','pass','a','now',?)",
            ("done", json.dumps([{"evidence_id": "e", "evidence_version": "v"}])),
        )
    result = snapshot(db, "p")
    assert result["summary"]["task_ids"] == ["cancelled", "done"]
    assert result["summary"]["valid_total"] == result["summary"]["valid_completed"] == 1
    assert result["nodes"]["child"]["summary"]["task_ids"] == ["done"]
    assert result["nodes"]["empty"]["empty_state"] == "undecomposed"
    assert result["nodes"]["cancel"]["empty_state"] == "cancelled_only"
    assert result["pending_task_ids"] == ["pending"]
    assert [t["id"] for t in result["unclassified_tasks"]] == ["unknown"]
    assert result["nodes"]["root"]["summary"]["scope_incomplete"]
    assert not result["stages"][1]["registered"]
    with connect(db) as conn:
        conn.execute("UPDATE task SET category=NULL WHERE id='pending'")
    assert snapshot(db, "p")["nodes"]["deep"]["summary"]["included_scope_complete"]
    with connect(db) as conn:
        conn.execute("UPDATE evidence SET status='changed' WHERE id='e'")
    source.write_text("# Stage\nchanged\n", encoding="utf-8")
    result = snapshot(db, "p")
    assert result["tasks"]["done"]["status"] == "done"
    assert result["summary"]["evidence_review_task_ids"] == ["done"]
    assert result["summary"]["valid_completed"] == 0
    assert result["summary"]["source_needs_review"]
    assert result["nodes"]["deep"]["source_status"] == "changed"


def test_empty_project_has_six_unregistered_stages(tmp_path):
    db = tmp_path / "empty.sqlite"
    migrate(db)
    create_project(db, "p", "P", request_id="p", actor="a")
    result = snapshot(db, "p")
    assert [stage["stage"] for stage in result["stages"]] == list("ABCDEF")
    assert not any(stage["registered"] for stage in result["stages"])
    assert result["summary"]["scope_incomplete"]
    assert not result["summary"]["included_scope_complete"]
