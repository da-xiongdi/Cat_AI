from copy import deepcopy

import pytest
from test_baseline import prepared
from test_split import rehash_snapshot

pytest.importorskip("shap")

from catalyst_ai.datasets.split import build_paper_split  # noqa: E402
from catalyst_ai.features.design import build_feature_table  # noqa: E402
from catalyst_ai.modeling.baseline import save_run, train_baselines  # noqa: E402
from catalyst_ai.modeling.diagnostics import analyze  # noqa: E402
from catalyst_ai.modeling.screening import screen  # noqa: E402
from catalyst_ai.reporting.evidence import digest  # noqa: E402


def measurement(value, unit):
    return {"state": "reported", "normalized_value": value, "normalized_unit": unit}


def baseline(sample, tmp_path):
    snapshot, qualification, _, _ = prepared(sample)
    for i, record in enumerate(snapshot["content"]["records"]):
        source = record["payload"]["source"]
        source.update(source_id=f"source-{i}", title=f"paper {i}", doi=f"10.1234/paper{i}")
        record["input_locator"] = f"fixture:{i}"
        test = record["payload"]["test"]
        test["pressure"] = measurement(10, "bar(abs)")
        test["pressure_type"] = "absolute"
        test["catalyst_mass"] = measurement(0.5, "g")
        test["reactant_ratio"] = {
            "numerator": "H2",
            "denominator": "CO2",
            "value": measurement(3, "1"),
        }
        test["mass_normalized_volume_flow"] = {
            "mass_basis": "catalyst",
            "gas_scope": "reactants_only",
            "reference_pressure_type": "absolute",
            "reference_temperature": measurement(293.15, "K"),
            "reference_pressure": measurement(1.01325, "bar(abs)"),
            "value": measurement(10, "NL/g_cat/h"),
        }
    rehash_snapshot(snapshot, qualification)
    split = build_paper_split(snapshot, qualification)
    args = (snapshot, qualification, split, build_feature_table(snapshot, qualification, split))
    report, bundle = train_baselines(*args)
    # Diagnostics only supports the tree model; preserve the fitted estimator and test predictions.
    report["model_selection"]["selected"] = "extra_trees"
    bundle["selected"] = "extra_trees"
    lock = tmp_path / "lock"
    lock.write_text("test", encoding="utf-8")
    report = save_run(tmp_path / "run", report, bundle, lock_path=lock)
    return args, report, tmp_path / "run" / "models.joblib"


def test_diagnostics_additivity_and_independent_group_counts(sample, tmp_path):
    args, run, model = baseline(sample, tmp_path)
    result = analyze(run, model, *args)
    assert result["shap"]["max_additivity_error"] < 1e-7
    assert result["spread"]["calibrated"] is False
    assert result["held_out"]["test"]["paper_groups"] == 1
    assert result["domain"]["probability_or_accuracy_guarantee"] is False
    tampered = deepcopy(run)
    tampered["model_selection"]["selected"] = "dummy"
    with pytest.raises(ValueError, match="report hash"):
        analyze(tampered, model, *args)


def test_screening_requires_evidence_and_valid_capacity(sample, tmp_path):
    args, run, model = baseline(sample, tmp_path)
    content = {"baseline_run_id": run["run_id"]}
    h = digest(content)
    diagnostic = {"content": content, "content_sha256": h, "diagnostic_id": "diagnostic-" + h}
    with pytest.raises(ValueError, match="capacity"):
        screen({"capacity": 7}, diagnostic, run, model, *args)
    with pytest.raises(ValueError, match="candidate designs"):
        screen({"capacity": 4}, diagnostic, run, model, *args)
    with pytest.raises(ValueError, match="evidence required"):
        screen({"candidates": [{"candidate_id": "x"}]}, diagnostic, run, model, *args)
    diagnostic["content"]["baseline_run_id"] = "changed"
    with pytest.raises(ValueError, match="hash mismatch"):
        screen({}, diagnostic, run, model, *args)


def test_screening_proposals_filter_invalid_and_enforce_fixed_conditions(sample, tmp_path):
    args, run, model = baseline(sample, tmp_path)
    snapshot, _, split, _ = args
    train_id = split["content"]["splits"]["train"]["record_ids"][0]
    record = next(r for r in snapshot["content"]["records"] if r["record_id"] == train_id)
    payload = record["payload"]
    recipe = deepcopy(payload["recipe"])
    for component in recipe["components"]:
        component["amount"]["normalized_value"] = 50
    candidate = {
        "candidate_id": "fixture-a",
        "recipe": recipe,
        "planned_synthesis": {"route": "fixture route", "evidence": "fixture evidence"},
    }
    invalid = deepcopy(candidate)
    invalid["candidate_id"] = "fixture-b"
    invalid["recipe"]["components"][0]["species"] = "UNSEEN"
    content = {"baseline_run_id": run["run_id"], "domain": {"threshold": 100000}}
    h = digest(content)
    diagnostic = {"content": content, "content_sha256": h, "diagnostic_id": "diagnostic-" + h}
    spec = {
        "candidates": [candidate, invalid],
        "fixed_test": payload["test"],
        "allowed_species": [c["species"] for c in recipe["components"]],
        "condition_bounds": {
            "temperature_k": [0, 1000],
            "pressure_bar_abs": [0, 100],
            "catalyst_mass_g": [0, 2],
            "h2_co2_ratio": [0, 10],
            "reactants_flow_nl_g_h": [0, 100],
        },
        "constraint_evidence": {
            k: "fixture"
            for k in ("equipment", "chemistry_compatibility", "precursors", "cost_risk")
        },
    }
    result = screen(spec, diagnostic, run, model, *args)
    assert result["scientific_use"] is False
    assert [c["candidate_id"] for c in result["selected"]] == ["fixture-a"]
    assert result["selected"][0]["status"] == "proposed"
    assert "unseen_component" in result["rejected"][0]["reasons"]
