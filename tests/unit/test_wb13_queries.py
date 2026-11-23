import pytest

from catalyst_ai.storage.workbench import migrate
from catalyst_ai.workbench.category_context import set_category_focus
from catalyst_ai.workbench.queries import query
from catalyst_ai.workbench.service import Missing, create_project, create_task


def test_query_scopes_counts_and_focus(tmp_path):
    path = tmp_path / "management.sqlite"
    migrate(path)
    create_project(path, "p", "P", request_id="project", actor="a")
    for task, category in (("r", "research"), ("w", "workbench"), ("u", None)):
        create_task(
            path,
            {"id": task, "project_id": "p", "title": task, "goal": "g", "category": category},
            request_id=task,
            actor="a",
        )
    set_category_focus(path, "p", "research", "r", 0, "focus", request_id="focus", actor="a")
    all_view = query(path, "p")
    assert all_view["total"] == 3
    assert [all_view["counts"][c]["total"] for c in ("research", "workbench", "unclassified")] == [
        1,
        1,
        1,
    ]
    assert all_view["contexts"]["research"]["context"]["focus_task_id"] == "r"
    assert {x["task_id"] for x in all_view["missing"]} == {"r", "w", "u"}
    for scope, task in (("research", "r"), ("workbench", "w"), ("unclassified", "u")):
        view = query(path, "p", scope)
        assert [t["id"] for t in view["tasks"]] == [task]
        assert view["total"] == 1
    with pytest.raises(ValueError):
        query(path, "p", "invalid")
    with pytest.raises(Missing):
        query(path, "unknown")


def test_next_work_orders_deduplicates_and_shows_history(tmp_path):
    from catalyst_ai.storage.workbench import transaction
    from catalyst_ai.workbench.category_context import save_recent_task

    path = tmp_path / "work.sqlite"
    migrate(path)
    create_project(path, "p", "P", request_id="p", actor="a")
    for task, priority in (("a", "low"), ("b", "urgent"), ("c", "high"), ("h", "normal")):
        create_task(
            path,
            {
                "id": task,
                "project_id": "p",
                "title": task,
                "goal": "g",
                "category": "research",
                "priority": priority,
            },
            request_id=task,
            actor="a",
        )
    set_category_focus(path, "p", "research", "a", 0, "focus", request_id="focus", actor="a")
    save_recent_task(path, "p", "research", "a", 2, 1, 0, "add", request_id="recent-a", actor="a")
    save_recent_task(path, "p", "research", "c", 1, 1, 0, "add", request_id="recent-c", actor="a")
    with transaction(path) as db:
        db.execute("UPDATE task SET status='done' WHERE id='h'")
    view = query(path, "p", "research")["next_work"]["research"]
    assert [t["id"] for t in view["active"]] == ["c", "a", "b"]
    assert [t["id"] for t in view["history"]] == ["h"]
    assert all(t["ready_reason"] for t in view["active"])
