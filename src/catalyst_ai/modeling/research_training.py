"""Training-only research core. Held-out test data is not an argument."""

from sklearn.dummy import DummyRegressor
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor, GradientBoostingRegressor
import hashlib
import json
import time
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from catalyst_ai.datasets.split import normalize_doi
from catalyst_ai.features.enhanced import EnhancedFeatures
from catalyst_ai.features.pipeline import R1Features
from catalyst_ai.modeling.baseline import target_value
from catalyst_ai.modeling.config import Model
from catalyst_ai.modeling.experiments import _availability, _predict, _score


def train(
    records,
    snapshot_content,
    validation_folds,
    candidates,
    *,
    seed=42,
    properties=None,
    species=None,
    selection_rule="legacy",
):
    """Fit fold-local features and select one candidate by OOF MAE.

    All records passed here must belong to the training partition. The caller is
    responsible for validating the immutable split and input bindings first.
    """
    by_id = {r["record_id"]: r for r in records}
    ids = set(by_id)
    flat = [i for fold in validation_folds for i in fold]
    if (
        len(ids) != len(records)
        or len(flat) != len(set(flat))
        or set(flat) != ids
        or len(validation_folds) < 2
        or any(not f or len(f) == len(ids) for f in validation_folds)
    ):
        raise ValueError("invalid training folds")
    if not candidates:
        raise ValueError("no candidates")
    targets = {i: target_value(r, snapshot_content) for i, r in by_id.items()}

    def transformer(rows, feature):
        payloads = [r["payload"] for r in rows]
        if feature.endswith("+Cu"):
            from catalyst_ai.features.copper import CopperFeatures

            if species is None:
                raise ValueError("Cu requires bound species catalog")
            base = transformer(rows, feature[:-3])
            return CopperFeatures.fit(base, payloads, species)
        if feature in ("F3-P", "F3-H", "F3-I"):
            from catalyst_ai.features.f3 import F3Features

            if properties is None or species is None:
                raise ValueError("F3 requires bound property and species catalogs")
            return F3Features.fit(payloads, feature, properties=properties, species=species)
        if feature in ("F1", "F2"):
            if properties is None or species is None:
                raise ValueError("F1/F2 require bound property and species catalogs")
            return EnhancedFeatures.fit(payloads, feature, properties=properties, species=species)
        return R1Features.fit(payloads, feature)

    def estimator(candidate):
        checked = Model.model_validate(
            {"name": candidate["model"], "params": candidate.get("params", {})}
        )
        if checked.name == "dummy":
            return DummyRegressor(strategy="mean")
        if checked.name == "ridge":
            return make_pipeline(StandardScaler(), Ridge(**checked.params))
        if checked.name == "xgboost":
            from xgboost import XGBRegressor

            return XGBRegressor(device="cpu", tree_method="hist", n_jobs=1,
                                random_state=42, **checked.params)
        if checked.name == "random_forest":
            return RandomForestRegressor(random_state=seed, **checked.params)
        if checked.name == "gradient_boosting":
            return GradientBoostingRegressor(random_state=seed, **checked.params)
        return ExtraTreesRegressor(random_state=seed, **checked.params)

    results = []
    for candidate in candidates:
        feature = candidate["feature"]
        predictions = []
        fold_timing = []
        for number, fold in enumerate(validation_folds):
            started = time.perf_counter()
            held = set(fold)
            fit = [by_id[i] for i in sorted(ids - held)]
            hold = [by_id[i] for i in sorted(held)]
            transform = transformer(fit, feature)
            matrix = [transform.transform_one(r["payload"])["values"] for r in fit]
            model = estimator(candidate).fit(matrix, [targets[r["record_id"]] for r in fit])
            if selection_rule == "s5-paired-v1":
                from catalyst_ai.modeling.s5_selection import predict

                scored = predict(transform, model, hold)
            else:
                scored = _predict(transform, model, hold, range(len(hold)))
            predictions.extend(
                {
                    "record_id": r["record_id"],
                    "doi": normalize_doi(r["payload"]["source"]["doi"]),
                    "observed": float(targets[r["record_id"]]),
                    "fold": number,
                    **p,
                }
                for r, p in zip(hold, scored, strict=True)
            )
            fold_timing.append({"fold": number, "seconds": time.perf_counter() - started,
                                "fit_ids_sha256": hashlib.sha256(json.dumps(sorted(ids - held)).encode()).hexdigest(),
                                "validation_ids_sha256": hashlib.sha256(json.dumps(sorted(held)).encode()).hexdigest()})
        if selection_rule == "s5-paired-v1":
            from catalyst_ai.modeling.s5_selection import diagnostics

            report = diagnostics(predictions)
            results.append(
                {
                    "candidate": candidate,
                    "metrics": report["diagnostic_metrics"],
                    "fold_metrics": [
                        diagnostics([p for p in predictions if p["fold"] == k])
                        for k in range(len(validation_folds))
                    ],
                    "availability": report,
                    "predictions": predictions,
                    "fold_timing": fold_timing,
                }
            )
        else:
            results.append(
                {
                    "candidate": candidate,
                    "metrics": _score(predictions),
                    "fold_metrics": [
                        _score([p for p in predictions if p["fold"] == k])
                        for k in range(len(validation_folds))
                    ],
                    "availability": _availability(predictions),
                    "predictions": predictions,
                }
            )
    decision = None
    if selection_rule == "s5-paired-v1":
        from catalyst_ai.modeling.s5_selection import SelectionUnavailable, select

        decision = select(results)
        selected = decision["selected_index"]
        if selected is None:
            raise SelectionUnavailable(decision)
    elif selection_rule == "legacy":
        selected = min(range(len(results)), key=lambda i: results[i]["metrics"]["mae"])
    else:
        raise ValueError("unknown selection rule")
    rows = [by_id[i] for i in sorted(ids)]
    packages = []
    indices = range(len(candidates)) if selection_rule == "s5-paired-v1" else [selected]
    for index in indices:
        candidate = candidates[index]
        transform = transformer(rows, candidate["feature"])
        model = estimator(candidate).fit(
            [transform.transform_one(r["payload"])["values"] for r in rows],
            [targets[r["record_id"]] for r in rows],
        )
        packages.append({"candidate_index": index, "transformer": transform, "model": model})
    selected_package = next(p for p in packages if p["candidate_index"] == selected)
    return {
        "selected_index": selected,
        "selection_decision": decision,
        "results": results,
        "transformer": selected_package["transformer"],
        "model": selected_package["model"],
        "packages": packages,
    }
