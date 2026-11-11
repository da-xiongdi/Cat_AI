"""Fixed, paper-held-out exploratory baselines; validation selects before test evaluation."""

import hashlib
import importlib.metadata
import math
import platform
from pathlib import Path

import joblib
import numpy as np
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from catalyst_ai.features.design import build_feature_table
from catalyst_ai.reporting.evidence import digest, write_json


def feature_matrix(rows, names):
    """Apply a training-defined feature list without fitting to held-out rows."""
    matrix = []
    for row in rows:
        values = {"condition:" + k: v for k, v in row["values"].items()}
        values.update({"component:" + k: v for k, v in row["composition_values"].items()})
        matrix.append([np.nan if values.get(name) is None else values[name] for name in names])
    return np.asarray(matrix, dtype=float)


def target_value(record, content):
    matches = [o for o in record["payload"]["observations"] if o["metric"] == content["target"]]
    if len(matches) != 1:
        raise ValueError("Each record must have exactly one target observation")
    value = matches[0]["value"]
    number = value.get("normalized_value")
    if (
        value.get("state") not in ("reported", "zero")
        or isinstance(number, bool)
        or not isinstance(number, (int, float))
        or not math.isfinite(number)
        or value.get("normalized_unit") != content["target_unit"]
        or value.get("definition") != content["target_definition"]
    ):
        raise ValueError("Target value, unit or definition is invalid")
    return number


def metrics(y, predicted):
    r2 = float(r2_score(y, predicted)) if len(y) >= 2 and np.ptp(y) > 0 else None
    return {
        "mae": float(mean_absolute_error(y, predicted)),
        "rmse": float(math.sqrt(mean_squared_error(y, predicted))),
        "r2": r2,
        "r2_unavailable_reason": None
        if r2 is not None
        else "fewer than two values or zero variance",
    }


def train_baselines(snapshot, qualification, split, features, *, seed=42):
    # Recreate the I3 projection to enforce its allowlist, fitted vocabulary and input identity.
    if features != build_feature_table(snapshot, qualification, split):
        raise ValueError("Feature table does not match the validated snapshot and split")
    content = snapshot["content"]
    rows = features["content"]["rows"]
    records = {r["record_id"]: r for r in content["records"]}
    parts = {p: [r for r in rows if r["partition"] == p] for p in ("train", "validation", "test")}
    if any(not part for part in parts.values()):
        raise ValueError("Every partition must be nonempty")
    all_names = sorted(
        {"condition:" + key for r in parts["train"] for key in r["values"]}
        | {"component:" + key for key in features["content"]["composition_vocabulary"]}
    )
    initial = feature_matrix(parts["train"], all_names)
    keep = ~np.isnan(initial).all(axis=0)
    names = [name for name, retained in zip(all_names, keep, strict=True) if retained]
    if not names:
        raise ValueError("No nonmissing training features")
    matrices = {p: feature_matrix(parts[p], names) for p in ("train", "validation")}
    targets = {
        p: np.asarray(
            [target_value(records[r["record_id"]], content) for r in parts[p]], dtype=float
        )
        for p in ("train", "validation")
    }
    models = {
        "dummy": DummyRegressor(strategy="mean"),
        "ridge": Ridge(alpha=1.0),
        "extra_trees": ExtraTreesRegressor(
            n_estimators=100, min_samples_leaf=2, random_state=seed, n_jobs=1
        ),
    }
    fitted, validation = {}, {}
    for name, model in models.items():
        # Median and missing indicators are fitted solely on the train partition.
        pipeline = make_pipeline(
            SimpleImputer(strategy="median", add_indicator=True), StandardScaler(), model
        )
        pipeline.fit(matrices["train"], targets["train"])
        fitted[name] = pipeline
        validation[name] = metrics(targets["validation"], pipeline.predict(matrices["validation"]))
    # Stable tie break, entirely before accessing any test metrics.
    selected = min(sorted(validation), key=lambda name: validation[name]["mae"])
    matrices["test"] = feature_matrix(parts["test"], names)
    targets["test"] = np.asarray(
        [target_value(records[r["record_id"]], content) for r in parts["test"]], dtype=float
    )
    results = {name: {"validation": value} for name, value in validation.items()}
    predictions = {}
    for name, pipeline in fitted.items():
        predicted = pipeline.predict(matrices["test"])
        results[name]["test"] = metrics(targets["test"], predicted)
        predictions[name] = [float(x) for x in predicted]
    coverage = {}
    for partition, part in parts.items():
        condition_coverage = {}
        for key in sorted(part[0]["values"]):
            observed = [r["values"][key] for r in part if r["values"][key] is not None]
            condition_coverage[key] = {
                "available": len(observed),
                "range": [min(observed), max(observed)] if observed else None,
            }
        y = targets[partition]
        coverage[partition] = {
            "records": len(part),
            "paper_groups": split["content"]["splits"][partition]["paper_group_count"],
            "target_range": [float(y.min()), float(y.max())],
            "conditions": condition_coverage,
        }
    report = {
        "schema_version": "i4-baselines-v1",
        "snapshot_id": snapshot["snapshot_id"],
        "qualification_id": qualification["qualification_id"],
        "split_id": split["split_id"],
        "feature_table_id": features["feature_table_id"],
        "feature_version": features["content"]["feature_version"],
        "dataset_kind": content["dataset_kind"],
        "scientific_use": content["scientific_use"],
        "target": {
            "metric": content["target"],
            "definition": content["target_definition"],
            "unit": content["target_unit"],
        },
        "configuration": {
            "seed": seed,
            "selection": "validation MAE; alphabetical tie break",
            "refit_on_validation": False,
            "imputation": "training median + missing indicators",
            "scaling": "training mean and standard deviation",
            "ridge_alpha": 1.0,
            "extra_trees_estimators": 100,
            "extra_trees_min_samples_leaf": 2,
        },
        "training_features": names,
        "dropped_all_missing_training_features": [
            n for n, retain in zip(all_names, keep, strict=True) if not retain
        ],
        "model_selection": {"selected": selected, "validation_metrics": validation},
        "metrics": results,
        "coverage": coverage,
        "test_predictions": [
            {
                "record_id": row["record_id"],
                "observed": float(targets["test"][i]),
                "predicted": {name: values[i] for name, values in predictions.items()},
            }
            for i, row in enumerate(parts["test"])
        ],
        "limitations": [
            "Published dataset accepted, not individually source verified",
            "Pressure type follows user assumption, not original source confirmation",
            "Paper holdout does not prove sample or batch independence",
            "Exploratory evaluation; no calibrated uncertainty or applicability domain",
        ],
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in ("scikit-learn", "numpy", "scipy", "joblib")
        },
        "python": platform.python_version(),
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    return report, {"models": fitted, "feature_names": names, "selected": selected}


def save_run(output, report, models, *, lock_path):
    """Create a new run directory; refuse any pre-existing output."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    model_path = output / "models.joblib"
    joblib.dump(models, model_path, compress=3)
    report["artifacts"] = {
        "models": {
            "path": model_path.name,
            "sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        },
        "lock_sha256": hashlib.sha256(Path(lock_path).read_bytes()).hexdigest(),
    }
    report["run_id"] = "baseline-" + digest(report)
    write_json(output / "report.json", report)
    return report
