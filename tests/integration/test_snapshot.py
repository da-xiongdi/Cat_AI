import json
from pathlib import Path

import pytest
from sqlalchemy import select

from catalyst_ai.ingest import ingest
from catalyst_ai.review import review_record
from catalyst_ai.storage.db import transaction
from catalyst_ai.storage.models import ReviewRow, StagedRow
from catalyst_ai.storage.snapshots import build_verified_snapshot


def approve_demo(settings, record_id):
    return review_record(
        settings,
        record_id,
        reviewer="pytest_mock_reviewer",
        decision="verified",
        evidence="synthetic_demo fixture policy test only",
        acknowledge_warnings=True,
    )


def test_unreviewed_and_demo_cannot_enter_research_snapshot(sample, settings, input_file):
    report = ingest(input_file([sample]), settings)
    identifier = report["rows"][0]["record_id"]
    with pytest.raises(ValueError, match="synthetic_demo"):
        build_verified_snapshot(settings, target="co2_conversion", record_ids=[identifier])
    with pytest.raises(ValueError, match="人工核验"):
        build_verified_snapshot(settings, target="co2_conversion", demo=True)
    approve_demo(settings, identifier)
    with pytest.raises(ValueError, match="synthetic_demo"):
        build_verified_snapshot(settings, target="co2_conversion", record_ids=[identifier])
    assert not (settings.data_dir / "snapshots").exists()


def test_review_requires_evidence_and_warning_acknowledgement(sample, settings, input_file):
    identifier = ingest(input_file([sample]), settings)["rows"][0]["record_id"]
    with pytest.raises(ValueError, match="warning"):
        review_record(settings, identifier, reviewer="test", decision="verified", evidence="test")
    with pytest.raises(ValueError, match="非空"):
        review_record(settings, identifier, reviewer=" ", decision="verified", evidence=" ")
    review = approve_demo(settings, identifier)
    with transaction(settings.database) as session:
        event = session.get(ReviewRow, review["review_id"])
        assert event.payload_sha256
        assert event.metadata_json["scope"] == "whole_record"


def test_reviewed_demo_snapshot_is_explicit_immutable_and_idempotent(sample, settings, input_file):
    identifier = ingest(input_file([sample]), settings)["rows"][0]["record_id"]
    approve_demo(settings, identifier)
    first = build_verified_snapshot(settings, target="co2_conversion", demo=True)
    path = Path(first["path"])
    original = path.read_bytes()
    manifest = json.loads(original)
    assert manifest["content"]["dataset_kind"] == "synthetic_demo"
    assert manifest["content"]["scientific_use"] is False
    assert manifest["content"]["split_status"] == "not_performed"
    assert build_verified_snapshot(settings, target="co2_conversion", demo=True) == first
    assert path.read_bytes() == original
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="拒绝覆盖"):
        build_verified_snapshot(settings, target="co2_conversion", demo=True)


def test_reject_and_payload_change_invalidate_future_snapshots(sample, settings, input_file):
    identifier = ingest(input_file([sample]), settings)["rows"][0]["record_id"]
    approve_demo(settings, identifier)
    first = build_verified_snapshot(settings, target="co2_conversion", demo=True)
    with transaction(settings.database) as session:
        row = session.get(StagedRow, identifier)
        payload = dict(row.payload)
        payload["test"] = {**payload["test"], "reactor": "tampered"}
        row.payload = payload
    with pytest.raises(ValueError, match="核验时内容不符"):
        build_verified_snapshot(settings, target="co2_conversion", demo=True)
    review_record(settings, identifier, reviewer="test", decision="rejected", evidence="test")
    with pytest.raises(ValueError, match="人工核验"):
        build_verified_snapshot(settings, target="co2_conversion", demo=True)
    assert Path(first["path"]).exists()


def test_missing_raw_and_missing_target_refused(sample, settings, input_file):
    report = ingest(input_file([sample]), settings)
    approve_demo(settings, report["rows"][0]["record_id"])
    with pytest.raises(ValueError, match="缺少目标"):
        build_verified_snapshot(settings, target="methanol_sty", demo=True)
    Path(report["raw_path"]).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="原始证据"):
        build_verified_snapshot(settings, target="co2_conversion", demo=True)


def test_staged_cannot_be_approved(sample, settings, input_file):
    sample["source"] = None
    identifier = ingest(input_file([sample]), settings)["rows"][0]["record_id"]
    with pytest.raises(ValueError, match="curated"):
        approve_demo(settings, identifier)
    with transaction(settings.database) as session:
        assert session.scalar(select(ReviewRow)) is None
