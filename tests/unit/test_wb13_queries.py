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
