"""All records and reviewer actions in this module are isolated synthetic fixtures."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from catalyst_ai.cli import main
from catalyst_ai.datasets.eligibility import (
    build_target_eligibility,
    freeze_qualified_snapshot,
)
from catalyst_ai.ingest import ingest
from catalyst_ai.reporting.evidence import digest
from catalyst_ai.review import review_record
from catalyst_ai.storage.db import transaction
from catalyst_ai.storage.models import StagedRow
from catalyst_ai.storage.snapshots import build_verified_snapshot


@pytest.fixture
def load_records(sample, settings, input_file):
    def load(variants, approve=True):
        records = [
            json.loads(json.dumps(record).replace("demo-", f"case-{index}-"))
            for index, record in enumerate(variants)
        ]
        report = ingest(input_file(records), settings)
        identifiers = [row["record_id"] for row in report["rows"]]
        if approve:
            for row in report["rows"]:
                if row["status"] == "curated":
                    review_record(
                        settings,
                        row["record_id"],
                        reviewer="pytest_mock_reviewer",
                        decision="verified",
                        evidence="synthetic_demo fixture only",
                        acknowledge_warnings=True,
                    )
        return identifiers, report

    return load


def qualify(settings, sample, identifiers, **overrides):
    arguments = {
        "record_ids": identifiers,
        "target": "co2_conversion",
        "target_definition": sample["observations"][0]["value"]["definition"],
        "target_unit": "%",
        "demo": True,
    }
    return build_target_eligibility(settings, **(arguments | overrides))


def test_mixed_target_views_preserve_evidence_and_freeze_only_eligible(
    sample,
    settings,
    load_records,
):
    missing = deepcopy(sample)
    missing["observations"] = missing["observations"][1:]
    unlabeled = deepcopy(sample)
    unlabeled["observations"][0]["value"].update(raw_value=None, state="not_measured")
    other_definition = deepcopy(sample)
    other_definition["observations"][0]["value"]["definition"] = "different denominator"
    ids, _ = load_records([sample, missing, unlabeled, other_definition])
    with transaction(settings.database) as session:
        before = {i: session.get(StagedRow, i).payload for i in ids}
    result = qualify(settings, sample, ids)
    content = result["content"]
    assert content["eligible_record_ids"] == ids[:1]
    assert content["counts"] == {
        "input_records": 4,
        "included_records": 1,
        "excluded_records": 3,
        "target_observations": 3,
        "included_observations": 1,
    }
    reasons = {r["record_id"]: r["reason_codes"] for r in content["records"]}
    assert "missing_target" in reasons[ids[1]]
    assert "missing_target_value" in reasons[ids[2]]
    assert "target_definition_mismatch" in reasons[ids[3]]
    assert content["coverage"]["input"]["source_id"] == 4
    assert content["coverage"]["included"]["synthesis_id"] == 1
    assert all(row["payload_sha256"] and row["input_sha256"] for row in content["records"])
    result = freeze_qualified_snapshot(settings, result)
    snapshot = json.loads(Path(result["snapshot"]["path"]).read_text(encoding="utf-8"))
    assert snapshot["content"]["record_ids"] == ids[:1]
    assert snapshot["content"]["scientific_use"] is False
    assert snapshot["content"]["split_status"] == "not_performed"
    assert result["qualification_id"] == "qualification-" + digest(result["content"])
    receipt = Path(result["qualification_path"])
    assert json.loads(receipt.read_text(encoding="utf-8")) == result
    assert freeze_qualified_snapshot(settings, result) == result
    with transaction(settings.database) as session:
        assert {i: session.get(StagedRow, i).payload for i in ids} == before
    with pytest.raises(ValueError):
        build_verified_snapshot(settings, target="co2_conversion", demo=True)
    # A record excluded for one target remains usable for a different target.
    other = qualify(
        settings,
        sample,
        [ids[1]],
        target="methanol_selectivity",
        target_definition=sample["observations"][1]["value"]["definition"],
    )
    assert other["content"]["eligible_record_ids"] == [ids[1]]


def test_pending_empty_view_is_read_only_and_never_falls_back_to_all_records(
    sample,
    settings,
    load_records,
):
    ids, _ = load_records([sample], approve=False)
    before = settings.database.read_bytes()
    result = qualify(settings, sample, ids)
    assert result["content"]["status"] == "empty"
    assert result["content"]["records"][0]["reason_codes"] == ["not_reviewed"]
    assert settings.database.read_bytes() == before
    with pytest.raises(ValueError, match="没有合格"):
        freeze_qualified_snapshot(settings, result)
    assert not (settings.data_dir / "snapshots").exists()


@pytest.mark.parametrize(
    "times, included",
    [
        ([None, None], False),
        ([("1", "h"), ("60", "min")], False),
        ([("1", "h"), ("120", "min")], True),
    ],
)
def test_multiple_observations_require_distinguishable_context(
    sample,
    settings,
    load_records,
    times,
    included,
):
    repeated = deepcopy(sample["observations"][0])
    repeated["observation_id"] = "demo-obs-3"
    sample["observations"].append(repeated)
    for obs, time in zip([sample["observations"][0], repeated], times, strict=True):
        if time:
            obs["time_on_stream"] = {
                "raw_value": time[0],
                "raw_unit": time[1],
                "state": "reported",
                "source_locator": "demo-extraction-1",
            }
    ids, _ = load_records([sample])
    result = qualify(settings, sample, ids)
    row = result["content"]["records"][0]
    assert len(row["observations"]) == 2
    assert len({o["observation_id"] for o in row["observations"]}) == 2
    assert (row["status"] == "included") is included
    if included:
        assert sorted(o["effective_time_seconds"] for o in row["observations"]) == [3600, 7200]
        assert result["content"]["counts"]["included_observations"] == 2
        assert freeze_qualified_snapshot(settings, result)["snapshot"]["record_count"] == 1
    else:
        assert "ambiguous_observation_context" in row["reason_codes"]


def test_invalid_target_sibling_excludes_entire_record(sample, settings, load_records):
    invalid = deepcopy(sample["observations"][0])
    invalid["observation_id"] = "demo-obs-3"
    invalid["value"].update(raw_value=None, state="not_measured")
    sample["observations"].append(invalid)
    ids, _ = load_records([sample])
    row = qualify(settings, sample, ids)["content"]["records"][0]
    assert row["status"] == "excluded"
    assert len(row["observations"]) == 2
    assert all(o["status"] == "excluded" for o in row["observations"])
    with pytest.raises(ValueError, match="有效标准值"):
        build_verified_snapshot(settings, target="co2_conversion", record_ids=ids, demo=True)


def test_unit_mismatch_and_zero_are_explicit(sample, settings, load_records):
    sample["observations"][0]["value"].update(raw_value="0", state="zero")
    ids, _ = load_records([sample])
    result = qualify(settings, sample, ids)
    assert result["content"]["records"][0]["observations"][0]["value"]["normalized_value"] == 0
    assert result["content"]["status"] == "ready"
    mismatch = qualify(settings, sample, ids, target_unit="1")
    assert mismatch["content"]["records"][0]["reason_codes"] == ["target_unit_mismatch"]


@pytest.mark.parametrize("change", ["raw_missing", "raw_changed", "payload", "rejected"])
def test_integrity_failures_block_even_when_target_is_absent(
    sample,
    settings,
    load_records,
    change,
):
    other = deepcopy(sample)
    other["observations"] = other["observations"][1:]
    ids, report = load_records([sample, other])
    original = qualify(settings, sample, ids)
    if change == "raw_missing":
        Path(report["raw_path"]).unlink()
    elif change == "raw_changed":
        Path(report["raw_path"]).write_bytes(b"tampered")
    elif change == "payload":
        with transaction(settings.database) as session:
            row = session.get(StagedRow, ids[1])
            payload = deepcopy(row.payload)
            payload["test"]["reactor"] = "tampered"
            row.payload = payload
    else:
        review_record(
            settings,
            ids[1],
            reviewer="pytest_mock_reviewer",
            decision="rejected",
            evidence="synthetic_demo revocation",
        )
    with pytest.raises(ValueError, match="已过期"):
        freeze_qualified_snapshot(settings, original)
    current = qualify(settings, sample, ids)
    assert current["content"]["status"] == "blocked"
    assert current["content"]["records"][1]["integrity_errors"]
    with pytest.raises(ValueError, match="完整性阻断"):
        freeze_qualified_snapshot(settings, current)
    assert not (settings.data_dir / "snapshots").exists()


def test_manifest_hash_idempotence_and_dataset_isolation(sample, settings, load_records):
    ids, _ = load_records([sample])
    first = qualify(settings, sample, ids)
    assert first == qualify(settings, sample, [*ids, *ids])
    tampered = deepcopy(first)
    tampered["content"]["target"]["unit"] = "forged"
    with pytest.raises(ValueError, match="哈希"):
        freeze_qualified_snapshot(settings, tampered)
    research = qualify(settings, sample, ids, demo=False)
    assert research["content"]["status"] == "blocked"
    assert "dataset_kind_mismatch" in research["content"]["records"][0]["integrity_errors"]


@pytest.mark.parametrize("identifiers", [[], "whole_database", [" "], [None]])
def test_explicit_selection_required(sample, settings, identifiers):
    with pytest.raises(ValueError, match="record_ids"):
        qualify(settings, sample, identifiers)
    assert not settings.database.exists()


def test_unknown_record_and_staged_input_are_reported(sample, settings, load_records):
    sample["source"] = None
    ids, _ = load_records([sample], approve=False)
    content = qualify(settings, sample, [*ids, "unknown"])["content"]
    assert content["status"] == "blocked"
    assert content["counts"]["input_records"] == 2
    assert "not_curated" in content["records"][0]["reason_codes"]
    assert content["records"][1]["reason_codes"] == ["record_not_found"]


def test_rules_and_target_specification_are_explicit(sample, settings, load_records):
    ids, _ = load_records([sample])
    for overrides in ({"target_definition": " "}, {"target_unit": ""}, {"rule_version": "2"}):
        with pytest.raises(ValueError):
            qualify(settings, sample, ids, **overrides)


def test_qualification_receipt_rejects_overwrite(sample, settings, load_records):
    ids, _ = load_records([sample])
    result = freeze_qualified_snapshot(settings, qualify(settings, sample, ids))
    receipt = Path(result["qualification_path"])
    receipt.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="拒绝覆盖"):
        freeze_qualified_snapshot(settings, result)
    assert receipt.read_text(encoding="utf-8") == "{}"


def test_cli_qualification_reports_then_freezes_with_separate_demo_marker(
    sample,
    settings,
    load_records,
    tmp_path,
    capsys,
):
    ids, _ = load_records([sample], approve=False)
    config = tmp_path / "project.yaml"
    config.write_text(yaml.safe_dump(settings.model_dump(mode="json")), encoding="utf-8")
    arguments = [
        "--config",
        str(config),
        "dataset",
        "qualify",
        "--demo",
        "--record-id",
        ids[0],
        "--target",
        "co2_conversion",
        "--target-definition",
        sample["observations"][0]["value"]["definition"],
        "--target-unit",
        "%",
    ]
    assert main(arguments) == 2
    assert json.loads(capsys.readouterr().out)["content"]["status"] == "empty"
    assert main([*arguments, "--freeze"]) == 1
    assert json.loads(capsys.readouterr().out)["snapshot"] is None
    review_record(
        settings,
        ids[0],
        reviewer="pytest_mock_reviewer",
        decision="verified",
        evidence="synthetic_demo CLI test",
        acknowledge_warnings=True,
    )
    report = tmp_path / "eligibility.json"
    assert main([*arguments, "--freeze", "--report", str(report)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == json.loads(report.read_text(encoding="utf-8"))
    assert result["content"]["scientific_use"] is False
    assert Path(result["snapshot"]["path"]).parent.name == "demo"
    original = report.read_bytes()
    assert main([*arguments, "--report", str(report)]) == 1
    assert "拒绝覆盖" in capsys.readouterr().err
    assert report.read_bytes() == original


def test_source_acceptance_is_distinct_and_requires_exact_dataset(
    sample, settings, input_file, monkeypatch
):
    import catalyst_ai.datasets.eligibility as eligibility

    sample["dataset_kind"] = "research"
    report = ingest(input_file([sample]), settings)
    identifier = report["rows"][0]["record_id"]
    args = dict(
        record_ids=[identifier],
        target="co2_conversion",
        target_definition=sample["observations"][0]["value"]["definition"],
        target_unit="%",
        source_acceptance=eligibility.THEMECAT_ACCEPTED,
    )
    assert build_target_eligibility(settings, **args)["content"]["status"] == "empty"
    monkeypatch.setattr(eligibility, "THEMECAT_SHA256", report["input_sha256"])
    result = build_target_eligibility(settings, **args)
    assert result["content"]["status"] == "ready"
    assert result["content"]["records"][0]["review"] is None
    frozen = freeze_qualified_snapshot(settings, result)
    snapshot = json.loads(Path(frozen["snapshot"]["path"]).read_text(encoding="utf-8"))
    assert snapshot["content"]["status"] == "published_dataset_accepted_not_row_verified"
    assert snapshot["content"]["records"][0]["review"] is None
    review_record(settings, identifier, reviewer="test", decision="rejected", evidence="test")
    rejected = build_target_eligibility(settings, **args)
    assert rejected["content"]["status"] == "blocked"
    with pytest.raises(ValueError):
        freeze_qualified_snapshot(settings, result)
