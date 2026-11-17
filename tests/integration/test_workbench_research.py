import pytest
from fastapi.testclient import TestClient

from catalyst_ai.web.app import create_app
from catalyst_ai.workbench import research, service


def test_independent_reviews_conflicts_missing_roles_and_invalidated_evidence(tmp_path):
    db = tmp_path / "wb.sqlite"
    client = TestClient(create_app(db, tmp_path), base_url="http://localhost")
    service.set_evidence(
        db, "cat-ai", "a", "a" * 64, "test", "available", request_id="e", actor="test"
    )
    content = dict(
        title="Model",
        object_type="model",
        classification="validated",
        scope="Frozen evaluation",
        conclusion="Limited",
        limitations="Not causal",
        evidence=[],
    )
    with pytest.raises(service.Conflict, match="snapshot"):
        research.save(db, "cat-ai", "claims", "C", content, 0, request_id="bad", actor="test")
    content.update(
        classification="implemented",
        evidence=[dict(id="a", version="a" * 64, role=role) for role in ("code", "test")],
    )
    result = research.save(db, "cat-ai", "claims", "C", content, 0, request_id="ok", actor="test")
    assert result["revision"] == 1
    with pytest.raises(service.Conflict, match="revision"):
        research.save(db, "cat-ai", "claims", "C", content, 0, request_id="stale", actor="test")
    service.set_evidence(
        db, "cat-ai", "a", "a" * 64, "test", "missing", request_id="missing", actor="test"
    )
    assert research.list_records(db, "cat-ai", "claims")[0]["needs_review"]
    assert client.get("/research").status_code == 200
    assert client.get("/api/workbench/v1/claims").json()["items"][0]["needs_review"]
    assert client.post("/api/workbench/v1/issues", json={}).status_code == 403
    assert client.get("/api/workbench/v1/model-runs").status_code == 200
