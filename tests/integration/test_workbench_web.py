import re

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from catalyst_ai.web.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "wb.sqlite", tmp_path)
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        yield client


def csrf(client, url="/tasks/new"):
    body = client.get(url).text
    return re.search(r'name="csrf" value="([^"]+)"', body).group(1)


def post(client, action, data, token, request_id):
    return client.post(
        "/actions/" + action,
        data={**data, "csrf": token, "actor": "tester", "request_id": request_id},
        follow_redirects=False,
    )


def test_full_review_and_conflict_preserves_input(client):
    token = csrf(client)
    create = {
        "task_id": "T1",
        "title": "Example",
        "goal": "Goal",
        "deliverables": "Report",
        "criteria": "c | Check",
        "priority": "normal",
    }
    assert post(client, "create-task", create, token, "create").status_code == 303
    assert (
        post(
            client,
            "transition",
            {"task_id": "T1", "revision": 1, "target": "ready"},
            token,
            "ready",
        ).status_code
        == 303
    )
    stale = post(
        client, "edit-task", {**create, "title": "My unsaved change", "revision": 1}, token, "stale"
    )
    assert stale.status_code == 409
    assert "My unsaved change" in stale.text
    assert (
        post(
            client,
            "transition",
            {"task_id": "T1", "revision": 2, "target": "in_progress"},
            token,
            "start",
        ).status_code
        == 303
    )
    assert (
        post(
            client,
            "submit-review",
            {
                "task_id": "T1",
                "revision": 3,
                "result-c": "pass",
                "explanation-c": "checked",
                "conclusion": "ok",
            },
            token,
            "submit",
        ).status_code
        == 303
    )
    assert (
        post(
            client,
            "accept-review",
            {"task_id": "T1", "revision": 4, "conclusion": "accepted"},
            token,
            "accept",
        ).status_code
        == 303
    )
    page = client.get("/tasks/T1")
    assert page.status_code == 200 and "accepted" in page.text and "已完成" in page.text


def test_navigation_and_sample_page(client):
    page = client.get("/")
    assert "项目管理" in page.text and "实验验证与回灌" in page.text
    assert client.get("/foundation/samples").status_code == 200
    pending = client.get("/pending/screening")
    assert pending.status_code == 200 and "此模块待接入" in pending.text
    assert "T1" in client.get("/tasks?status=done&q=T1").text


def test_csrf_origin_host_and_escaped_content(client):
    token = csrf(client)
    assert client.post("/actions/focus", data={"csrf": "wrong"}).status_code == 403
    assert (
        client.post(
            "/actions/focus", data={"csrf": token}, headers={"Origin": "http://evil.example"}
        ).status_code
        == 403
    )
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 403
    data = {"task_id": "T1", "title": "<script>alert(1)</script>", "goal": "g"}
    assert post(client, "create-task", data, token, "xss").status_code == 303
    body = client.get("/tasks/T1").text
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


def test_artifact_decision_and_documents(client, tmp_path):
    token = csrf(client)
    (tmp_path / "doc.md").write_text("# source\n<script>unsafe</script>", encoding="utf-8")
    assert (
        post(
            client,
            "register",
            {"artifact_id": "doc1", "kind": "document", "path": "doc.md"},
            token,
            "reg",
        ).status_code
        == 303
    )
    assert post(client, "scan", {}, token, "scan").status_code == 303
    assert "doc1" in client.get("/documents").text
    body = client.get("/artifacts/doc1").text
    version = re.search(r"/download/([0-9a-f]{64})", body).group(1)
    preview = client.get("/artifacts/doc1", params={"version": version})
    assert "&lt;script&gt;unsafe&lt;/script&gt;" in preview.text
    assert (
        client.get(f"/artifacts/doc1/download/{version}").content
        == (tmp_path / "doc.md").read_bytes()
    )
    data = {
        "decision_id": "D1",
        "revision": "0",
        "title": "Decision",
        "background": "Context",
        "conclusion": "Result",
        "source": "doc.md",
    }
    assert post(client, "save-decision", data, token, "decision").status_code == 303
    assert "Decision" in client.get("/decisions/D1").text
    assert "Result" in client.get("/decisions/D1/export").text


def test_config_rejects_domain_database(tmp_path):
    domain = tmp_path / "data" / "catalog.sqlite"
    with pytest.raises(ValueError, match="domain"):
        create_app(domain, tmp_path)
    assert not domain.exists()


def test_decision_revision_conflict_and_history(client):
    token = csrf(client)
    data = {
        "decision_id": "D1",
        "revision": "0",
        "title": "Initial",
        "background": "Context",
        "conclusion": "First",
    }
    assert post(client, "save-decision", data, token, "d1").status_code == 303
    data.update(revision="1", title="Revised", conclusion="Second")
    assert post(client, "save-decision", data, token, "d2").status_code == 303
    conflict = post(client, "save-decision", data, token, "d3")
    assert conflict.status_code == 409
    page = client.get("/decisions/D1")
    assert "Initial" in page.text and "Revised" in page.text


def test_upgrade_v2_preserves_tasks_and_backup(tmp_path):
    from catalyst_ai.storage.workbench import connect, migrate
    from catalyst_ai.workbench import service

    db = tmp_path / "workbench.sqlite"
    migrate(db)
    service.create_project(db, "p", "Existing", request_id="old-project", actor="A")
    service.create_task(
        db,
        {"id": "old", "project_id": "p", "title": "Old", "goal": "Goal"},
        request_id="old-task",
        actor="A",
    )
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
    con.execute("PRAGMA user_version=2")
    con.close()
    migrate(db)
    assert service.get_task(db, "old")["title"] == "Old"
    backup = connect(tmp_path / "workbench.sqlite.v2.backup")
    assert backup.execute("PRAGMA user_version").fetchone()[0] == 2
    assert backup.execute("SELECT title FROM task WHERE id='old'").fetchone()[0] == "Old"
    backup.close()


def test_historical_r1_registration_and_summary(tmp_path):
    import hashlib
    import json

    from catalyst_ai.reporting.evidence import digest
    from catalyst_ai.workbench import index
    from catalyst_ai.workbench.service import Conflict

    def write(relative, data):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    metric = {"records": 47, "papers": 6, "mae": 4.1}
    availability = {"available_records": 29, "total_records": 47}
    report = {
        "schema_version": "r1-oof-comparison-v1",
        "selected": {"feature_set": "F_base", "model": "extra_trees"},
        "selection": {"content": {}},
        "configuration": {},
        "oof_scores": {"F_base": {"extra_trees": metric}},
        "oof_availability": {"F_base": {"extra_trees": availability}},
        "validation": {"candidates": {"F_base": {"metrics": metric, "availability": availability}}},
        "test": {"candidates": {"F_base": {"metrics": metric, "availability": availability}}},
    }
    report["content_sha256"] = digest(report)
    model_bytes = b"fixture model; never loaded"
    model = {
        "report_sha256": "incorrect",
        "artifact_sha256": hashlib.sha256(model_bytes).hexdigest(),
    }
    model["model_id"] = "r1-" + digest(model)
    report_path = "artifacts/reports/themecat-r1-comparison-20261112-verified/report.json"
    model_dir = "artifacts/models/themecat-r1-prediction-20261112-final/"
    write(report_path, json.dumps(report).encode())
    write(
        "artifacts/reports/themecat-r1-prediction-20261112-final/report.json",
        json.dumps(report).encode(),
    )
    write(model_dir + "model.pkl", model_bytes)
    write(model_dir + "manifest.json", json.dumps(model).encode())
    write("artifacts/reports/themecat-i5-20261110/model_card.md", b"I5")
    write("artifacts/reports/themecat-i5-20261110/diagnostics.json", b"{}")
    db = tmp_path / "wb.sqlite"
    app = create_app(db, tmp_path)
    with pytest.raises(Conflict):
        index.register_historical_r1(db, "cat-ai", request_id="bad", actor="tester")
    assert index.list_artifacts(db, "cat-ai")["items"] == []
    model.pop("model_id")
    model["report_sha256"] = report["content_sha256"]
    model["model_id"] = "r1-" + digest(model)
    write(model_dir + "manifest.json", json.dumps(model).encode())
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        token = csrf(client)
        assert post(client, "register-historical-r1", {}, token, "r1").status_code == 303
        assert post(client, "register-historical-r1", {}, token, "r1").status_code == 303
        index.scan(db, "cat-ai")
        page = client.get("/model-evidence").text
        assert "R1-comparison" in page and "I5-model-card" in page
        assert "available_records" in page and "29" in page
        assert "\u65e7\u6a21\u578b" in page
        assert (
            post(
                client,
                "create-task",
                {"task_id": "T-R1", "title": "R1", "goal": "Review"},
                token,
                "task-r1",
            ).status_code
            == 303
        )
        assert (
            post(client, "register-r1-run", {"task_id": "T-R1"}, token, "run1").status_code == 303
        )
        assert "R1-prediction" in client.get("/tasks/T-R1").text
        assert "R1-prediction" in client.get("/search?q=R1-prediction").text
        run = client.get("/api/workbench/v1/model-runs/R1-prediction").json()
        assert run["revision"] == 1
        content = run["history"][0]["content"]
        for ref in content["evidence"]:
            ref.pop("status")
        body = {
            "id": "R1-prediction",
            "content": content,
            "expected_revision": 1,
            "request_id": "edit-run",
            "actor": "tester",
        }
        api = "/api/workbench/v1/model-runs"
        assert client.post(api, json=body).status_code == 403
        assert client.post(api, json=body, headers={"x-csrf-token": token}).status_code == 200
        body["request_id"] = "stale-run"
        assert client.post(api, json=body, headers={"x-csrf-token": token}).status_code == 409
        write(model_dir + "model.pkl", b"changed")
        index.scan(db, "cat-ai")
        changed = client.get("/api/workbench/v1/model-runs/R1-prediction").json()
        assert len(changed["history"]) == 2
        assert changed["history"][0]["content"]["evidence"][0]["status"] == "invalid"
    assert len(index.list_artifacts(db, "cat-ai")["items"]) == 5
