import pytest

from catalyst_ai.storage.workbench import migrate
from catalyst_ai.workbench.category_context import (
    get_category_context,
    migrate_legacy_focus,
    save_recent_task,
    set_category_focus,
)
from catalyst_ai.workbench.decisions import set_focus
from catalyst_ai.workbench.service import Conflict, create_project, create_task


def test_category_focus_and_recent(tmp_path):
    path = tmp_path / "db.sqlite"
    migrate(path)
    create_project(path, "p", "P", request_id="p", actor="a")
    for task, category in (("r", "research"), ("w", "workbench"), ("u", None)):
        create_task(
            path,
            {"id": task, "project_id": "p", "title": task, "goal": "g", "category": category},
            request_id=task,
            actor="a",
        )
    set_focus(path, "p", "u", request_id="legacy", actor="a")
    assert migrate_legacy_focus(path, "p", 0, request_id="m", actor="a")["needs_review"]
    set_category_focus(path, "p", "research", "r", 0, "focus", request_id="f1", actor="a")
    set_category_focus(path, "p", "workbench", "w", 0, "focus", request_id="f2", actor="a")
    assert get_category_context(path, "p", "research")["context"]["focus_task_id"] == "r"
    with pytest.raises(ValueError):
        set_category_focus(path, "p", "research", "w", 1, "bad", request_id="bad", actor="a")
    with pytest.raises(Conflict):
        set_category_focus(path, "p", "research", "r", 0, "stale", request_id="stale", actor="a")
    save_recent_task(path, "p", "research", "r", 1, 1, 0, "add", request_id="recent", actor="a")
    with pytest.raises(Conflict):
        save_recent_task(
            path, "p", "research", "r", 1, 1, 0, "duplicate", request_id="duplicate", actor="a"
        )
    assert len(get_category_context(path, "p", "research")["recent"]) == 1
    set_focus(path, "p", "r", request_id="legacy2", actor="a")
    assert get_category_context(path, "p", "research")["context"]["focus_task_id"] == "r"
    set_category_focus(path, "p", "research", None, 1, "clear", request_id="clear", actor="a")
    cleared = get_category_context(path, "p", "research")
    assert cleared["context"]["focus_task_id"] is None
    assert cleared["legacy_focus_task_id"] is None
    assert not cleared["legacy_needs_migration"]
    assert get_category_context(path, "p", "workbench")["context"]["focus_task_id"] == "w"


def test_legacy_migration_conflict_and_unknown(tmp_path):
    from catalyst_ai.storage.workbench import transaction

    path = tmp_path / "db.sqlite"
    migrate(path)
    create_project(path, "p", "P", request_id="p", actor="a")
    for task, category in (("r", "research"), ("r2", "research"), ("u", None)):
        create_task(
            path,
            {"id": task, "project_id": "p", "title": task, "goal": "g", "category": category},
            request_id=task,
            actor="a",
        )
    with transaction(path) as db:
        db.execute("UPDATE project SET focus_task_id='r' WHERE id='p'")
    first = migrate_legacy_focus(path, "p", 0, request_id="m1", actor="a")
    assert first == migrate_legacy_focus(path, "p", 0, request_id="m1", actor="a")
    assert (
        migrate_legacy_focus(path, "p", 1, request_id="m2", actor="a")["context"]["revision"] == 1
    )
    with transaction(path) as db:
        db.execute("UPDATE project SET focus_task_id='r2' WHERE id='p'")
    with pytest.raises(Conflict):
        migrate_legacy_focus(path, "p", 1, request_id="m3", actor="a")
    assert get_category_context(path, "p", "research")["context"]["focus_task_id"] == "r"
    with transaction(path) as db:
        db.execute("UPDATE project SET focus_task_id='u' WHERE id='p'")
    set_category_focus(path, "p", "research", "r2", 1, "change", request_id="f", actor="a")
    view = get_category_context(path, "p", "research")
    assert view["legacy_focus_task_id"] == "u" and view["legacy_needs_review"]
    with transaction(path) as db:
        assert db.execute("SELECT count(*) FROM category_context_revision").fetchone()[0] == 2


def test_order_history_and_category_changes(tmp_path):
    from catalyst_ai.storage.workbench import transaction
    from catalyst_ai.workbench.service import set_task_category, transition

    path = tmp_path / "db.sqlite"
    migrate(path)
    for project in ("p", "other"):
        create_project(path, project, project, request_id=project, actor="a")
    for task, priority, date, project in (
        ("a", "high", "2026-12-01", "p"),
        ("b", "urgent", None, "p"),
        ("c", "high", "2026-12-01", "p"),
        ("x", "urgent", None, "other"),
    ):
        create_task(
            path,
            {
                "id": task,
                "project_id": project,
                "title": task,
                "goal": "g",
                "category": "research",
                "priority": priority,
                "planned_date": date,
            },
            request_id=task,
            actor="a",
        )
    set_category_focus(path, "p", "research", "a", 0, "focus", request_id="f", actor="a")
    assert [t["id"] for t in get_category_context(path, "p", "research")["default_order"]] == [
        "b",
        "a",
        "c",
    ]
    for task, order in (("a", 2), ("b", 1), ("c", 2)):
        save_recent_task(
            path, "p", "research", task, order, 1, 0, "add", request_id="add" + task, actor="a"
        )
    with pytest.raises(Exception) as error:
        set_category_focus(
            path, "p", "research", "x", 1, "cross project", request_id="cross", actor="a"
        )
    from catalyst_ai.workbench.service import Missing

    assert isinstance(error.value, Missing)
    assert [t["task_id"] for t in get_category_context(path, "p", "research")["recent"]] == [
        "b",
        "a",
        "c",
    ]
    transition(path, "b", 1, "cancelled", request_id="cancel", actor="a", reason="cancel")
    set_task_category(
        path, "p", "a", "workbench", 1, "correction", request_id="category", actor="a"
    )
    view = get_category_context(path, "p", "research")
    assert view["focus_needs_review"]
    assert {t["task_id"]: t["needs_review"] for t in view["recent"]} == {
        "a": True,
        "b": True,
        "c": False,
    }
    removed = save_recent_task(
        path, "p", "research", "a", 2, 0, 1, "archive", request_id="archive", actor="a"
    )
    assert removed["revision"] == 2
    assert len(get_category_context(path, "p", "research")["recent"]) == 3
    with transaction(path) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM category_recent_task_revision WHERE entity_id=?",
                (removed["id"],),
            ).fetchone()[0]
            == 2
        )
        assert db.execute("SELECT status FROM task WHERE id='a'").fetchone()[0] == "planned"


def test_unmigrated_legacy_is_preserved_and_concurrent_writes_conflict(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from catalyst_ai.storage.workbench import transaction

    path = tmp_path / "db.sqlite"
    migrate(path)
    create_project(path, "p", "P", request_id="p", actor="a")
    for task, category in (("r", "research"), ("w", "workbench"), ("w2", "workbench")):
        create_task(
            path,
            {"id": task, "project_id": "p", "title": task, "goal": "g", "category": category},
            request_id=task,
            actor="a",
        )
    with transaction(path) as db:
        db.execute("UPDATE project SET focus_task_id='r' WHERE id='p'")
    set_category_focus(path, "p", "workbench", "w", 0, "new", request_id="new", actor="a")
    view = get_category_context(path, "p", "research")
    assert view["legacy_focus_task_id"] == "r" and view["legacy_needs_migration"]
    set_focus(path, "p", "w", request_id="legacy-write", actor="a")
    assert get_category_context(path, "p", "research")["context"]["focus_task_id"] == "r"

    def update(task):
        try:
            return set_category_focus(
                path, "p", "workbench", task, 1, "concurrent", request_id="race-" + task, actor="a"
            )
        except Conflict:
            return None

    # One update changes the value; both writers carry the same expected revision.
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, ("w2", "w2")))
    # Same request is idempotent, including under concurrent delivery.
    assert results[0] == results[1] and results[0]["revision"] == 2
    with pytest.raises(Conflict):
        set_category_focus(path, "p", "workbench", "w", 1, "stale", request_id="stale2", actor="a")


def test_competing_arrangements_reject_stale_revision(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "db.sqlite"
    migrate(path)
    create_project(path, "p", "P", request_id="p", actor="a")
    create_task(
        path,
        {"id": "t", "project_id": "p", "title": "t", "goal": "g", "category": "research"},
        request_id="t",
        actor="a",
    )
    set_category_focus(path, "p", "research", "t", 0, "focus", request_id="f", actor="a")
    save_recent_task(path, "p", "research", "t", 0, 1, 0, "add", request_id="add", actor="a")

    def update(order):
        try:
            return save_recent_task(
                path,
                "p",
                "research",
                "t",
                order,
                1,
                1,
                "reorder",
                request_id=f"order-{order}",
                actor="a",
            )
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, (1, 2)))
    assert sum(result is not None for result in results) == 1
    assert get_category_context(path, "p", "research")["recent"][0]["revision"] == 2
