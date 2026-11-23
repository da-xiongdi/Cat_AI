from pathlib import Path

import pytest

from catalyst_ai.storage.workbench import connect, migrate
from catalyst_ai.workbench.deliveries import (
    list_historical_deliveries,
    preview_historical_deliveries,
    upsert_workbench_delivery,
)
from catalyst_ai.workbench.index import configure_workspace
from catalyst_ai.workbench.service import Conflict, create_project, create_task, get_task


def test_historical_delivery_preview_and_revision(tmp_path):
    db = tmp_path / "db.sqlite"
    migrate(db)
    create_project(db, "p", "Project", request_id="p", actor="test")
    configure_workspace(db, "p", Path.cwd(), request_id="workspace", actor="test")
    preview = preview_historical_deliveries(db, "p")
    assert len(preview) == 12
    assert "训练" in preview[9]["remaining_scope"]
    entry = preview[9]
    save = lambda request: upsert_workbench_delivery(  # noqa: E731
        db, "p", entry, 0, "source", request_id=request, actor="test"
    )
    first = save("save")
    assert save("save") == first
    with pytest.raises(Conflict):
        save("stale")
    assert list_historical_deliveries(db, "p")[0]["registration_status"] == (
        "historical_pending_task_registration"
    )
    create_task(
        db,
        {"id": "t", "project_id": "p", "title": "T", "goal": "G", "category": "workbench"},
        request_id="t",
        actor="test",
    )
    before = get_task(db, "t")
    linked = upsert_workbench_delivery(
        db, "p", {**entry, "task_id": "t"}, 1, "link", request_id="link", actor="test"
    )
    assert linked["revision"] == 2
    from catalyst_ai.workbench.queries import query

    for scope in ("all", "workbench"):
        history = query(db, "p", scope)["historical_deliveries"]
        assert len(history) == 1
        assert history[0]["task_id"] == "t"
        assert history[0]["registration_status"] == "registered"
    assert query(db, "p", "research")["historical_deliveries"] == []
    after = get_task(db, "t")
    assert {k: v for k, v in after.items() if k != "activity"} == {
        k: v for k, v in before.items() if k != "activity"
    }
    conn = connect(db)
    assert conn.execute("SELECT count(*) FROM workbench_delivery_revision").fetchone()[0] == 2
    conn.close()


def test_missing_source_is_preserved(tmp_path):
    db = tmp_path / "db.sqlite"
    migrate(db)
    create_project(db, "p", "P", request_id="p", actor="test")
    configure_workspace(db, "p", tmp_path, request_id="w", actor="test")
    source = tmp_path / "source.md"
    source.write_text("# Source\nEvidence", encoding="utf-8")
    import hashlib

    entry = {
        "original_wb_id": "WB-02",
        "delivered_scope": "done",
        "remaining_scope": "remaining",
        "source_path": "source.md",
        "source_section": "Source",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }
    upsert_workbench_delivery(db, "p", entry, 0, "evidence", request_id="s", actor="test")
    source.unlink()
    assert list_historical_deliveries(db, "p")[0]["source_status"] == "missing_or_invalid"
