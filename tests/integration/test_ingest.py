import copy
import json

from sqlalchemy import func, select

from catalyst_ai.ingest import ingest
from catalyst_ai.storage.db import transaction
from catalyst_ai.storage.models import (
    CuratedRow,
    ObservationRow,
    RecipeRow,
    StagedRow,
    SynthesisRow,
    TestRow,
)


def test_dry_run_no_side_effects(sample, settings, input_file):
    report = ingest(input_file([sample]), settings, dry_run=True)
    assert report["counts"]["curated"] == 1
    assert not settings.database.exists()
    assert not settings.report_dir.exists()
    assert not settings.data_dir.exists()


def test_import_trace_and_duplicates(sample, settings, input_file):
    input_path = input_file([sample])
    report = ingest(input_path, settings)
    assert report["counts"]["curated"] == 1
    assert report["dataset_kinds"] == ["synthetic_demo"]
    assert report["rows"][0]["input_locator"] == "$[0]"
    duplicate = ingest(input_path, settings)
    assert duplicate["counts"]["duplicate"] == 1
    with transaction(settings.database) as session:
        assert session.scalar(select(func.count()).select_from(CuratedRow)) == 1
        assert session.scalar(select(func.count()).select_from(StagedRow)) == 2
        assert session.scalar(select(CuratedRow)).review_status == "pending"
    assert next((settings.data_dir / "raw").glob("*.json")).read_bytes() == input_path.read_bytes()


def test_multiple_batches_conditions_and_observations(sample, settings, input_file):
    other_condition = copy.deepcopy(sample)
    other_condition["test"]["test_id"] = "demo-test-2"
    other_condition["test"]["temperature"]["raw_value"] = "270"
    for i, obs in enumerate(other_condition["observations"]):
        obs.update(observation_id=f"demo-second-{i}", test_id="demo-test-2")
    second_batch = copy.deepcopy(other_condition)
    second_batch["synthesis"]["synthesis_id"] = "demo-syn-2"
    second_batch["test"].update(synthesis_id="demo-syn-2", test_id="demo-test-3")
    for i, obs in enumerate(second_batch["observations"]):
        obs.update(observation_id=f"demo-third-{i}", test_id="demo-test-3")
    report = ingest(input_file([sample, other_condition, second_batch]), settings)
    assert report["counts"]["curated"] == 3
    with transaction(settings.database) as session:
        for cls, expected in [(RecipeRow, 1), (SynthesisRow, 2), (TestRow, 3), (ObservationRow, 6)]:
            assert session.scalar(select(func.count()).select_from(cls)) == expected


def test_conflicting_entity_does_not_overwrite(sample, settings, input_file):
    ingest(input_file([sample]), settings)
    sample["observations"][0]["value"]["raw_value"] = "21"
    report = ingest(input_file([sample]), settings)
    assert report["counts"]["staged"] == 1
    assert "entity_conflict" in [i["code"] for i in report["rows"][0]["issues"]]
    with transaction(settings.database) as session:
        assert session.scalar(select(ObservationRow)).payload["value"]["raw_value"] == "20.0"


def test_invalid_row_retained(sample, settings, input_file):
    report = ingest(input_file([sample, {"dataset_kind": "synthetic_demo"}]), settings)
    assert report["counts"]["staged"] == 1
    assert report["counts"]["curated"] == 1
    with transaction(settings.database) as session:
        row = session.get(StagedRow, report["rows"][1]["record_id"])
        assert row.raw_payload == {"dataset_kind": "synthetic_demo"}


def test_csv_json_equivalence(settings):
    from pathlib import Path

    example_dir = Path(__file__).parents[2] / "data/examples"
    csv_report = ingest(example_dir / "synthetic_demo.csv", settings)
    json_report = ingest(example_dir / "synthetic_demo.json", settings, dry_run=True)
    assert csv_report["rows"][0]["fingerprint"] == json_report["rows"][0]["fingerprint"]
    assert csv_report["rows"][0]["input_locator"] == "lines:2-2"
    assert json_report["counts"]["duplicate"] == 1


def test_missing_source_and_units_stay_staged(sample, settings, input_file):
    sample["source"] = None
    sample["test"]["pressure"]["raw_unit"] = "?"
    report = ingest(input_file([sample]), settings)
    assert report["counts"]["curated"] == 0
    assert {"source_missing", "unit_unknown"} <= {i["code"] for i in report["rows"][0]["issues"]}
    stored = json.loads(
        (settings.data_dir / "staged" / f"{report['run_id']}.json").read_text(encoding="utf-8")
    )
    assert stored["records"][0]["raw_payload"]["test"]["pressure"]["raw_unit"] == "?"


def test_duplicate_with_changed_wrapper_is_still_blocked(sample, settings, input_file):
    ingest(input_file([sample]), settings)
    sample["source"]["access"] = "synthetic_demo modified wrapper"
    report = ingest(input_file([sample]), settings)
    assert report["counts"]["curated"] == 0
    assert "duplicate_observation" in [i["code"] for i in report["rows"][0]["issues"]]


def test_dry_run_existing_database_changes_no_files(sample, settings, input_file):
    import hashlib

    path = input_file([sample])
    ingest(path, settings)
    root = settings.data_dir.parent
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    ingest(path, settings, dry_run=True)
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    assert before == after
