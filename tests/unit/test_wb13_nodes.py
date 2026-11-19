from pathlib import Path

import pytest

from catalyst_ai.storage.workbench import connect, migrate
from catalyst_ai.workbench.index import configure_workspace
from catalyst_ai.workbench.research_nodes import (
    list_research_nodes,
    preview_research_nodes,
    save_research_node,
    save_task_node_link,
)
from catalyst_ai.workbench.service import Conflict, create_project, create_task


def test_nodes_and_links(tmp_path):
    db = tmp_path / "test.sqlite"
    migrate(db)
    for p in ("p", "q"):
        create_project(db, p, p, request_id=p, actor="a")
    configure_workspace(db, "p", Path.cwd(), request_id="workspace", actor="a")
    preview = preview_research_nodes(db, "p")
    root = preview["nodes"][0]

    def node(id, data, rev, request):
        return save_research_node(db, "p", id, data, rev, "test", request_id=request, actor="a")

    first = node("root", root, 0, "root")
    assert node("root", root, 0, "root") == first
    node("child", {**root, "parent_id": "root"}, 0, "child")
    with pytest.raises(ValueError):
        node("root", {**root, "parent_id": "child"}, 1, "cycle")
    with pytest.raises(Conflict):
        node("root", root, 0, "stale")
    for id, category, project in [
        ("t", "research", "p"),
        ("w", "workbench", "p"),
        ("x", "research", "q"),
    ]:
        create_task(
            db,
            {
                "id": id,
                "project_id": project,
                "title": id,
                "goal": "g",
                "category": category,
                "stages": ["A"],
                "primary_stage": "A",
            },
            request_id=id,
            actor="a",
        )

    def link(id, task, n, role, request):
        return save_task_node_link(
            db,
            "p",
            id,
            {"task_id": task, "node_id": n, "role": role},
            0,
            "test",
            request_id=request,
            actor="a",
        )

    link("l1", "t", "root", "primary", "l1")
    link("l2", "t", "child", "reference", "l2")
    with pytest.raises(Conflict):
        link("l3", "t", "child", "primary", "l3")
    for task in ("w", "x"):
        with pytest.raises(ValueError):
            link("bad" + task, task, "root", "reference", "bad" + task)
    summary = list_research_nodes(db, "p")
    assert summary["nodes"][0]["task_count"] == 1
    assert not summary["nodes"][0]["complete"]
    conn = connect(db)
    assert conn.execute("SELECT count(*) FROM dependency").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM research_node_revision").fetchone()[0] == 2
    conn.close()


def test_linked_task_edits_and_source_conflicts(tmp_path):
    from catalyst_ai.workbench.service import get_task, set_task_category, update_task

    db = tmp_path / "test.sqlite"
    migrate(db)
    create_project(db, "p", "P", request_id="p", actor="a")
    configure_workspace(db, "p", tmp_path, request_id="workspace", actor="a")
    source = tmp_path / "plan.md"
    source.write_text("# Stage A\n", encoding="utf-8")
    import hashlib

    node = {
        "stage": "A",
        "parent_id": None,
        "sort_order": 0,
        "source_path": "plan.md",
        "source_section": "Stage A",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }
    save_research_node(db, "p", "n", node, 0, "source", request_id="n", actor="a")
    create_task(
        db,
        {
            "id": "t",
            "project_id": "p",
            "title": "T",
            "goal": "G",
            "category": "research",
            "stages": ["A"],
            "primary_stage": "A",
        },
        request_id="t",
        actor="a",
    )
    save_task_node_link(
        db,
        "p",
        "l",
        {"task_id": "t", "node_id": "n", "role": "primary"},
        0,
        "link",
        request_id="l",
        actor="a",
    )
    with pytest.raises(Conflict):
        set_task_category(db, "p", "t", "workbench", 1, "change", request_id="c", actor="a")
    with pytest.raises(Conflict):
        update_task(db, "t", 1, {"stages": ["B"], "primary_stage": "B"}, request_id="u", actor="a")
    assert get_task(db, "t")["revision"] == 1
    source.write_text("# Stage A\nchanged", encoding="utf-8")
    with pytest.raises(Conflict):
        save_research_node(
            db, "p", "n", {**node, "sort_order": 1}, 1, "change", request_id="n2", actor="a"
        )
    conn = connect(db)
    assert conn.execute("SELECT revision FROM research_node WHERE id='n'").fetchone()[0] == 1
    conn.close()


def test_preview_proposes_sourced_branches(tmp_path):
    db = tmp_path / "test.sqlite"
    migrate(db)
    create_project(db, "p", "P", request_id="p", actor="a")
    configure_workspace(db, "p", Path.cwd(), request_id="workspace", actor="a")
    create_task(
        db,
        {
            "id": "S2-01",
            "project_id": "p",
            "title": "T",
            "goal": "G",
            "category": "research",
            "stages": ["C"],
            "primary_stage": "C",
        },
        request_id="t",
        actor="a",
    )
    result = preview_research_nodes(db, "p")
    assert result["link_candidates"][0]["task_id"] == "S2-01"
    assert any(n["source_section"].startswith("S2-01") for n in result["nodes"])


def test_atomic_initialization_revision_and_replay(tmp_path):
    from catalyst_ai.workbench.research_nodes import apply_research_initialization

    db = tmp_path / "test.sqlite"
    migrate(db)
    create_project(db, "p", "P", request_id="p", actor="a")
    configure_workspace(db, "p", Path.cwd(), request_id="workspace", actor="a")
    create_task(
        db,
        {
            "id": "S2-01",
            "project_id": "p",
            "title": "T",
            "goal": "G",
            "category": "research",
            "stages": ["C"],
            "primary_stage": "C",
        },
        request_id="t",
        actor="a",
    )
    preview = preview_research_nodes(db, "p")
    nodes = preview["nodes"]
    candidate = preview["link_candidates"][0]
    link = {**candidate, "id": "link", "expected_revision": 0}

    def apply(links, request):
        return apply_research_initialization(
            db, "p", nodes, links, "reviewed", request_id=request, actor="a"
        )

    with pytest.raises(Conflict):
        apply([{**link, "task_revision": 999}], "bad")
    conn = connect(db)
    assert conn.execute("SELECT count(*) FROM research_node").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM research_node_revision").fetchone()[0] == 0
    conn.close()
    result = apply([link], "good")
    assert apply([link], "good") == result
    conn = connect(db)
    assert conn.execute("SELECT count(*) FROM task_node_link").fetchone()[0] == 1
    conn.close()
