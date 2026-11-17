import hashlib
import json
import shutil
from pathlib import Path

import pytest

from catalyst_ai.reporting.evidence import digest
from catalyst_ai.storage.workbench import connect, migrate
from catalyst_ai.workbench import adapters, index, service


@pytest.fixture
def setup_index(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    db = tmp_path / "workbench.sqlite"
    migrate(db)
    service.create_project(db, "p", "project", request_id="project", actor="tester")
    index.configure_workspace(db, "p", root, request_id="workspace", actor="tester")
    return db, root


def register(db, artifact_id, kind, path):
    return index.register(
        db, "p", artifact_id, kind, path, request_id="reg-" + path, actor="tester"
    )


def snapshot(path, values):
    content = {"records": values}
    sha = digest(content)
    path.write_text(
        json.dumps({"snapshot_id": "snapshot-" + sha, "content_sha256": sha, "content": content}),
        encoding="utf8",
    )


def test_versions_preview_corruption_and_missing(setup_index):
    db, root = setup_index
    source = root / "snapshot.json"
    snapshot(source, [1, 2, 3])
    register(db, "a", "snapshot", "snapshot.json")
    first = index.scan(db, "p")
    artifact = index.get_artifact(db, "a")
    version = artifact["revisions"][0]["file_sha256"]
    assert index.preview(db, "a", version, offset=1, limit=1)["items"] == [2]
    snapshot(source, [4])
    with pytest.raises(service.Conflict):
        index.preview(db, "a", version)
    index.scan(db, "p")
    old = next(r for r in index.get_artifact(db, "a")["revisions"] if r["file_sha256"] == version)
    assert old["status"] == "changed"
    source.write_text("{broken", encoding="utf8")
    scan = index.get_scan(db, index.scan(db, "p"))
    assert scan["observations"][0]["status"] == "invalid"
    source.unlink()
    scan = index.get_scan(db, index.scan(db, "p"))
    assert scan["observations"][0]["status"] == "missing"
    assert index.get_scan(db, first)["status"] == "complete"


def test_interrupted_scan_does_not_publish(setup_index, monkeypatch):
    db, root = setup_index
    snapshot(root / "s.json", [1])
    register(db, "a", "snapshot", "s.json")
    published = index.scan(db, "p")

    def interrupt(*args):
        raise KeyboardInterrupt()

    monkeypatch.setattr(adapters, "inspect", interrupt)
    with pytest.raises(KeyboardInterrupt):
        index.scan(db, "p")
    assert index.list_artifacts(db, "p")["scan_id"] == published
    con = connect(db)
    running = con.execute("SELECT id FROM index_scan WHERE status='running'").fetchone()[0]
    con.close()
    index.interrupt_scan(db, running)
    assert index.get_scan(db, running)["status"] == "interrupted"
    assert index.list_artifacts(db, "p")["scan_id"] == published


def test_multiple_locations_preserve_available_version(setup_index):
    db, root = setup_index
    snapshot(root / "a.json", [1])
    shutil.copyfile(root / "a.json", root / "b.json")
    register(db, "a", "snapshot", "a.json")
    register(db, "a", "snapshot", "b.json")
    index.scan(db, "p")
    version = index.get_artifact(db, "a")["revisions"][0]["file_sha256"]
    (root / "a.json").unlink()
    index.scan(db, "p")
    assert index.get_artifact(db, "a")["revisions"][0]["status"] == "available"
    assert index.preview(db, "a", version)["path"] == "b.json"


def test_accepted_evidence_refresh_blocks_dependents(setup_index):
    db, root = setup_index
    snapshot(root / "a.json", [1])
    register(db, "a", "snapshot", "a.json")
    index.scan(db, "p")
    version = index.get_artifact(db, "a")["revisions"][0]["file_sha256"]
    for task in ("one", "two"):
        service.create_task(
            db,
            {
                "id": task,
                "project_id": "p",
                "title": task,
                "goal": "g",
                "deliverables": ["report"],
                "criteria": [{"id": "c", "description": "check"}],
            },
            request_id="create-" + task,
            actor="tester",
        )
    service.transition(db, "one", 1, "ready", request_id="ready", actor="tester")
    service.transition(db, "one", 2, "in_progress", request_id="start", actor="tester")
    service.submit_review(
        db,
        "one",
        3,
        [{"criterion_id": "c", "passed": True, "evidence_id": "a", "evidence_version": version}],
        "ok",
        request_id="submit",
        actor="tester",
    )
    service.accept_review(db, "one", 4, "ok", request_id="accept", actor="tester")
    service.add_dependency(db, "two", "one", 1, request_id="dependency", actor="tester")
    snapshot(root / "a.json", [2])
    index.scan(db, "p")
    assert service.get_task(db, "one")["evidence_needs_review"]
    with pytest.raises(service.Conflict, match="dependency"):
        service.transition(db, "two", 2, "ready", request_id="ready2", actor="tester")


def test_workspace_boundary(setup_index, tmp_path):
    db, root = setup_index
    with pytest.raises(ValueError):
        register(db, "a", "document", "../outside")
    assert not (root / "outside").exists()


def test_real_sources_and_catalog_are_read_only():
    root = Path(__file__).resolve().parents[2]
    files = [
        (
            "snapshot",
            "data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json",
        ),
        (
            "qualification",
            "data/snapshots/qualifications/qualification-b450e999aca00cd7e035b5bb1006a48d3fbd171520391710eb05a2490aa85967.json",
        ),
        ("split", "artifacts/reports/themecat-i2-20261110/split-verified.json"),
        ("selection", "artifacts/reports/s1-b-20261113-v4/selection.json"),
        ("features", "artifacts/reports/s1-b-20261113-v4/features.json"),
        ("report", "artifacts/reports/themecat-r1-comparison-20261112-verified/report.json"),
        ("model", "artifacts/models/themecat-r1-prediction-20261112-final/manifest.json"),
    ]
    if (
        not all((root / path).is_file() for _, path in files)
        or not (root / "data/catalog.sqlite").is_file()
    ):
        pytest.skip("local source artifacts not available")
    db = root / "data/catalog.sqlite"
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    for kind, path in files:
        assert adapters.inspect(root, path, kind, 64 * 1024 * 1024)["content_id"]
    result = adapters.verify_feature_catalog(db, root / files[3][1], root / files[4][1])
    assert result["rows"] == 553
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_scan_publish_conflict_preserves_previous(setup_index, monkeypatch):
    db, root = setup_index
    snapshot(root / "a.json", [1])
    snapshot(root / "b.json", [2])
    register(db, "a", "snapshot", "a.json")
    previous = index.scan(db, "p")
    original = adapters.inspect

    def change_scope(*args):
        register(db, "b", "snapshot", "b.json")
        return original(*args)

    monkeypatch.setattr(adapters, "inspect", change_scope)
    with pytest.raises(service.Conflict, match="scope"):
        index.scan(db, "p")
    assert index.list_artifacts(db, "p")["scan_id"] == previous


def test_model_manifest_detects_tampering(setup_index):
    db, root = setup_index
    package = root / "model"
    package.mkdir()
    data = b"never unpickle this"
    (package / "model.pkl").write_bytes(data)
    manifest = {"artifact_sha256": hashlib.sha256(data).hexdigest(), "schema_version": "test"}
    manifest["model_id"] = "r1-" + digest(manifest)
    (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf8")
    register(db, "model", "model", "model/manifest.json")
    index.scan(db, "p")
    assert index.get_artifact(db, "model")["revisions"][0]["status"] == "available"
    (package / "model.pkl").write_bytes(b"modified")
    result = index.get_scan(db, index.scan(db, "p"))
    assert result["observations"][0]["status"] == "invalid"
    assert index.get_artifact(db, "model")["revisions"][0]["status"] == "invalid"


def test_v1_upgrade_preserves_data_and_creates_backup(tmp_path):
    db = tmp_path / "v1.sqlite"
    migrate(db)
    service.create_project(db, "p", "project", request_id="p", actor="tester")
    con = connect(db)
    for table in (
        "research_record",
        "model_run_revision",
        "model_run",
        "foundation_record",
        "foundation_import",
        "task_decision",
        "decision_revision",
        "decision",
    ):
        con.execute(f"DROP TABLE {table}")
    con.execute("ALTER TABLE project DROP COLUMN focus_task_id")
    for table in (
        "published_index",
        "index_observation",
        "index_scan",
        "artifact_revision",
        "artifact_location",
        "artifact",
        "index_workspace",
    ):
        con.execute(f"DROP TABLE {table}")
    con.execute("PRAGMA user_version=1")
    con.close()
    migrate(db)
    backup = connect(tmp_path / "v1.sqlite.v1.backup")
    assert backup.execute("PRAGMA user_version").fetchone()[0] == 1
    assert backup.execute("SELECT name FROM project WHERE id='p'").fetchone()[0] == "project"
    backup.close()
    assert service.list_tasks(db, "p") == []
