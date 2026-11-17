import json

import pytest
from fastapi.testclient import TestClient

from catalyst_ai.storage.workbench import migrate, transaction
from catalyst_ai.web.app import create_app
from catalyst_ai.workbench import backup, foundation, samples
from catalyst_ai.workbench.service import Conflict


def make_backup():
    data = {kind: [] for kind in foundation.KINDS}
    data.update(version=1, settings={"capacity": 4, "workspaceRevision": "1.1"})
    data["sources"] = [{"id": "S1", "title": "原始来源"}]
    data["records"] = [{"id": "R1", "sourceId": "S1", "status": "已核验"}]
    return data


def raw(data):
    return json.dumps(data, ensure_ascii=False).encode()


def test_import_idempotency_revisions_and_atomic_conflict(tmp_path):
    db = tmp_path / "workbench.sqlite"
    migrate(db)
    with transaction(db) as conn:
        conn.execute("INSERT INTO project(id,name) VALUES('p','test')")
    data = make_backup()
    first = foundation.stage(db, "p", "json", raw(data), "tester")
    assert foundation.stage(db, "p", "json", raw(data), "tester")["id"] == first["id"]
    foundation.apply(db, "p", first["id"], first["sha256"])
    data["sources"][0]["title"] = "新来源"
    data["records"].append({"id": "R2", "sourceId": "S1"})
    second = foundation.stage(db, "p", "json", raw(data), "tester")
    with pytest.raises(Conflict):
        foundation.apply(db, "p", second["id"], second["sha256"])
    assert len(foundation.list_records(db, "p", "records")) == 1
    foundation.apply(db, "p", second["id"], second["sha256"], conflict="revise")
    assert foundation.list_records(db, "p", "sources")[0]["revision"] == 2
    assert len(foundation.list_records(db, "p", "records")) == 2


def test_invalid_references_stay_staged(tmp_path):
    db = tmp_path / "workbench.sqlite"
    migrate(db)
    with transaction(db) as conn:
        conn.execute("INSERT INTO project(id,name) VALUES('p','test')")
    data = make_backup()
    data["records"][0]["sourceId"] = "missing"
    batch = foundation.stage(db, "p", "json", raw(data), "tester")
    assert batch["report"]["errors"]
    with pytest.raises(Conflict):
        foundation.apply(db, "p", batch["id"], batch["sha256"])


def test_web_upload_preview_and_apply(tmp_path):
    client = TestClient(
        create_app(tmp_path / "workbench.sqlite", tmp_path, project_id="p"),
        base_url="http://localhost",
    )
    import re

    page = client.get("/foundation")
    token = re.search(r'name="csrf" value="([^"]+)', page.text).group(1)
    response = client.post(
        "/foundation/preview",
        data={"csrf": token, "actor": "tester", "format": "json"},
        files={"file": ("backup.json", raw(make_backup()), "application/json")},
    )
    assert response.status_code == 200
    batch_id = re.search(r'name="id" value="([^"]+)', response.text).group(1)
    sha = re.search(r'name="sha256" value="([^"]+)', response.text).group(1)
    response = client.post(
        "/foundation/apply",
        data={"csrf": token, "id": batch_id, "sha256": sha, "conflict": "reject"},
    )
    assert response.status_code == 200
    assert "原始来源" in response.text


def test_domain_samples_are_read_only(tmp_path):
    import sqlite3

    path = tmp_path / "catalog.sqlite"
    assert samples.list_samples(path)["status"] == "unavailable"
    assert not path.exists()
    with sqlite3.connect(path) as conn:
        conn.executescript(
            "CREATE TABLE test_run(id TEXT,synthesis_id TEXT,payload TEXT);"
            "CREATE TABLE performance_observation(id TEXT,test_id TEXT,payload TEXT);"
            "INSERT INTO test_run VALUES('T1','S1','{}');"
            "INSERT INTO performance_observation VALUES('O1','T1','{}');"
        )
    before = path.read_bytes()
    result = samples.list_samples(path)
    assert result["total"] == 1
    assert result["items"][0]["observations"] == [{}]
    assert path.read_bytes() == before


@pytest.fixture
def foundation_db(tmp_path):
    path = tmp_path / "workbench.sqlite"
    migrate(path)
    with transaction(path) as conn:
        conn.execute("INSERT INTO project(id,name) VALUES('p','test')")
    return path


@pytest.mark.parametrize("revision", [None, "1.1"])
def test_legacy_custom_fields_and_missing_methanol(foundation_db, revision):
    data = make_backup()
    if revision is None:
        data["settings"].pop("workspaceRevision")
    data["settings"]["capacity"] = "4"
    data["fields"] = [{"id": "F-X", "key": "surface", "name": "表面特征", "category": "结构"}]
    data["records"][0].update(conv=0, sel="", extras={"surface": 3.5})
    batch = foundation.stage(foundation_db, "p", "json", raw(data), "tester")
    assert not batch["report"]["errors"]
    assert batch["report"]["warnings"]
    foundation.apply(foundation_db, "p", batch["id"], batch["sha256"])
    dictionary = foundation.field_dictionary(foundation_db, "p")
    assert len(dictionary) == 37
    assert len({item["category"] for item in dictionary}) == 5
    assert dictionary[-1]["data_type"] == "number"
    assert not dictionary[-1]["training_available"]
    assert foundation.export_data(foundation_db, "p")["records"][0]["conv"] == 0


@pytest.mark.parametrize(
    "kind,key,value",
    [
        ("records", "conv", 101),
        ("records", "temp", "NaN"),
        ("records", "extras", []),
        ("screenings", "modelId", "missing"),
        ("experiments", "candidateId", "missing"),
        ("experiments", "batchId", "missing"),
    ],
)
def test_invalid_values_and_links(foundation_db, kind, key, value):
    data = make_backup()
    data[kind] = [{"id": "bad", key: value}]
    batch = foundation.stage(foundation_db, "p", "json", raw(data), "tester")
    assert batch["report"]["errors"]
    with pytest.raises(Conflict):
        foundation.apply(foundation_db, "p", batch["id"], batch["sha256"])
    assert foundation.list_records(foundation_db, "p", "sources") == []


def test_concurrent_preview_cannot_overwrite_new_revision(foundation_db):
    data = make_backup()
    first = foundation.stage(foundation_db, "p", "json", raw(data), "tester")
    data["sources"][0]["title"] = "另一标签页"
    other = foundation.stage(foundation_db, "p", "json", raw(data), "tester")
    foundation.apply(foundation_db, "p", first["id"], first["sha256"])
    with pytest.raises(Conflict, match="预览已过期"):
        foundation.apply(foundation_db, "p", other["id"], other["sha256"], conflict="revise")
    other = foundation.stage(foundation_db, "p", "json", raw(data), "tester")
    foundation.apply(foundation_db, "p", other["id"], other["sha256"], conflict="revise")


def test_bundle_restores_import_history_and_files(foundation_db, tmp_path):
    data = make_backup()
    batch = foundation.stage(foundation_db, "p", "json", raw(data), "tester")
    foundation.apply(foundation_db, "p", batch["id"], batch["sha256"])
    evidence = tmp_path / "report.txt"
    evidence.write_text("证据", encoding="utf-8")
    with transaction(foundation_db) as conn:
        conn.execute("INSERT INTO artifact VALUES('a','p','text','now')")
        conn.execute("INSERT INTO artifact_location VALUES('a','report.txt')")
    content = backup.create_bundle(foundation_db, tmp_path)
    preview = backup.preview_bundle(content)
    target = tmp_path / "restored"
    with pytest.raises(ValueError, match="哈希"):
        backup.restore_bundle(content, target, "incorrect")
    assert not target.exists()
    backup.restore_bundle(content, target, preview["sha256"])
    restored = target / "workbench.sqlite"
    assert foundation.export_data(restored, "p") == foundation.export_data(foundation_db, "p")
    assert foundation.import_report(restored, "p", batch["id"]) == foundation.import_report(
        foundation_db, "p", batch["id"]
    )
    assert (target / "workspace/report.txt").read_bytes() == evidence.read_bytes()
    with pytest.raises(FileExistsError):
        backup.restore_bundle(content, target, preview["sha256"])


def test_bundle_includes_model_payload_and_reports_hash_mismatch(foundation_db, tmp_path):
    import hashlib
    import json

    model = tmp_path / "model.pkl"
    model.write_bytes(b"fixed model bytes")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"artifact_sha256": hashlib.sha256(model.read_bytes()).hexdigest()})
    )
    with transaction(foundation_db) as conn:
        conn.execute("INSERT INTO artifact VALUES('model','p','model','now')")
        conn.execute("INSERT INTO artifact_location VALUES('model','manifest.json')")
    bundle = backup.create_bundle(foundation_db, tmp_path)
    preview = backup.preview_bundle(bundle)
    assert "workspace/model.pkl" in preview["manifest"]["files"]
    model.write_bytes(b"changed")
    preview = backup.preview_bundle(backup.create_bundle(foundation_db, tmp_path))
    assert any(item["reason"] == "hash_mismatch" for item in preview["manifest"]["missing"])


def test_bundle_rejects_corruption(foundation_db, tmp_path):
    import io
    import zipfile

    content = backup.create_bundle(foundation_db, tmp_path)
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as original, zipfile.ZipFile(output, "w") as altered:
        for name in original.namelist():
            altered.writestr(
                name, b"corrupt" if name == "workbench.sqlite" else original.read(name)
            )
    with pytest.raises(ValueError, match="哈希"):
        backup.preview_bundle(output.getvalue())


def test_interrupted_apply_rolls_back_and_retries(foundation_db, monkeypatch):
    data = make_backup()
    batch = foundation.stage(foundation_db, "p", "json", raw(data), "tester")
    original = foundation._json

    def fail_on_record(obj):
        if isinstance(obj, dict) and obj.get("id") == "R1":
            raise RuntimeError("interrupted")
        return original(obj)

    with monkeypatch.context() as context:
        context.setattr(foundation, "_json", fail_on_record)
        with pytest.raises(RuntimeError, match="interrupted"):
            foundation.apply(foundation_db, "p", batch["id"], batch["sha256"])
    assert foundation.list_records(foundation_db, "p", "sources") == []
    assert foundation.import_report(foundation_db, "p", batch["id"])["status"] == "staged"
    foundation.apply(foundation_db, "p", batch["id"], batch["sha256"])
    assert len(foundation.list_records(foundation_db, "p", "sources")) == 1


def test_registration_review_scope_and_governance(foundation_db):
    source = {
        "id": "S1",
        "title": "来源",
        "reviews": [
            {
                "scope": "数据集来源接受",
                "actor": "tester",
                "conclusion": "接受此版本",
                "evidence_version": "sha256:fixed",
            }
        ],
    }
    batch = foundation.stage_record(foundation_db, "p", "sources", json.dumps(source), "tester")
    foundation.apply(foundation_db, "p", batch["id"], batch["sha256"])
    package = {
        "id": "G1",
        "name": "单位复核",
        "inputs": ["R1"],
        "rule_version": "1",
        "owner": "tester",
        "evidence": "S1",
        "snapshot": "snapshot-v1",
    }
    batch = foundation.stage_record(foundation_db, "p", "governance", json.dumps(package), "tester")
    assert not batch["report"]["errors"]
    foundation.apply(foundation_db, "p", batch["id"], batch["sha256"])
    assert foundation.export_data(foundation_db, "p")["governance"][0] == package
    source["reviews"] = [{"conclusion": "缺少范围"}]
    with pytest.raises(ValueError, match="scope"):
        foundation.stage_record(foundation_db, "p", "sources", json.dumps(source), "tester")
