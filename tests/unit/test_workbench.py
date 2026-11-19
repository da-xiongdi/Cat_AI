from concurrent.futures import ThreadPoolExecutor

import pytest

from catalyst_ai.storage.workbench import atomic_operations, connect, migrate
from catalyst_ai.workbench import service as s


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "workbench.sqlite"
    migrate(path)
    s.create_project(path, "p", "Project", request_id="project", actor="A")
    return path


def create(db, name):
    return s.create_task(
        db,
        {
            "id": name,
            "project_id": "p",
            "title": name,
            "goal": "goal",
            "deliverables": ["report"],
            "criteria": [{"id": "c", "description": "check"}],
        },
        request_id="create-" + name,
        actor="A",
    )


def move(db, task, revision, target, **kwargs):
    return s.transition(
        db, task, revision, target, request_id=f"{task}-{revision}-{target}", actor="A", **kwargs
    )


def complete(db, task):
    move(db, task, 1, "ready")
    move(db, task, 2, "in_progress")
    s.submit_review(
        db,
        task,
        3,
        [{"criterion_id": "c", "passed": True, "evidence_id": "e", "evidence_version": "v1"}],
        "checked",
        request_id=task + "-submit",
        actor="A",
    )
    s.accept_review(db, task, 4, "accepted", request_id=task + "-accept", actor="B")


def test_operation_batch_rolls_back_tasks_and_idempotency_records(db):
    with pytest.raises(s.Conflict, match="invalid state transition"):
        with atomic_operations(db):
            create(db, "a")
            assert s.get_task(db, "a")["status"] == "planned"
            move(db, "a", 1, "in_progress")
    with pytest.raises(s.Missing):
        s.get_task(db, "a")
    with atomic_operations(db):
        create(db, "a")
        move(db, "a", 1, "ready")
    assert s.get_task(db, "a")["status"] == "ready"


def test_acceptance_and_changed_evidence_blocks_dependency(db):
    create(db, "a")
    create(db, "b")
    s.set_evidence(db, "p", "e", "v1", "report hash", "available", request_id="e1", actor="A")
    complete(db, "a")
    s.add_dependency(db, "b", "a", 1, request_id="dep", actor="A")
    s.set_evidence(db, "p", "e", "v1", "report hash", "changed", request_id="e2", actor="A")
    assert s.get_task(db, "a")["evidence_needs_review"]
    with pytest.raises(s.Conflict, match="dependency"):
        move(db, "b", 2, "ready")
    assert len(s.get_task(db, "a")["reviews"]) == 2
    assert s.get_task(db, "b")["revision"] == 2


def test_cycle_idempotence_and_conflicts(db):
    create(db, "a")
    create(db, "b")
    result = s.add_dependency(db, "a", "b", 1, request_id="d", actor="A")
    assert s.add_dependency(db, "a", "b", 1, request_id="d", actor="A") == result
    with pytest.raises(s.Conflict, match="request ID"):
        s.add_dependency(db, "a", "b", 2, request_id="d", actor="A")
    with pytest.raises(s.Conflict, match="cyclic"):
        s.add_dependency(db, "b", "a", 1, request_id="cycle", actor="A")
    with pytest.raises(s.Conflict, match="revision"):
        move(db, "a", 1, "ready")


def test_review_failure_and_reopening_preserves_versions(db):
    create(db, "a")
    move(db, "a", 1, "ready")
    move(db, "a", 2, "in_progress")
    with pytest.raises(s.Conflict):
        s.submit_review(db, "a", 3, [], "missing", request_id="bad", actor="A")
    s.submit_review(
        db,
        "a",
        3,
        [{"criterion_id": "c", "passed": False, "explanation": "not done"}],
        "unresolved",
        request_id="submit",
        actor="A",
    )
    with pytest.raises(s.Conflict, match="not passed"):
        s.accept_review(db, "a", 4, "accepted", request_id="accept", actor="A")
    move(db, "a", 4, "in_progress", reason="fix")
    s.submit_review(
        db,
        "a",
        5,
        [{"criterion_id": "c", "passed": True, "explanation": "verified manually"}],
        "fixed",
        request_id="submit2",
        actor="A",
    )
    s.accept_review(db, "a", 6, "accepted", request_id="accept2", actor="B")
    move(db, "a", 7, "in_progress", reason="scope changed")
    with pytest.raises(s.Conflict, match="new criteria"):
        s.update_task(db, "a", 8, {"goal": "new scope"}, request_id="scope", actor="A")
    s.update_task(
        db,
        "a",
        8,
        {"criteria": [{"id": "new", "description": "new scope"}]},
        request_id="update",
        actor="A",
    )
    task = s.get_task(db, "a")
    assert task["criteria_version"] == 2
    assert task["reviews"][-1]["criteria_version"] == 1


def test_concurrent_writes_one_conflict(db):
    create(db, "a")

    def update(i):
        try:
            return s.update_task(db, "a", 1, {"title": str(i)}, request_id=f"u{i}", actor="A")
        except s.Conflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, [1, 2]))
    assert sum(x is not None for x in results) == 1
    assert len(s.get_task(db, "a")["activity"]) == 2


def test_migration_backup_and_idempotence(tmp_path):
    path = tmp_path / "old.sqlite"
    db = connect(path)
    db.execute("CREATE TABLE old_data(value TEXT)")
    db.execute("INSERT INTO old_data VALUES('retained')")
    db.close()
    migrate(path)
    backup = connect(tmp_path / "old.sqlite.v0.backup")
    assert backup.execute("SELECT value FROM old_data").fetchone()[0] == "retained"
    backup.close()
    migrate(path)
