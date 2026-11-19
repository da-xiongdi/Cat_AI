import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from threading import Barrier

import pytest

from catalyst_ai.storage.workbench import connect, migrate
from catalyst_ai.workbench.index import configure_workspace, get_artifact, register, scan
from catalyst_ai.workbench.plans import (
    inspect_task_plan_reference,
    list_document_purposes,
    list_plan_verifications,
    list_task_plan_references,
    save_document_purpose,
    save_task_plan_reference,
    verify_task_plan_reference,
)
from catalyst_ai.workbench.service import Conflict, Missing, create_project, create_task

ACTOR = "wb13-05-acceptance"
REFERENCE = {
    "task_id": "task",
    "document_id": "doc",
    "path": "docs/plan.md",
    "section_locator": "Plan",
    "purpose": "execution_plan",
    "is_primary": 1,
}


@pytest.fixture
def workspace(tmp_path):
    db_path = tmp_path / "acceptance.sqlite"
    root = tmp_path / "workspace"
    (root / "docs").mkdir(parents=True)
    plan = root / REFERENCE["path"]
    plan.write_text("# Plan\nOriginal text\n", encoding="utf-8")
    migrate(db_path)
    create_project(db_path, "p", "Project", request_id="project", actor=ACTOR)
    configure_workspace(db_path, "p", root, request_id="workspace", actor=ACTOR)
    register(db_path, "p", "doc", "document", REFERENCE["path"], request_id="doc", actor=ACTOR)
    create_task(
        db_path,
        {"id": "task", "project_id": "p", "title": "Test task", "goal": "Test goal"},
        request_id="task",
        actor=ACTOR,
    )
    save_reference(db_path, "primary", REFERENCE)
    return db_path, plan


def save_reference(db_path, reference_id, data, revision=0):
    return save_task_plan_reference(
        db_path,
        "p",
        reference_id,
        data,
        revision,
        "Acceptance test",
        request_id=f"{reference_id}-{revision}",
        actor=ACTOR,
    )


def inspect_reference(db_path):
    return inspect_task_plan_reference(db_path, "p", "primary")


def verify_reference(db_path, checksum, request_id, revision=1):
    return verify_task_plan_reference(
        db_path, "p", "primary", revision, checksum, request_id=request_id, actor=ACTOR
    )


def test_multiple_documents_purposes_and_primary_conflict(workspace):
    db_path, plan = workspace
    with closing(connect(db_path)) as db:
        before_version = db.execute("PRAGMA user_version").fetchone()[0]
        task_before = tuple(db.execute("SELECT * FROM task").fetchone())
    plan.with_name("reference.md").write_text("# Reference\nDetails\n", encoding="utf-8")
    register(
        db_path, "p", "ref", "document", "docs/reference.md", request_id="doc-ref", actor=ACTOR
    )
    purpose = {"document_id": "ref", "purpose": "research_plan", "category": "research"}
    saved = save_document_purpose(
        db_path, "p", "purpose", purpose, 0, "Reference plan", request_id="purpose", actor=ACTOR
    )
    assert list_document_purposes(db_path, "p") == [saved]
    with pytest.raises(Conflict, match="duplicate document purpose"):
        save_document_purpose(
            db_path, "p", "duplicate", purpose, 0, "Duplicate", request_id="duplicate", actor=ACTOR
        )
    reference = {
        **REFERENCE,
        "document_id": "ref",
        "path": "docs/reference.md",
        "section_locator": "Reference",
        "purpose": "research_plan",
        "is_primary": 0,
    }
    save_reference(db_path, "secondary", reference)
    with pytest.raises(Conflict, match="primary"):
        save_reference(
            db_path, "second-primary", {**reference, "purpose": "execution_plan", "is_primary": 1}
        )
    assert [
        (r["reference"]["id"], r["reference"]["is_primary"])
        for r in list_task_plan_references(db_path, "p", "task")
    ] == [("primary", 1), ("secondary", 0)]
    with closing(connect(db_path)) as db:
        assert tuple(db.execute("SELECT * FROM task").fetchone()) == task_before
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA user_version").fetchone()[0] == before_version == 8
        counts = {
            table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (
                "task",
                "document_purpose",
                "document_purpose_revision",
                "task_plan_reference",
                "task_plan_reference_revision",
                "task_plan_verification",
            )
        }
        assert list(counts.values()) == [1, 1, 1, 2, 2, 0]
        print(f"Isolated schema: {before_version} -> 8; integrity=ok; foreign keys=ok; {counts}")


def test_cross_project_task_document_purpose_and_history(workspace):
    db_path, plan = workspace
    create_project(db_path, "other", "Other", request_id="other", actor=ACTOR)
    configure_workspace(db_path, "other", plan.parents[1], request_id="other-root", actor=ACTOR)
    register(
        db_path,
        "other",
        "other-doc",
        "document",
        REFERENCE["path"],
        request_id="other-doc",
        actor=ACTOR,
    )
    create_task(
        db_path,
        {"id": "other-task", "project_id": "other", "title": "Other", "goal": "Other"},
        request_id="other-task",
        actor=ACTOR,
    )
    for key, value in (("task_id", "other-task"), ("document_id", "other-doc")):
        with pytest.raises(ValueError, match="does not belong to project"):
            save_reference(db_path, f"reject-{key}", {**REFERENCE, key: value})
    with pytest.raises(ValueError, match="document does not belong to project"):
        save_document_purpose(
            db_path,
            "p",
            "foreign-purpose",
            {"document_id": "other-doc", "purpose": "acceptance"},
            0,
            "Cross-project test",
            request_id="foreign-purpose",
            actor=ACTOR,
        )
    verify_reference(db_path, inspect_reference(db_path)["current_sha256"], "verified")
    with pytest.raises(Missing, match="plan reference not found"):
        list_plan_verifications(db_path, "other", "primary")


def test_actual_bytes_override_stale_available_index_and_history_survives(workspace):
    db_path, plan = workspace
    scan(db_path, "p")
    first_hash = sha256(plan.read_bytes()).hexdigest()
    assert get_artifact(db_path, "doc")["revisions"][0]["file_sha256"] == first_hash
    old = verify_reference(db_path, first_hash, "verify-first")
    plan.write_text("# Plan\nUpdated text\n", encoding="utf-8")
    second_hash = sha256(plan.read_bytes()).hexdigest()
    detected = inspect_reference(db_path)
    assert (detected["status"], detected["current_sha256"], detected["last_verification"]) == (
        "changed",
        second_hash,
        old,
    )
    assert list_plan_verifications(db_path, "p", "primary") == [old]
    with pytest.raises(Conflict):
        verify_reference(db_path, first_hash, "verify-stale-hash")
    new = verify_reference(db_path, second_hash, "verify-second")
    assert inspect_reference(db_path)["status"] == "valid"
    plan.unlink()
    observations = get_artifact(db_path, "doc")["observations"]
    assert observations[0]["status"] == "available"
    detected = inspect_reference(db_path)
    assert (detected["status"], detected["current_sha256"], detected["last_verification"]) == (
        "missing_or_invalid",
        None,
        new,
    )
    assert list_plan_verifications(db_path, "p", "primary") == [old, new]
    print(f"Isolated source SHA-256: original={first_hash}; updated={second_hash}")


@pytest.mark.parametrize(
    ("replacement", "expected"),
    [("# Renamed\n", "section_missing"), ("# Plan\n## Plan\n", "section_ambiguous")],
)
def test_renamed_or_duplicate_heading_preserves_old_verification(workspace, replacement, expected):
    db_path, plan = workspace
    old = verify_reference(db_path, inspect_reference(db_path)["current_sha256"], "verified")
    plan.write_text(replacement, encoding="utf-8")
    detected = inspect_reference(db_path)
    assert detected["status"] == expected
    assert detected["last_verification"] == old
    with pytest.raises(Conflict, match=expected):
        verify_reference(db_path, detected["current_sha256"], "invalid-section")
    assert list_plan_verifications(db_path, "p", "primary") == [old]


def test_rejects_absolute_and_parent_paths_on_registration(workspace):
    db_path, plan = workspace
    for number, value in enumerate((str(plan.resolve()), "../outside.md")):
        with pytest.raises(ValueError, match="path must be relative"):
            save_reference(db_path, f"escaped-{number}", {**REFERENCE, "path": value})


def test_concurrent_same_request_appends_once_and_stale_revision_conflicts(workspace):
    db_path, _ = workspace
    checksum = inspect_reference(db_path)["current_sha256"]
    ready = Barrier(2, timeout=10)

    def send():
        ready.wait()
        return verify_reference(db_path, checksum, "simultaneous")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = [pool.submit(send) for _ in range(2)]
        old = first.result(timeout=10)
        assert old == second.result(timeout=10)
    updated = save_reference(db_path, "primary", {**REFERENCE, "is_primary": 0}, revision=1)
    assert updated["revision"] == 2
    with pytest.raises(Conflict, match="revision conflict"):
        verify_reference(db_path, checksum, "stale-tab")
    assert list_plan_verifications(db_path, "p", "primary") == [old]
    with closing(connect(db_path)) as db:
        assert (
            db.execute("SELECT count(*) FROM activity WHERE action='plan_verified'").fetchone()[0]
            == 1
        )
        assert (
            db.execute("SELECT count(*) FROM request_log WHERE request_id='stale-tab'").fetchone()[
                0
            ]
            == 0
        )


def test_renamed_heading_is_not_replaced_by_a_fenced_example(workspace):
    db_path, plan = workspace
    old = verify_reference(db_path, inspect_reference(db_path)["current_sha256"], "verified")
    plan.write_text("# Renamed\n\n```markdown\n# Plan\n```\n", encoding="utf-8")
    detected = inspect_reference(db_path)
    assert detected["last_verification"] == old
    accepted = None
    try:
        accepted = verify_reference(db_path, detected["current_sha256"], "fenced-example")
    except Conflict as exc:
        assert "section_missing" in str(exc)
    assert (detected["status"], accepted) == ("section_missing", None)
    assert list_plan_verifications(db_path, "p", "primary") == [old]


def test_registered_path_with_escaped_directory_reports_status(workspace, tmp_path, monkeypatch):
    db_path, plan = workspace
    old = verify_reference(db_path, inspect_reference(db_path)["current_sha256"], "verified")
    root = plan.parent.parent
    (root / "other.md").write_text("# Plan\n", encoding="utf-8")
    register(db_path, "p", "other", "document", "other.md", request_id="other", actor=ACTOR)
    save_reference(
        db_path,
        "secondary",
        {**REFERENCE, "document_id": "other", "path": "other.md", "is_primary": 0},
    )
    outside = tmp_path / "outside"
    plan.parent.rename(outside)
    if os.name == "nt":
        subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(plan.parent), str(outside)],
            check=True,
            capture_output=True,
        )
    else:
        plan.parent.symlink_to(outside, target_is_directory=True)
    try:
        original_read = Path.read_bytes

        def checked_read(path):
            assert not path.is_relative_to(outside)
            return original_read(path)

        monkeypatch.setattr(Path, "read_bytes", checked_read)
        with pytest.raises(ValueError, match="path escapes workspace"):
            save_reference(db_path, "escaped", REFERENCE)
        assert list_plan_verifications(db_path, "p", "primary") == [old]
        detected = inspect_reference(db_path)
        assert detected["status"] == "path_escape"
        assert detected["current_sha256"] is None
        assert detected["last_verification"] == old
        references = list_task_plan_references(db_path, "p", "task")
        assert references[0] == detected
        assert references[1]["status"] == "unverified"
        with pytest.raises(Conflict, match="path_escape"):
            verify_reference(db_path, old["file_sha256"], "escaped-verification")
        assert list_plan_verifications(db_path, "p", "primary") == [old]
    finally:
        if os.name == "nt":
            plan.parent.rmdir()
        else:
            plan.parent.unlink()


def test_implementation_plan_section_can_be_referenced(workspace):
    db_path, plan = workspace
    source = Path("docs/workbench/wb13_implementation_plan.md")
    plan.write_bytes(source.read_bytes())
    locator = "WB-13-05：执行计划与文档引用"
    updated = save_reference(
        db_path, "primary", {**REFERENCE, "section_locator": locator}, revision=1
    )
    checksum = sha256(source.read_bytes()).hexdigest()
    assert inspect_reference(db_path)["current_sha256"] == checksum
    verified = verify_reference(
        db_path, checksum, "verify-repo-section", revision=updated["revision"]
    )
    assert verified["file_sha256"] == checksum
