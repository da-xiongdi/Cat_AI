from copy import deepcopy

import pytest
from test_r1_features import payload
from test_split import inputs, rehash_snapshot

pytest.importorskip("sklearn")

from catalyst_ai.datasets.split import build_paper_split  # noqa: E402
from catalyst_ai.modeling.experiments import _score, compare_r1  # noqa: E402


def prepared(sample):
    snapshot, qualification = inputs(sample)
    template = snapshot["content"]["records"][0]
    records = []
    for i in range(12):
        record = deepcopy(template)
        record["record_id"] = str(i).zfill(2)
        record["revision"]["original_fingerprint"] = str(i)
        item = payload(record["payload"], "X" + str(i))
        item["source"].update(source_id="s" + str(i), doi=f"10.1234/paper{i}", title=f"paper {i}")
        target = next(o for o in item["observations"] if o["metric"] == "co2_conversion")
        target["value"].update(
            state="reported", normalized_value=10 + i, normalized_unit="%", definition="test"
        )
        record["payload"] = item
        records.append(record)
    content = snapshot["content"]
    content.update(
        records=records,
        record_ids=[r["record_id"] for r in records],
        target_unit="%",
        target_definition="test",
    )
    qualification["content"]["eligible_record_ids"] = content["record_ids"]
    from catalyst_ai.reporting.evidence import digest

    qualification["content_sha256"] = digest(qualification["content"])
    qualification["qualification_id"] = "qualification-" + qualification["content_sha256"]
    rehash_snapshot(snapshot, qualification)
    return snapshot, qualification, build_paper_split(snapshot, qualification)


def test_grouped_oof_and_validation_isolation(sample):
    snapshot, qualification, split = prepared(sample)
    report, fitted = compare_r1(snapshot, qualification, split)
    assert fitted["features"].feature_set == "F_base"
    rows = report["oof_predictions"]["F_base"]["ridge"]
    assert len(rows) == len(split["content"]["splits"]["train"]["record_ids"])
    assert all(row["status"].startswith("unsupported_species_role") for row in rows)
    for fold in report["fold_details"]:
        assert not set(fold["training_record_ids"]) & set(fold["held_out_record_ids"])
        held_keys = {("compound", "X" + str(int(i))) for i in fold["held_out_record_ids"]}
        assert not held_keys & {tuple(k) for k in fold["features"]["F_base"]["vocabulary"]}
    before = report["oof_scores"]
    val_ids = set(split["content"]["splits"]["validation"]["record_ids"])
    for record in snapshot["content"]["records"]:
        if record["record_id"] in val_ids:
            record["payload"]["observations"][0]["value"]["normalized_value"] += 50
    rehash_snapshot(snapshot, qualification)
    split = build_paper_split(snapshot, qualification)
    after, _ = compare_r1(snapshot, qualification, split)
    assert after["oof_scores"] == before
    assert after["selected"] == report["selected"]
    assert (
        after["validation"]["candidates"]["F_base"]["metrics"]
        != report["validation"]["candidates"]["F_base"]["metrics"]
    )


def test_paper_equal_weight():
    rows = [
        {"doi": "a", "observed": 0, "raw_prediction": 1},
        {"doi": "a", "observed": 0, "raw_prediction": 1},
        {"doi": "b", "observed": 0, "raw_prediction": 7},
    ]
    assert _score(rows)["paper_equal_mae"] == 4
    assert _score(rows)["mae"] == 3


def test_insufficient_training_groups(sample):
    snapshot, qualification, split = prepared(sample)
    for record in snapshot["content"]["records"]:
        if record["record_id"] in split["content"]["splits"]["train"]["record_ids"][2:]:
            record["payload"]["recipe"]["composition_basis"] = "wt_pct"
    rehash_snapshot(snapshot, qualification)
    split = build_paper_split(snapshot, qualification)
    with pytest.raises(ValueError, match="at least 3 DOI"):
        compare_r1(snapshot, qualification, split)


def test_availability_and_common_support():
    from catalyst_ai.modeling.experiments import _availability, _common_support

    def row(identifier, status, prediction):
        return {
            "record_id": identifier,
            "doi": "paper" + identifier,
            "observed": 10,
            "raw_prediction": prediction,
            "status": status,
        }

    base = [
        row("1", "caution", 11),
        row("2", "unsupported_species_role", 20),
        row("3", "caution+output_out_of_range", 101),
    ]
    cond = [row("1", "ok", 12), row("2", "ok", 15), row("3", "ok", 10)]
    summary = _availability(base)
    assert summary["total_records"] == 3 and summary["available_records"] == 1
    assert summary["rejection_reasons"] == {"output_out_of_range": 1, "unsupported_species_role": 1}
    assert summary["available_metrics"]["mae"] == 1
    common = _common_support({"F_base": base, "F_cond": cond})
    assert common["record_ids"] == ["1"]
    assert common["metrics"]["F_cond"]["mae"] == 2
    none = _common_support({"base": base[1:], "cond": cond})
    assert none["records"] == 0 and none["metrics"]["base"] is None
    assert _availability(base[1:])["available_metrics"] is None


def test_research_source_integrity(tmp_path):
    import hashlib

    from catalyst_ai.modeling.experiments import _verify_research_evidence
    from catalyst_ai.reporting.evidence import digest

    raw = tmp_path / "source.csv"
    raw.write_bytes(b"original")
    h = hashlib.sha256(raw.read_bytes()).hexdigest()
    record = {
        "record_id": "1",
        "payload": {"x": 1},
        "input_sha256": h,
        "input_locator": "row 1",
        "payload_sha256": digest({"x": 1}),
    }
    snapshot = {
        "content": {
            "dataset_kind": "research",
            "target": "co2_conversion",
            "target_definition": "conversion",
            "target_unit": "%",
            "records": [record],
        }
    }
    evidence = {
        k: record[k] for k in ("record_id", "input_sha256", "input_locator", "payload_sha256")
    }
    evidence.update(status="included", integrity_errors=[])
    qualification = {
        "content": {
            "dataset_kind": "research",
            "records": [evidence],
            "target": {"metric": "co2_conversion", "definition": "conversion", "unit": "%"},
        }
    }
    _verify_research_evidence(snapshot, qualification, {h: raw})
    with pytest.raises(ValueError, match="missing original"):
        _verify_research_evidence(snapshot, qualification, {})
    raw.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        _verify_research_evidence(snapshot, qualification, {h: raw})
    record["payload"]["x"] = 2
    with pytest.raises(ValueError, match="evidence mismatch"):
        _verify_research_evidence(snapshot, qualification, {h: raw})


def test_test_targets_do_not_change_model_selection(sample):
    snapshot, qualification, split = prepared(sample)
    report, _ = compare_r1(snapshot, qualification, split)
    ids = set(split["content"]["splits"]["test"]["record_ids"])
    for record in snapshot["content"]["records"]:
        if record["record_id"] in ids:
            record["payload"]["observations"][0]["value"]["normalized_value"] += 30
    rehash_snapshot(snapshot, qualification)
    changed, _ = compare_r1(snapshot, qualification, build_paper_split(snapshot, qualification))
    assert changed["selected"] == report["selected"]
    assert changed["oof_scores"] == report["oof_scores"]
    assert changed["validation"] == report["validation"]
    assert changed["test"] != report["test"]


def test_multi_record_groups_scaling_ties_and_repeatability(sample, monkeypatch):
    import numpy as np

    import catalyst_ai.modeling.experiments as experiments
    from catalyst_ai.features.pipeline import R1Features

    snapshot, qualification, _ = prepared(sample)
    records = snapshot["content"]["records"]
    for i, record in enumerate(records):
        # Two records per paper; the holdout must exclude the entire paper.
        record["payload"]["source"].update(doi=f"10.1234/paper{i // 2}", title=f"paper {i // 2}")
        record["payload"]["observations"][0]["value"]["normalized_value"] = 15
    rehash_snapshot(snapshot, qualification)
    split = build_paper_split(snapshot, qualification)
    fitted_models = []
    original = experiments._model

    def tracked(name):
        model = original(name)
        if name == "ridge":
            fitted_models.append(model)
        return model

    monkeypatch.setattr(experiments, "_model", tracked)
    report, _ = compare_r1(snapshot, qualification, split)
    assert report["selected"] == {"feature_set": "F_base", "model": "dummy"}
    by_id = {r["record_id"]: r for r in records}
    for fold_index, fold in enumerate(report["fold_details"]):
        train = [by_id[i]["payload"] for i in fold["training_record_ids"]]
        hold = [by_id[i]["payload"] for i in fold["held_out_record_ids"]]
        assert not {r["source"]["doi"] for r in train} & {r["source"]["doi"] for r in hold}
        for feature_index, feature in enumerate(("F_cond", "F_base")):
            transformer = R1Features.fit(train, feature)
            matrix = np.asarray([transformer.transform_one(p)["values"] for p in train])
            scaler = fitted_models[fold_index * 2 + feature_index].named_steps["standardscaler"]
            np.testing.assert_allclose(scaler.mean_, matrix.mean(axis=0))
            assert scaler.n_samples_seen_ == len(train)
    assert len({r["record_id"] for r in report["fold_assignments"]}) == sum(
        len(f["held_out_record_ids"]) for f in report["fold_details"]
    )
    repeated, _ = compare_r1(snapshot, qualification, split)
    assert repeated == report


def test_nonfinite_prediction_stops_evaluation(sample):
    import numpy as np

    from catalyst_ai.features.pipeline import R1Features
    from catalyst_ai.modeling.experiments import _predict

    snapshot, _, _ = prepared(sample)
    record = snapshot["content"]["records"][0]

    class BrokenModel:
        def predict(self, values):
            return np.full(len(values), np.nan)

    features = R1Features.fit([record["payload"]])
    with pytest.raises(ValueError, match=f"non-finite.*{record['record_id']}"):
        _predict(features, BrokenModel(), [record], [0])


def test_comparison_script_persists_reviewable_evidence(sample, tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    from catalyst_ai.modeling.experiments import write_r1_comparison
    from catalyst_ai.reporting.evidence import digest

    snapshot, qualification, split = prepared(sample)
    output = tmp_path / "run"
    arguments = []
    for name, value in (("snapshot", snapshot), ("qualification", qualification), ("split", split)):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        arguments.extend(["--" + name, str(path)])
    script = Path(__file__).resolve().parents[2] / "scripts" / "compare_r1.py"
    result = subprocess.run(
        [sys.executable, str(script), *arguments, "--output", str(output)],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert json.loads(result.stdout)["content_sha256"] == report["content_sha256"]
    assert (
        digest({k: v for k, v in report.items() if k != "content_sha256"})
        == report["content_sha256"]
    )
    for filename, key in (("selection.json", "selection"), ("configuration.json", "configuration")):
        assert json.loads((output / filename).read_text(encoding="utf-8")) == report[key]
    folds = json.loads((output / "folds.json").read_text(encoding="utf-8"))
    assert folds["assignments"] == report["fold_assignments"]
    assert folds["details"] == report["fold_details"]
    assert (output / "README.md").is_file()
    for part in ("train", "validation", "test"):
        coverage = report["input_coverage"][part]
        assert coverage["parent"] == coverage["retained"]
        assert coverage["retained"]["composition_signatures"] == coverage["retained"]["records"]
    with pytest.raises(FileExistsError):
        write_r1_comparison(output, report)
    report["selected"]["model"] = "tampered"
    with pytest.raises(ValueError, match="hash mismatch"):
        write_r1_comparison(tmp_path / "invalid", report)
    assert not (tmp_path / "invalid").exists()
