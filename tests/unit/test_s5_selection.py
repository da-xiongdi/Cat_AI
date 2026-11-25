import pytest

from catalyst_ai.modeling.s5_selection import select


def result(feature, values, status=None):
    return {
        "candidate": {"feature": feature, "model": "extra_trees"},
        "predictions": [
            {
                "record_id": str(i),
                "fold": i % 5,
                "observed": 0.0,
                "raw_prediction": v,
                "status": "ok" if status is None else status[i],
            }
            for i, v in enumerate(values)
        ],
    }


def test_common_support_and_added_coverage():
    a = result("F_base", [1.0] * 90 + [None] * 10)
    b = result("F1", [0.5] * 85 + [None] * 5 + [0.5] * 10)
    d = select([a, b])
    c = d["comparisons"][1]
    assert c["common_with_baseline"] == 85 and len(c["new_coverage_ids"]) == 10
    assert len(c["lost_coverage_ids"]) == 5 and c["mae_delta_vs_baseline"] == pytest.approx(-0.5)
    assert d["selected_index"] == 1


def test_tie_prioritizes_baseline_and_catalog_order():
    a = result("F_base", [1.0] * 100)
    b = result("F1", [0.95] * 100)
    assert select([a, b])["selected_index"] == 0
    c = result("F2", [0.5] * 100)
    d = result("F1", [0.55] * 100)
    assert select([a, c, d])["selected_index"] == 1


def test_low_support_and_all_fail():
    a = result("F_base", [1.0] * 100)
    b = result("F1", [0.1] * 20 + [None] * 80)
    d = select([a, b])
    assert d["selected_index"] == 0 and not d["comparisons"][1]["eligible"]
    a = result("F_base", [1.0] * 20 + [None] * 80)
    b = result("F1", [0.1] * 20 + [None] * 80)
    d = select([a, b])
    assert d["selected_index"] is None and d["reason"] == "baseline_not_eligible_no_selection"


def test_all_candidate_intersection_fallback():
    a = result("F_base", [1.0] * 100)
    # Pairwise support passes, but the total intersection loses five disjoint slices.
    candidates = [a] + [
        result("F1", [None if i in range(k * 5, (k + 1) * 5) else 0.1 for i in range(100)])
        for k in range(5)
    ]
    d = select(candidates)
    assert (
        d["selected_index"] == 0
        and d["reason"] == "insufficient_all_candidate_common_support_baseline_fallback"
    )


def test_reject_mismatched_members_and_folds():
    a = result("F_base", [1.0] * 100)
    b = result("F1", [1.0] * 100)
    b["predictions"][0]["fold"] = 4
    with pytest.raises(ValueError, match="fold or target"):
        select([a, b])
    b["predictions"].pop()
    with pytest.raises(ValueError, match="share OOF"):
        select([a, b])


def test_nullable_predictions_preserve_rows_and_denominators():
    from catalyst_ai.modeling.s5_selection import diagnostics, predict

    class Transform:
        def transform_one(self, payload, diagnostic):
            return {"values": payload, "status": "ok"}

    class Model:
        def predict(self, values):
            return [float("nan") if x[0] == 2 else 8.0 for x in values]

    records = [{"payload": [1.0]}, {"payload": None}, {"payload": [2.0]}]
    out = predict(Transform(), Model(), records)
    assert [x["raw_prediction"] for x in out] == [8.0, None, None]
    assert [x["status"] for x in out] == ["ok", "unencodable", "non_finite_prediction"]
    rows = [dict(item, record_id=str(i), doi="x", observed=7.0) for i, item in enumerate(out)]
    report = diagnostics(rows)
    assert (
        report["total_records"],
        report["diagnostic_records"],
        report["available_records"],
        report["null_prediction_records"],
    ) == (3, 1, 1, 2)


def test_s5_training_and_scoring_isolation(tmp_path, monkeypatch):
    from pathlib import Path

    from catalyst_ai.modeling import research_run
    from catalyst_ai.modeling.research_preflight import preflight

    root = Path(__file__).resolve().parents[2]
    checked = preflight(root / "configs/research_preflight_example.json", root=root)
    ids = checked["split"]["train"]
    train, test = ids[:60], ids[60:65]
    checked["split"] = {
        "train": train,
        "test": test,
        "validation_folds": [train[i::5] for i in range(5)],
    }
    checked["config"]["schema_version"] = 2
    checked["config"]["selection_rule"] = "s5-paired-v1"
    checked["config"]["candidates"] = [
        {
            "feature": "F_base",
            "model": "extra_trees",
            "params": {"n_estimators": 10, "min_samples_leaf": 2, "n_jobs": 1},
        }
    ]
    checked["config"]["outputs"] = ["predictions"]
    monkeypatch.setattr(research_run, "preflight", lambda *args, **kwargs: checked)
    held = [r for r in checked["snapshot"]["content"]["records"] if r["record_id"] in test]
    labels = [r["payload"]["observations"] for r in held]
    for r in held:
        r["payload"]["observations"] = []
    run = tmp_path / "run"
    research_run.fit("ignored", run, root=root)
    import json

    cv = json.loads((run / "cross_validation.json").read_text(encoding="utf-8"))
    assert cv["selection_decision"]["version"] == "s5-paired-v1"
    assert {p["record_id"] for p in cv["results"][0]["predictions"]} == set(train)
    assert not (run / "holdout").exists()
    for r, v in zip(held, labels, strict=True):
        r["payload"]["observations"] = v
    research_run.score(run, root=root)
    with pytest.raises(FileExistsError):
        research_run.score(run, root=root)
