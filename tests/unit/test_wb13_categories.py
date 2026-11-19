import sqlite3

import pytest

from catalyst_ai.storage.workbench import connect, migrate
from catalyst_ai.workbench.service import (
    Conflict,
    apply_task_categories,
    create_project,
    create_task,
    get_task,
    list_tasks_by_category,
    set_task_category,
)


def test_category_preserves_task_and_checks_revision(tmp_path):
    path = tmp_path / "workbench.sqlite"
    migrate(path)
    create_project(path, "p", "Project", request_id="p", actor="tester")
    create_task(
        path,
        {"id": "t", "project_id": "p", "title": "T", "goal": "G"},
        request_id="t",
        actor="tester",
    )
    before = get_task(path, "t")
    result = set_task_category(
        path, "p", "t", "research", 1, "evidence", request_id="c", actor="tester"
    )
    assert result == set_task_category(
        path, "p", "t", "research", 1, "evidence", request_id="c", actor="tester"
    )
    after = get_task(path, "t")
    for key in before.keys() - {"category", "revision", "activity"}:
        assert before[key] == after[key]
    assert after["revision"] == 2
    assert list_tasks_by_category(path, "p", "research")[0]["id"] == "t"
    with pytest.raises(Conflict):
        set_task_category(
            path, "p", "t", "workbench", 1, "correction", request_id="stale", actor="tester"
        )
    with pytest.raises(ValueError):
        set_task_category(
            path, "other", "t", "workbench", 2, "correction", request_id="other", actor="tester"
        )


def test_failed_migration_rolls_back_and_backup_is_not_overwritten(tmp_path):
    path = tmp_path / "db.sqlite"
    migrate(path)
    db = connect(path)
    db.execute("PRAGMA user_version=7")
    db.close()
    # Existing category makes the schema-8 ALTER fail after BEGIN.
    with pytest.raises(sqlite3.OperationalError):
        migrate(path)
    backup = path.with_name(path.name + ".v7.backup")
    contents = backup.read_bytes()
    with pytest.raises(FileExistsError):
        migrate(path)
    assert backup.read_bytes() == contents
    db = connect(path)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 7
    db.close()


def test_batch_conflict_rolls_back(tmp_path):
    path = tmp_path / "db.sqlite"
    migrate(path)
    create_project(path, "p", "Project", request_id="p", actor="tester")
    for task_id in ("a", "b"):
        create_task(
            path,
            {"id": task_id, "project_id": "p", "title": task_id, "goal": "g"},
            request_id=task_id,
            actor="tester",
        )
    proposals = [
        {"task_id": "a", "category": "research", "expected_revision": 1, "evidence": "goal"},
        {"task_id": "b", "category": "research", "expected_revision": 99, "evidence": "goal"},
    ]
    with pytest.raises(Conflict):
        apply_task_categories(path, "p", proposals, request_id="batch", actor="tester")
    assert get_task(path, "a")["category"] is None
    assert get_task(path, "a")["revision"] == 1


def test_partial_ddl_failure_rolls_back(tmp_path):
    source = tmp_path / "source.sqlite"
    migrate(source)
    db = connect(source)
    db.execute("PRAGMA user_version=7")
    db.close()
    # Drop only early schema-8 objects, so a later CREATE fails after ALTER succeeds.
    db = connect(source)
    db.execute("DROP TABLE task_category_revision")
    db.execute("ALTER TABLE task DROP COLUMN category")
    db.close()
    with pytest.raises(sqlite3.OperationalError):
        migrate(source)
    db = connect(source)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 7
    assert "category" not in [row[1] for row in db.execute("PRAGMA table_info(task)")]
    assert not db.execute(
        "SELECT 1 FROM sqlite_master WHERE name='task_category_revision'"
    ).fetchone()
    db.close()
