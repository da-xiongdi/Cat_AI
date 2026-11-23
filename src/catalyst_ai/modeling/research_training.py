"""Training-only research core. Held-out test data is not an argument."""

from sklearn.dummy import DummyRegressor
from sklearn.ensemble import ExtraTreesRegressor
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
        return ExtraTreesRegressor(random_state=seed, **checked.params)

    results = []
    for candidate in candidates:
        feature = candidate["feature"]
        predictions = []
        for number, fold in enumerate(validation_folds):
            held = set(fold)
            fit = [by_id[i] for i in sorted(ids - held)]
            hold = [by_id[i] for i in sorted(held)]
            transform = transformer(fit, feature)
            matrix = [transform.transform_one(r["payload"])["values"] for r in fit]
            model = estimator(candidate).fit(matrix, [targets[r["record_id"]] for r in fit])
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
    selected = min(range(len(results)), key=lambda i: results[i]["metrics"]["mae"])
    candidate = candidates[selected]
    rows = [by_id[i] for i in sorted(ids)]
    transform = transformer(rows, candidate["feature"])
    model = estimator(candidate).fit(
        [transform.transform_one(r["payload"])["values"] for r in rows],
        [targets[r["record_id"]] for r in rows],
    )
    return {
        "selected_index": selected,
        "results": results,
        "transformer": transform,
        "model": model,
    }
