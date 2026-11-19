import json
from types import SimpleNamespace

import pytest

from catalyst_ai.features.pipeline import R1Features
from catalyst_ai.modeling.predictor import _payload
from scripts import d06_evaluate as d06


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    item = {
        "components": [{"role": "element", "species": "Ni", "mol_pct": 100}],
        "temperature_k": 500,
        "pressure_bar_abs": 20,
        "h2_co2_ratio": 3,
        "reactants_flow_nl_g_h": 12,
    }
    candidates = [
        dict(
            record_id=str(i),
            source_group=f"g{i % 10}",
            source=f"source {i % 10}",
            locator=f"table row {i}",
            decision="eligible",
            reason="synthetic",
            input=item,
        )
        for i in range(30)
    ]
    candidates[0]["input"] = {**item, "temperature_k": 501.5}
    candidates[1]["input"] = {**item, "temperature_k": 504}
    candidates[2]["input"] = {
        **item,
        "components": [{"role": "element", "species": "Pt", "mol_pct": 100}],
    }
    candidates.append(
        dict(
            record_id="excluded",
            source_group="excluded",
            source="other",
            locator="page 2",
            decision="excluded",
            reason="missing composition",
        )
    )
    labels = [dict(record_id=str(i), co2_conversion_pct=11 if i == 0 else 12) for i in range(30)]
    conditions = {k: item[k] for k in d06.CONDITIONS}
    files = {
        "protocol.md": "test protocol",
        "source-ledger.md": "synthetic sources",
        "features.json": json.dumps(
            {
                "content": {
                    "rows": [
                        {
                            "record_id": "train",
                            "partition": "train",
                            "conditions": conditions,
                            "composition": [
                                {"role": "element", "species": "Ni", "material_mol_pct": 100}
                            ],
                        },
                    ]
                }
            }
        ),
        "model.pkl": "test model",
        "label-access.json": json.dumps(
            {
                "custodian": "test",
                "eligible_labels_unseen_by_evaluators": True,
                "history": ["prepared synthetic labels"],
            }
        ),
        "labels.json": json.dumps(labels),
        "candidates.json": json.dumps(candidates),
    }
    hashes = {name: d06.sha256(value.encode()) for name, value in files.items()}
    manifest = {
        "model_id": d06.MODEL_ID,
        "target_definition": "CO2 conversion",
        "feature_set_id": "F_base",
        "training_record_ids": ["train"],
        "dependencies": {},
        "artifact_sha256": hashes["model.pkl"],
    }
    files["model-manifest.json"] = json.dumps(manifest)
    hashes["model-manifest.json"] = d06.sha256(files["model-manifest.json"].encode())
    files["rule.json"] = json.dumps(
        {
            "model_id": d06.MODEL_ID,
            "version": "d03-candidate-v1",
            "input_sha256": {
                f"{d06.MODEL_DIR}/manifest.json": hashes["model-manifest.json"],
                d06.FEATURE_FILE: hashes["features.json"],
            },
            "reference": {
                "final": {
                    "records": 1,
                    "condition_iqr": dict.fromkeys(conditions, 1),
                    "thresholds": {"composition": [1, 2], "conditions": [1, 2]},
                }
            },
        }
    )
    hashes["rule.json"] = d06.sha256(files["rule.json"].encode())
    for name, value in files.items():
        path = tmp_path / ("manifest.json" if name == "model-manifest.json" else name)
        path.write_bytes(value.encode())
    d06.write_json(
        tmp_path / "freeze.json",
        {
            "version": "d04-evaluation-freeze-v1",
            "candidate_scope": "synthetic registration",
            "coverage_scope": "synthetic conditions",
            "sha256": hashes,
        },
    )
    monkeypatch.setattr(d06, "PROTOCOL_SHA", hashes["protocol.md"])
    monkeypatch.setattr(d06, "RULE_SHA", hashes["rule.json"])
    fitted = {
        "features": R1Features.fit([_payload(item)]),
        "model": SimpleNamespace(predict=lambda _: [10]),
    }
    return tmp_path, (manifest, fitted)


def preflight(path):
    return d06.preflight(path, path, path / "rule.json", path / "features.json")


def test_preflight_has_no_label_or_model_execution_dependency(bundle, monkeypatch):
    path, _ = bundle
    (path / "labels.json").rename(path / "sealed.json")
    monkeypatch.setattr(d06, "load_package", lambda _: pytest.fail("loaded a model"))
    checked = preflight(path)[0]
    assert checked["status"] == "ready"
    assert checked["eligible"] == {"records": 30, "groups": 10}
    assert checked["candidate"] == {"records": 31, "groups": 11}
    assert not (path / "d06-run").exists()

    (path / "candidates.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        preflight(path)


def test_evaluation_preserves_entry_status_and_reports_distinct_denominators(bundle, monkeypatch):
    path, package = bundle
    monkeypatch.setattr(d06, "load_package", lambda _: package)
    labels = path / "labels.json"
    out = d06.evaluate(path, path, labels, preflight(path))
    summary = json.loads((out / "inputs.json").read_bytes())
    metrics = json.loads((out / "group-metrics.json").read_bytes())
    rows = json.loads((out / "row-results.json").read_bytes())
    assert summary["evaluation_performed"] and summary["evaluation_label_access_started_at_utc"]
    assert [r["domain"] for r in rows[:4]] == ["warning", "outside", "outside", "inside"]
    assert [r["prediction"]["status"] for r in rows[:4]] == [
        "caution",
        "caution",
        "unsupported_species_role",
        "ok",
    ]
    assert metrics["input_eligibility_rate"] == pytest.approx(30 / 31)
    assert metrics["overall"]["availability"] == pytest.approx(29 / 30)
    assert metrics["overall"]["mae_pct_points"] == pytest.approx(57 / 29)
    assert metrics["overall"]["rmse_pct_points"] == pytest.approx((113 / 29) ** 0.5)
    assert metrics["overall"]["group_equal_mae_pct_points"] == pytest.approx((9 * 2 + 5 / 3) / 10)
    assert metrics["domain"]["outside"]["coverage"] == pytest.approx(2 / 30)
    assert metrics["domain"]["outside"]["available"] == {"records": 1, "groups": 1}
    assert not metrics["domain"]["outside"]["error_evidence"]
    assert metrics["entry_rejection_reasons"] == {"unsupported_species_role": 1}
    assert rows[2]["absolute_error_pct_points"] is None
    with pytest.raises(FileExistsError):
        d06.evaluate(path, path, labels, preflight(path))


def test_too_few_groups_stops_before_model_and_labels(bundle, monkeypatch):
    path, _ = bundle
    candidates = json.loads((path / "candidates.json").read_bytes())
    for row in candidates:
        row["source_group"] = "same group"
    d06.write_json(path / "candidates.json", candidates)
    freeze = json.loads((path / "freeze.json").read_bytes())
    freeze["sha256"]["candidates.json"] = d06.sha256((path / "candidates.json").read_bytes())
    d06.write_json(path / "freeze.json", freeze)
    monkeypatch.setattr(d06, "load_package", lambda _: pytest.fail("loaded a model"))
    with pytest.raises(ValueError, match="insufficient eligible records or groups"):
        d06.evaluate(path, path, path / "absent-labels.json", preflight(path))
    assert not (path / "d06-run").exists()


def test_invalid_labels_leave_auditable_failed_run(bundle, monkeypatch):
    path, package = bundle
    monkeypatch.setattr(d06, "load_package", lambda _: package)
    (path / "labels.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        d06.evaluate(path, path, path / "labels.json", preflight(path))
    out = path / "d06-run"
    assert json.loads((out / "inputs.json").read_bytes())["status"] == "failed"
    assert not (out / "group-metrics.json").exists()


def test_empty_metrics_use_null_for_missing_denominator_and_errors():
    result = d06.score([], 0, d06.DOMAIN_MINIMUM)
    assert result["coverage"] is result["availability"] is result["mae_pct_points"] is None
    assert not result["coverage_evidence"] and not result["error_evidence"]
