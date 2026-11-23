"""Training and separately invoked holdout scoring for validated experiments."""

import importlib.metadata
import pickle
import platform
import traceback
from pathlib import Path

from catalyst_ai.datasets.split import normalize_doi
from catalyst_ai.modeling.baseline import target_value
from catalyst_ai.modeling.experiments import _availability, _predict, _score
from catalyst_ai.modeling.research_plots import write_plots
from catalyst_ai.modeling.research_preflight import preflight, read_json, sha
from catalyst_ai.modeling.research_training import train
from catalyst_ai.reporting.evidence import digest, write_json, write_new
from catalyst_ai.storage.feature_catalog import get_catalog


def code_hash():
    src = Path(__file__).resolve().parents[1]
    return digest({p.relative_to(src).as_posix(): sha(p) for p in sorted(src.rglob("*.py"))})


def environment():
    return {
        "python": platform.python_version(),
        "scikit_learn": importlib.metadata.version("scikit-learn"),
        "numpy": importlib.metadata.version("numpy"),
        "code_sha256": code_hash(),
        "platform": platform.platform(),
        "packages": dict(
            sorted(
                (d.metadata["Name"], d.version)
                for d in importlib.metadata.distributions()
                if d.metadata.get("Name")
            )
        ),
    }


def fit(config_path, output, *, root):
    """Create a new development run. No held-out target is used for fitting."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    try:
        return _fit(config_path, output, root=root)
    except Exception:
        write_new(output / "failure.log", traceback.format_exc().encode("utf-8"))
        raise


def fit_batch(config_directory, output, *, root):
    """Train each prepared configuration independently, retaining failed attempts."""
    paths = sorted(Path(config_directory).glob("*.json"))
    if not paths:
        raise ValueError("no experiment configurations")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for path in paths:
        try:
            fit(path, output / path.stem, root=root)
        except Exception as error:
            results.append({"config": str(path), "status": "failed", "error": str(error)})
        else:
            results.append({"config": str(path), "status": "completed"})
    write_json(output / "batch.json", {"runs": results})
    return results


def _fit(config_path, output, *, root):
    root = Path(root).resolve()
    checked = preflight(config_path, root=root)
    content, split, config = checked["snapshot"]["content"], checked["split"], checked["config"]
    selection_paths = [
        p for p in checked["view"]["content"]["binding"]["sources"] if p.endswith("/selection.json")
    ]
    if len(selection_paths) != 1:
        raise ValueError("feature selection binding is ambiguous")
    selection = read_json(root / selection_paths[0])
    binding = selection["content"]["binding"]
    if (
        digest(selection["content"]) != selection["content_sha256"]
        or selection["selection_id"] != checked["view"]["content"]["binding"]["selection_id"]
        or binding["snapshot_id"] != checked["snapshot"]["snapshot_id"]
        or binding["snapshot_sha256"] != checked["snapshot"]["content_sha256"]
    ):
        raise ValueError("feature selection binding mismatch")
    database = root / config["catalog_database"]
    properties = get_catalog(database, "properties", binding["property_version"])
    species = get_catalog(database, "species", binding["mapping_version"])
    if (
        properties["sha256"] != binding["property_sha256"]
        or species["sha256"] != binding["mapping_sha256"]
    ):
        raise ValueError("feature catalog hash mismatch")
    train_ids = set(split["train"])
    records = [r for r in content["records"] if r["record_id"] in train_ids]
    result = train(
        records,
        content,
        split["validation_folds"],
        config["candidates"],
        seed=config["model_seed"],
        properties=properties,
        species=species,
    )
    write_json(output / "config.json", config)
    write_json(output / "split.json", split)
    write_json(
        output / "cross_validation.json",
        {"selected_index": result["selected_index"], "results": result["results"]},
    )
    write_new(
        output / "run.log",
        b"Training and cross-validation completed; holdout scoring not performed.\n",
    )
    write_new(
        output / "model.pkl",
        pickle.dumps({"model": result["model"], "transformer": result["transformer"]}, protocol=5),
    )
    lock = {
        "schema_version": 1,
        "input_hashes": checked["hashes"],
        "environment": environment(),
        "feature_catalogs": {"properties": properties["sha256"], "species": species["sha256"]},
        "artifacts": {
            name: sha(output / name)
            for name in (
                "config.json",
                "split.json",
                "cross_validation.json",
                "model.pkl",
                "run.log",
            )
        },
        "selected_index": result["selected_index"],
        "test_scored": False,
    }
    write_json(output / "lock.json", lock)
    return lock


def load_locked_model(run):
    """Load a trusted research package after checking its artifacts and runtime."""
    run = Path(run)
    lock = read_json(run / "lock.json")
    required = {"config.json", "split.json", "cross_validation.json", "model.pkl", "run.log"}
    if lock.get("schema_version") != 1 or set(lock.get("artifacts", {})) != required:
        raise ValueError("invalid run lock")
    if lock["environment"] != environment():
        raise ValueError("runtime or code differs from training")
    for name, expected in lock["artifacts"].items():
        if sha(run / name) != expected:
            raise ValueError(f"locked artifact mismatch: {name}")
    return lock, pickle.loads((run / "model.pkl").read_bytes())


def predict_payloads(run, payloads):
    """Predict governed payloads without loading training or test records."""
    if not payloads:
        raise ValueError("prediction inputs are empty")
    lock, package = load_locked_model(run)
    rows = [{"record_id": str(i), "payload": item} for i, item in enumerate(payloads)]
    results = _predict(package["transformer"], package["model"], rows, range(len(rows)))
    return {
        "model_sha256": lock["artifacts"]["model.pkl"],
        "semantics": "diagnostic raw predictions; only ok or caution are available",
        "predictions": results,
    }


def score(run, *, root, retry=False):
    """Score a locked model once; only load model packages created by trusted runs."""
    run = Path(run)
    lock, package = load_locked_model(run)
    checked = preflight(run / "config.json", root=root)
    if checked["hashes"] != lock["input_hashes"] or checked["split"] != read_json(
        run / "split.json"
    ):
        raise ValueError("locked input mismatch")
    prior = sorted(p for p in run.glob("holdout*") if p.is_dir())
    if any((p / "manifest.json").exists() for p in prior):
        raise FileExistsError("holdout has already been scored")
    if prior:
        if not retry or any(not (p / "failure.log").is_file() for p in prior):
            raise FileExistsError("previous holdout attempt requires explicit retry after failure")
        output = run / f"holdout-retry-{len(prior):03d}"
    else:
        if retry:
            raise ValueError("no failed holdout attempt to retry")
        output = run / "holdout"
    output.mkdir(exist_ok=False)
    try:
        return _score_holdout(checked, lock, package, output)
    except Exception:
        write_new(output / "failure.log", traceback.format_exc().encode("utf-8"))
        raise


def _score_holdout(checked, lock, package, output):
    content, split = checked["snapshot"]["content"], checked["split"]
    test_ids = set(split["test"])
    rows = [r for r in content["records"] if r["record_id"] in test_ids]
    predicted = _predict(package["transformer"], package["model"], rows, range(len(rows)))
    predictions = [
        {
            "record_id": r["record_id"],
            "doi": normalize_doi(r["payload"]["source"]["doi"]),
            "observed": float(target_value(r, content)),
            **p,
        }
        for r, p in zip(rows, predicted, strict=True)
    ]
    full_metrics = _score(predictions)
    chosen = checked["config"].get("metrics", ["mae", "rmse", "r2", "availability"])
    metrics = {
        "metrics": {
            k: v
            for k, v in full_metrics.items()
            if k in chosen or k in ("records", "papers", "r2_unavailable_reason")
        },
        "model_sha256": lock["artifacts"]["model.pkl"],
    }
    if "availability" in chosen:
        metrics["availability"] = _availability(predictions)
    selected_outputs = checked["config"].get("outputs", ["predictions", "plots"])
    if "predictions" in selected_outputs:
        write_json(output / "predictions.json", predictions)
    write_json(output / "metrics.json", metrics)
    if "plots" in selected_outputs:
        write_plots(output, predictions)
    write_json(
        output / "manifest.json",
        {"files": {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()}},
    )
    return metrics
