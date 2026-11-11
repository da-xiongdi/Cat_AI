"""Exploratory, paper-group-aware diagnostics for a frozen I4 run."""

import hashlib
import importlib.metadata
import math
from collections import defaultdict
from pathlib import Path

import joblib
import numpy as np
import shap
from sklearn.inspection import permutation_importance
from sklearn.metrics import pairwise_distances

from catalyst_ai.datasets.split import normalize_doi
from catalyst_ai.features.design import build_feature_table
from catalyst_ai.modeling.baseline import feature_matrix, metrics, target_value
from catalyst_ai.reporting.evidence import digest


def verified_model(run, model_path, snapshot, qualification, split, features):
    bare = {k: v for k, v in run.items() if k != "run_id"}
    if run.get("run_id") != "baseline-" + digest(bare):
        raise ValueError("Baseline report hash mismatch")
    if (
        hashlib.sha256(Path(model_path).read_bytes()).hexdigest()
        != run["artifacts"]["models"]["sha256"]
    ):
        raise ValueError("Model file hash mismatch")
    if features != build_feature_table(snapshot, qualification, split):
        raise ValueError("Features do not match validated frozen inputs")
    for field, value in (
        ("snapshot_id", snapshot["snapshot_id"]),
        ("qualification_id", qualification["qualification_id"]),
        ("split_id", split["split_id"]),
        ("feature_table_id", features["feature_table_id"]),
    ):
        if run[field] != value:
            raise ValueError("Baseline inputs do not match")
    for name, version in run["dependencies"].items():
        if importlib.metadata.version(name) != version:
            raise ValueError("Baseline dependency version mismatch: " + name)
    # joblib is executable serialization: only load files from a trusted producer.
    bundle = joblib.load(model_path)
    if (
        bundle["selected"] != run["model_selection"]["selected"]
        or bundle["feature_names"] != run["training_features"]
    ):
        raise ValueError("Model metadata mismatch")
    model = bundle["models"][bundle["selected"]]
    if bundle["selected"] != "extra_trees":
        raise ValueError("This diagnostic version supports only Extra Trees")
    return model, bundle["feature_names"]


def transformed_names(model, names):
    missing = model.named_steps["simpleimputer"].indicator_.features_
    return names + ["missing:" + names[i] for i in missing]


def estimate_spread(model, x):
    transformed = model[:-1].transform(x)
    ensemble = model[-1]
    tree_predictions = np.asarray([tree.predict(transformed) for tree in ensemble.estimators_])
    return np.mean(tree_predictions, axis=0), np.std(tree_predictions, axis=0)


def analyze(run, model_path, snapshot, qualification, split, features, *, seed=42):
    model, names = verified_model(run, model_path, snapshot, qualification, split, features)
    rows = features["content"]["rows"]
    records = {r["record_id"]: r for r in snapshot["content"]["records"]}
    parts = {p: [r for r in rows if r["partition"] == p] for p in ("train", "validation", "test")}
    xs = {p: feature_matrix(v, names) for p, v in parts.items()}
    ys = {
        p: np.asarray([target_value(records[r["record_id"]], snapshot["content"]) for r in v])
        for p, v in parts.items()
    }
    groups = {
        p: [normalize_doi(records[r["record_id"]]["payload"]["source"]["doi"]) for r in v]
        for p, v in parts.items()
    }

    # I4's stored held-out predictions must agree with the trusted model before diagnostics.
    stored = {r["record_id"]: r for r in run["test_predictions"]}
    reproduced = model.predict(xs["test"])
    if len(stored) != len(parts["test"]) or not all(
        r["record_id"] in stored
        and math.isclose(
            float(reproduced[i]),
            stored[r["record_id"]]["predicted"]["extra_trees"],
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
        and math.isclose(
            float(ys["test"][i]), stored[r["record_id"]]["observed"], rel_tol=0, abs_tol=1e-12
        )
        for i, r in enumerate(parts["test"])
    ):
        raise ValueError("Baseline test predictions do not reproduce")

    perm = permutation_importance(
        model,
        xs["validation"],
        ys["validation"],
        scoring="neg_mean_absolute_error",
        n_repeats=5,
        random_state=seed,
        n_jobs=1,
    )
    permutation = sorted(
        [
            {"feature": n, "mean_mae_increase": float(m), "std": float(s)}
            for n, m, s in zip(names, perm.importances_mean, perm.importances_std, strict=True)
        ],
        key=lambda x: (-x["mean_mae_increase"], x["feature"]),
    )
    processed = model[:-1].transform(xs["validation"])
    explainer = shap.TreeExplainer(model[-1], feature_perturbation="tree_path_dependent")
    values = np.asarray(explainer.shap_values(processed))
    if values.shape != processed.shape:
        raise ValueError("Unexpected SHAP output shape")
    base = float(np.asarray(explainer.expected_value).reshape(-1)[0])
    additivity_error = float(
        np.max(np.abs(base + values.sum(axis=1) - model.predict(xs["validation"])))
    )
    if additivity_error > 1e-7:
        raise ValueError("SHAP additivity check failed")
    shap_summary = sorted(
        [
            {"feature": n, "mean_absolute_shap": float(v)}
            for n, v in zip(
                transformed_names(model, names), np.mean(np.abs(values), axis=0), strict=True
            )
        ],
        key=lambda x: (-x["mean_absolute_shap"], x["feature"]),
    )

    # Distances use only train-fitted preprocessing. Leave each paper out when setting threshold.
    z = {p: model[:-1].transform(x) for p, x in xs.items()}
    dtrain = pairwise_distances(z["train"], z["train"])
    for i, gi in enumerate(groups["train"]):
        for j, gj in enumerate(groups["train"]):
            if gi == gj:
                dtrain[i, j] = np.inf
    nearest_train = dtrain.min(axis=1)
    if not np.isfinite(nearest_train).all():
        raise ValueError("At least two independent training papers are required")
    threshold = float(np.quantile(nearest_train, 0.95))
    distances = {
        p: pairwise_distances(z[p], z["train"]).min(axis=1) for p in ("validation", "test")
    }
    partitions = {}
    for p in ("validation", "test"):
        mean, sd = estimate_spread(model, xs[p])
        residuals = np.abs(ys[p] - mean)
        covered = residuals <= 2 * sd
        grouped = defaultdict(list)
        for i, doi in enumerate(groups[p]):
            grouped[doi].append(i)
        group_results = []
        for doi, indices in sorted(grouped.items()):
            group_results.append(
                {
                    "doi": doi,
                    "count": len(indices),
                    "metrics": metrics(ys[p][indices], mean[indices]),
                    "spread_band_coverage": float(np.mean(covered[indices])),
                }
            )
        partitions[p] = {
            "count": len(parts[p]),
            "paper_groups": len(grouped),
            "tree_spread_mean": float(sd.mean()),
            "two_spread_band_coverage": float(covered.mean()),
            "two_spread_band_mean_width": float(np.mean(4 * sd)),
            "outside_distance_count": int(np.sum(distances[p] > threshold)),
            "rows_with_unseen_components": sum(bool(r["unseen_component_count"]) for r in parts[p]),
            "condition_range_extrapolation_count": sum(
                any(
                    r["values"].get(key) is not None
                    and bounds["range"] is not None
                    and not bounds["range"][0] <= r["values"][key] <= bounds["range"][1]
                    for key, bounds in run["coverage"]["train"]["conditions"].items()
                )
                for r in parts[p]
            ),
            "per_paper": group_results,
        }
    return {
        "schema_version": "i5-diagnostics-v1",
        "baseline_run_id": run["run_id"],
        "snapshot_id": snapshot["snapshot_id"],
        "split_id": split["split_id"],
        "feature_table_id": features["feature_table_id"],
        "model": "extra_trees",
        "seed": seed,
        "permutation_partition": "validation",
        "permutation_repeats": 5,
        "permutation_importance": permutation,
        "shap": {
            "partition": "validation",
            "method": "tree_path_dependent",
            "expected_value": base,
            "max_additivity_error": additivity_error,
            "mean_absolute_values": shap_summary,
        },
        "domain": {
            "method": "train-scaled Euclidean; nearest training record",
            "threshold": threshold,
            "threshold_method": "95th percentile train nearest distance excluding same paper",
            "probability_or_accuracy_guarantee": False,
        },
        "spread": {
            "method": "population standard deviation across fitted trees",
            "band": "prediction +/- 2 tree standard deviations",
            "calibrated": False,
            "nominal_coverage": None,
        },
        "held_out": partitions,
        "limitations": [
            "validation data was used to choose the model; explanations are exploratory",
            "SHAP and permutation importance are not causal; correlated and missing features "
            "can distort attribution",
            "distance threshold is a heuristic, not a validated applicability guarantee",
            "tree spread is not a calibrated prediction interval; records within a paper "
            "are dependent",
            "published dataset not individually verified; pressure type is assumed absolute",
            "paper holdout does not prove independent sample or batch identity",
        ],
        "dependencies": {"shap": importlib.metadata.version("shap"), **run["dependencies"]},
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
