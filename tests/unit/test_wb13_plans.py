import pytest

from catalyst_ai.storage.workbench import migrate
from catalyst_ai.workbench.index import configure_workspace, register
from catalyst_ai.workbench.plans import (
    _inspect,
    inspect_task_plan_reference,
    list_plan_verifications,
    save_document_purpose,
    save_task_plan_reference,
    verify_task_plan_reference,
)
from catalyst_ai.workbench.service import Conflict, create_project, create_task


@pytest.mark.parametrize("fence", ["```", "~~~~"])
def test_fenced_headings_do_not_count(tmp_path, fence):
    plan = tmp_path / "plan.md"
    plan.write_text(f"# Renamed\n{fence}markdown\n# Plan\n{fence}\n", encoding="utf-8")
    assert _inspect(tmp_path, "plan.md", "Plan")[0] == "section_missing"
    plan.write_text(f"# Plan\n{fence}\n# Plan\n{fence}\n# Plan\n", encoding="utf-8")
    assert _inspect(tmp_path, "plan.md", "Plan")[0] == "section_ambiguous"


def test_plan_verification_and_conflicts(tmp_path):
    db = tmp_path / "db.sqlite"
    migrate(db)
    create_project(db, "p", "P", request_id="p", actor="a")
    configure_workspace(db, "p", tmp_path, request_id="w", actor="a")
    f = tmp_path / "plan.md"
    f.write_text("# Plan\ntext", encoding="utf-8")
    register(db, "p", "d", "document", "plan.md", request_id="d", actor="a")
    create_task(
        db, {"id": "t", "project_id": "p", "title": "T", "goal": "G"}, request_id="t", actor="a"
    )
    save_document_purpose(
        db,
        "p",
        "purpose",
        {"document_id": "d", "purpose": "execution_plan"},
        0,
        "initial",
        request_id="purpose",
        actor="a",
    )
    data = {
        "task_id": "t",
        "document_id": "d",
        "path": "plan.md",
        "section_locator": "Plan",
        "purpose": "execution_plan",
        "is_primary": 1,
    }
    save_task_plan_reference(db, "p", "r", data, 0, "initial", request_id="r", actor="a")
    with pytest.raises(Conflict):
        save_task_plan_reference(db, "p", "r2", data, 0, "initial", request_id="r2", actor="a")
    inspection = inspect_task_plan_reference(db, "p", "r")
    assert inspection["status"] == "unverified"
    verify_task_plan_reference(
        db, "p", "r", 1, inspection["current_sha256"], request_id="v", actor="a"
    )
    f.write_text("# Plan\nchanged", encoding="utf-8")
    assert inspect_task_plan_reference(db, "p", "r")["status"] == "changed"
    with pytest.raises(Conflict):
        verify_task_plan_reference(
            db, "p", "r", 1, inspection["current_sha256"], request_id="stale", actor="a"
        )
    f.write_text("# Plan\n# Plan\n", encoding="utf-8")
    assert inspect_task_plan_reference(db, "p", "r")["status"] == "section_ambiguous"
    f.unlink()
    assert inspect_task_plan_reference(db, "p", "r")["status"] == "missing_or_invalid"
    assert len(list_plan_verifications(db, "p", "r")) == 1
