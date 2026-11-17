from pathlib import Path

import pytest

from catalyst_ai.storage.workbench import migrate
from catalyst_ai.workbench import backup, import_draft, service


def test_import_and_backup_in_isolated_database(tmp_path):
    root = Path(__file__).resolve().parents[2]
    manifest = root / "docs/workbench/first_import.json"
    db = tmp_path / "workbench.sqlite"
    migrate(db)
    service.create_project(db, "cat-ai", "Cat AI", request_id="project", actor="test")
    details = import_draft.preview(root, manifest)
    if any(s["status"] != "available" for s in details["sources"]):
        pytest.skip("local source artifacts not available")
    result = import_draft.apply(
        db, root, manifest, details["manifest_sha256"], request_id="import", actor="test"
    )
    assert result["tasks"] == 7
    assert (
        import_draft.apply(
            db, root, manifest, details["manifest_sha256"], request_id="import-again", actor="test"
        )
        == result
    )
    assert service.get_task(db, "S1B-01")["status"] == "planned"
    assert service.get_task(db, "S2-01")["dependencies"] == ["S1B-01"]
    assert "?" not in service.get_task(db, "S1B-01")["title"]
    saved = tmp_path / "saved.sqlite"
    backup.backup_database(db, saved)
    assert service.get_task(saved, "S1B-01")["title"] == "物化特征构建验收"
    with pytest.raises(FileExistsError):
        backup.backup_database(db, saved)
