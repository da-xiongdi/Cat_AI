import copy

import pytest

from catalyst_ai.ingest import ingest
from catalyst_ai.reporting.evidence import digest
from catalyst_ai.review import review_record
from catalyst_ai.revision import revise
from catalyst_ai.storage.db import transaction
from catalyst_ai.storage.models import CuratedRow, RevisionRow, StagedRow
from catalyst_ai.storage.snapshots import build_verified_snapshot


def test_revision_lineage_idempotency_and_review(sample, settings, input_file):
    original = ingest(input_file([sample]), settings)
    parent_id = original["rows"][0]["record_id"]
    review_record(
        settings,
        parent_id,
        reviewer="reviewer",
        decision="verified",
        evidence="page 1",
        acknowledge_warnings=True,
    )
    with transaction(settings.database) as session:
        parent = session.get(StagedRow, parent_id)
        before = copy.deepcopy(parent.payload)
        raw = copy.deepcopy(parent.raw_payload)
    observations = copy.deepcopy(before["observations"])
    for obs in observations:
        obs["observation_id"] += "-rev1"
    args = dict(
        patch={"observations": observations},
        expected_parent_sha256=digest(before),
        reason="correct identity",
        operator="editor",
        evidence="paper p.1",
    )
    report = revise(settings, parent_id, **args)
    assert report["counts"]["curated"] == 1
    assert revise(settings, parent_id, **args) == report
    new_id = report["rows"][0]["record_id"]
    with transaction(settings.database) as session:
        assert session.get(StagedRow, parent_id).payload == before
        new = session.get(StagedRow, new_id)
        assert new.raw_payload == raw
        assert new.fingerprint == digest(raw)
        assert session.get(CuratedRow, new_id).review_status == "pending"
        assert session.get(RevisionRow, new_id).parent_record_id == parent_id
    with pytest.raises(ValueError, match="尚未人工核验"):
        build_verified_snapshot(
            settings, target=observations[0]["metric"], record_ids=[new_id], demo=True
        )
    review_record(
        settings,
        new_id,
        reviewer="reviewer",
        decision="verified",
        evidence="page 1",
        acknowledge_warnings=True,
    )
    with pytest.raises(ValueError, match="多个版本"):
        build_verified_snapshot(
            settings, target=observations[0]["metric"], record_ids=[parent_id, new_id], demo=True
        )
    with pytest.raises(ValueError, match="已有不同"):
        revise(settings, parent_id, **{**args, "reason": "different"})
    with pytest.raises(ValueError, match="哈希不匹配"):
        revise(settings, parent_id, **{**args, "expected_parent_sha256": "wrong"})
    assert ingest(input_file([sample]), settings)["counts"]["duplicate"] == 1


def test_conflicting_entities_block_and_original_evidence_required(sample, settings, input_file):
    report = ingest(input_file([sample]), settings)
    parent_id = report["rows"][0]["record_id"]
    with transaction(settings.database) as session:
        parent = session.get(StagedRow, parent_id)
        payload = copy.deepcopy(parent.payload)
    test = copy.deepcopy(payload["test"])
    test["temperature"]["raw_value"] = "999"
    args = dict(
        patch={"test": test},
        expected_parent_sha256=digest(payload),
        reason="correction",
        operator="editor",
        evidence="p.2",
    )
    result = revise(settings, parent_id, **args)
    assert result["counts"]["staged"] == 1
    assert "entity_conflict" in [i["code"] for i in result["rows"][0]["issues"]]
    new_id = result["rows"][0]["record_id"]
    with transaction(settings.database) as session:
        assert session.get(CuratedRow, new_id) is None
        new = session.get(StagedRow, new_id)
        new_hash = digest(new.payload)
    from pathlib import Path

    Path(report["raw_path"]).write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="原始证据"):
        revise(
            settings,
            new_id,
            patch={"test": payload["test"]},
            expected_parent_sha256=new_hash,
            reason="retry",
            operator="editor",
            evidence="p.2",
        )


def test_themecat_v1_replayed_as_v2(settings, tmp_path):
    import csv
    from pathlib import Path

    from catalyst_ai.sources.themecat import COLUMNS

    source = (
        Path(__file__).parents[2]
        / "data/raw/46000f00323ac64a79f63777e54c05634e83d1a6476176c8b6569122bd03dfbd.csv"
    )
    with source.open(encoding="utf-8-sig", newline="") as f:
        first = next(csv.DictReader(f))
    path = tmp_path / "one.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerow(first)
    original = ingest(path, settings, adapter="themecat-v1")
    parent_id = original["rows"][0]["record_id"]
    with transaction(settings.database) as session:
        parent = session.get(StagedRow, parent_id)
        parent_hash = digest(parent.payload)
        fingerprint = parent.fingerprint
    result = revise(
        settings,
        parent_id,
        patch={},
        expected_parent_sha256=parent_hash,
        reason="dataset semantics v2",
        operator="editor",
        evidence="dataset paper",
        base_adapter="themecat-v2",
    )
    assert result["rows"][0]["fingerprint"] == fingerprint
    assert result["rows"][0]["semantic_rule_version"] == "2"
    assert result["counts"]["staged"] == 1
    with transaction(settings.database) as session:
        revised = session.get(StagedRow, result["rows"][0]["record_id"])
        assert revised.payload["test"]["flow_mode"] == "mass_normalized_reactants"
        assert revised.payload["test"]["pressure_type"] == "unknown"
