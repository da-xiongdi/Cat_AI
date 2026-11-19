import json

import numpy as np
import pytest
from sklearn.preprocessing import StandardScaler
from test_experiments import prepared
from test_split import rehash_snapshot

from catalyst_ai.datasets.split import build_paper_split
from catalyst_ai.features.enhanced import EnhancedFeatures
from catalyst_ai.features.pipeline import R1Features
from catalyst_ai.modeling.experiments import _score, run_configured


@pytest.fixture
def experiment(sample, tmp_path, monkeypatch):
    import catalyst_ai.modeling.config as config_module
    import catalyst_ai.storage.feature_catalog as catalog_module

    snapshot, qualification, _ = prepared(sample)
    for i, record in enumerate(snapshot["content"]["records"]):
        record["payload"]["source"].update(doi=f"10.1234/paper{i // 2}", title=f"paper {i // 2}")
    rehash_snapshot(snapshot, qualification)
    split = build_paper_split(snapshot, qualification)
    selection = {
        "content": {
            "binding": {"property_version": "v", "mapping_version": "v"},
            "retained": {
                p: split["content"]["splits"][p]["record_ids"]
                for p in ("train", "validation", "test")
            },
        },
        "content_sha256": "selection",
    }
    selection["content"]["excluded"] = {p: [] for p in ("train", "validation", "test")}
    docs = {
        "snapshot": snapshot,
        "qualification": qualification,
        "split": split,
        "selection": selection,
        "features": {"content_sha256": "features"},
    }
    for name, document in docs.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(document), encoding="utf-8")
    from catalyst_ai.features.physchem import PROPERTIES

    properties = {
        "catalog": {
            "entries": [
                {"element": "A", "property": prop, "state": "available", "value": 1.0}
                for prop in PROPERTIES
            ]
        }
    }
    species = {
        "catalog": {
            "entries": [
                {"species": f"X{i}", "state": "supported", "centers": {"A": 1}} for i in range(12)
            ]
        }
    }
    catalogs = (properties, species)
    monkeypatch.setattr(
        catalog_module,
        "get_catalog",
        lambda db, kind, version: properties if kind == "properties" else species,
    )
    effective = {
        "mode": "custom_train",
        "dataset": {**{n: f"{n}.json" for n in docs}, "catalog_database": "catalog"},
        "features": {"preset": "R2", "sets": ["F2", "F1", "F_base"]},
        "models": [{"name": "ridge", "params": {"alpha": 2.0}}, {"name": "dummy", "params": {}}],
        "validation": {"n_splits": 2},
        "seed": 17,
        "output": "run",
    }
    monkeypatch.setattr(config_module, "load_config", lambda _: {"effective_config": effective})
    return tmp_path, docs, effective, catalogs


def test_custom_folds_vocab_scaling_and_oof(experiment, monkeypatch):
    path, docs, config, catalogs = experiment
    fitted_scalers = []
    original_fit = StandardScaler.fit

    def capture(self, X, y=None, **kwargs):
        result = original_fit(self, X, y, **kwargs)
        fitted_scalers.append((self.mean_.copy(), self.n_samples_seen_))
        return result

    monkeypatch.setattr(StandardScaler, "fit", capture)
    report, fitted = run_configured(path / "config.yaml")
    records = {r["record_id"]: r for r in docs["snapshot"]["content"]["records"]}
    assert set(fitted) == {(f, m) for f in config["features"]["sets"] for m in ("ridge", "dummy")}
    assert fitted["F_base", "ridge"][1].named_steps["ridge"].alpha == 2
    seen = []
    for fold in report["fold_details"]:
        train = [records[i]["payload"] for i in fold["training_record_ids"]]
        hold = [records[i]["payload"] for i in fold["held_out_record_ids"]]
        assert not {p["source"]["doi"] for p in train} & {p["source"]["doi"] for p in hold}
        seen.extend(fold["held_out_record_ids"])
        for feature in config["features"]["sets"]:
            transform = (
                R1Features.fit(train, feature)
                if feature == "F_base"
                else EnhancedFeatures.fit(
                    train, feature, properties=catalogs[0], species=catalogs[1]
                )
            )
            vocab = transform.vocabulary if feature == "F_base" else transform.base.vocabulary
            assert fold["features"][feature]["vocabulary"] == [list(k) for k in vocab]
            assert not {("compound", "X" + str(int(i))) for i in fold["held_out_record_ids"]} & set(
                vocab
            )
            matrix = np.asarray([transform.transform_one(p)["values"] for p in train])
            mean, count = fitted_scalers.pop(0)
            np.testing.assert_allclose(mean, matrix.mean(axis=0))
            assert count == len(train)
    train_ids = docs["selection"]["content"]["retained"]["train"]
    assert sorted(seen) == sorted(train_ids)
    for feature in config["features"]["sets"]:
        for model in ("dummy", "ridge"):
            rows = report["oof_predictions"][feature][model]
            assert sorted(r["record_id"] for r in rows) == sorted(train_ids)
            assert report["oof_scores"][feature][model] == _score(rows)


def test_custom_ties_single_model_and_holdout_isolation(experiment):
    path, docs, config, _ = experiment
    for record in docs["snapshot"]["content"]["records"]:
        record["payload"]["observations"][0]["value"]["normalized_value"] = 15
    snapshot_path = path / "snapshot.json"
    snapshot_path.write_text(json.dumps(docs["snapshot"]), encoding="utf-8")
    report, _ = run_configured(path / "config.yaml")
    assert report["selected"] == {"feature_set": "F_base", "model": "dummy"}
    config["output"] = "single"
    config["models"] = [config["models"][0]]
    single, fitted = run_configured(path / "config.yaml")
    assert single["selected"] == {"feature_set": "F_base", "model": "ridge"}
    assert len(fitted) == 3
    for part in ("validation", "test"):
        for record in docs["snapshot"]["content"]["records"]:
            if record["record_id"] in docs["selection"]["content"]["retained"][part]:
                record["payload"]["observations"][0]["value"]["normalized_value"] += 30
    snapshot_path.write_text(json.dumps(docs["snapshot"]), encoding="utf-8")
    config["output"] = "changed"
    changed, _ = run_configured(path / "config.yaml")
    assert changed["selected"] == single["selected"]
    assert changed["oof_predictions"] == single["oof_predictions"]
    assert changed["oof_scores"] == single["oof_scores"]
    assert changed["validation"] != single["validation"]
    assert changed["test"] != single["test"]


def test_oof_paper_weight_is_not_fold_or_record_weight():
    rows = [
        {"doi": "a", "observed": 0, "raw_prediction": 1},
        {"doi": "a", "observed": 0, "raw_prediction": 1},
        {"doi": "b", "observed": 0, "raw_prediction": 7},
    ]
    assert _score(rows)["paper_equal_mae"] == 4
    assert _score(rows)["mae"] == 3


def test_s2_package_roundtrip_and_tampering(experiment):
    from catalyst_ai.modeling.predictor import load_package, predict_batch, save_package
    from catalyst_ai.reporting.evidence import digest

    path, _, _, catalogs = experiment
    catalogs[0]["sha256"] = "properties"
    catalogs[1]["sha256"] = "species"
    report, fitted = run_configured(path / "config.yaml")
    report["binding"].update(property_sha256="properties", mapping_sha256="species")
    report["selected"] = {"feature_set": "F2", "model": "ridge"}
    report["content_sha256"] = digest({k: v for k, v in report.items() if k != "content_sha256"})
    saved = save_package(path / "package", report, fitted)
    package = load_package(path / "package")
    assert package[0] == saved
    item = {
        "components": [{"role": "compound", "species": "X0", "mol_pct": 100}],
        "temperature_k": 500,
        "pressure_bar_abs": 1,
        "h2_co2_ratio": 3,
        "reactants_flow_nl_g_h": 100,
    }
    assert predict_batch(package, [item, {}])[1]["status"] == "invalid_input"
    model_path = path / "package" / "model.pkl"
    model_path.write_bytes(model_path.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="model hash"):
        load_package(path / "package")


@pytest.mark.parametrize("feature", ["F1", "F2"])
def test_enhanced_prediction_boundaries(experiment, feature):
    from copy import deepcopy

    from catalyst_ai.modeling.predictor import predict_batch, predict_one

    path, docs, _, _ = experiment
    _, fitted = run_configured(path / "config.yaml")
    transform, model = fitted[feature, "ridge"]
    from catalyst_ai.features.pipeline import project

    payload = docs["snapshot"]["content"]["records"][0]["payload"]
    row = project(payload)
    item = {
        **row["conditions"],
        "components": [dict(role=r, species=s, mol_pct=a) for (r, s), a in row["amounts"].items()],
    }
    metadata = dict(target_definition="CO2 conversion", model_id="test", feature_set_id=feature)
    package = (metadata, dict(features=transform, model=model))
    result = predict_one(package, item)
    zero = deepcopy(item)
    zero["components"].append(dict(role="compound", species="Unknown", mol_pct=0))
    assert predict_one(package, zero) == result
    unknown = deepcopy(item)
    unknown["components"][0]["species"] = "Unknown"
    rejected = predict_one(package, unknown)
    assert rejected["co2_conversion_pct"] is None
    assert "unsupported_species" in rejected["validation"][0]
    for value in (float("nan"), float("inf"), -1):
        invalid = deepcopy(item)
        invalid["temperature_k"] = value
        response = predict_one(package, invalid)
        assert response["status"] == "invalid_input"
        assert response["co2_conversion_pct"] is None
        json.dumps(response, allow_nan=False)
    outside = deepcopy(item)
    outside["temperature_k"] = 100000
    batch = predict_batch(package, [item, {}, unknown, zero, outside, None])
    assert len(batch) == 6
    assert batch[0] == batch[3] == result
    assert batch[2] == rejected
    assert batch[1]["status"] == batch[5]["status"] == "invalid_input"
    assert batch[4] == predict_one(package, outside)
    assert batch[4]["out_of_range"]
    json.dumps(batch, allow_nan=False)

    class Constant:
        def __init__(self, value):
            self.value = value

        def predict(self, values):
            return [self.value]

    for value, status in [(101, "output_out_of_range"), (np.inf, "nonfinite_prediction")]:
        output = predict_one((metadata, dict(features=transform, model=Constant(value))), item)
        assert output["status"] == status
        assert output["co2_conversion_pct"] is None
        assert output["raw_prediction"] == (101 if value == 101 else None)
        json.dumps(output, allow_nan=False)
    caution = predict_one((metadata, dict(features=transform, model=Constant(20))), outside)
    assert caution["status"] == "caution"


@pytest.mark.parametrize(
    "kind", ["binding", "catalog", "mapping", "vocabulary", "identity", "dependency"]
)
def test_s2_rejects_rebound_package(experiment, kind):
    import hashlib
    import pickle

    from catalyst_ai.modeling.predictor import load_package, save_package
    from catalyst_ai.reporting.evidence import digest

    path, _, _, catalogs = experiment
    catalogs[0]["sha256"] = "properties"
    catalogs[1]["sha256"] = "species"
    report, fitted = run_configured(path / "config.yaml")
    report["binding"].update(property_sha256="properties", mapping_sha256="species")
    report["content_sha256"] = digest({k: v for k, v in report.items() if k != "content_sha256"})
    directory = path / "package"
    metadata = save_package(directory, report, fitted, candidate=("F2", "ridge"))
    if kind == "binding":
        metadata["binding"]["property_sha256"] = "replacement"
    elif kind in ("catalog", "mapping"):
        data = pickle.loads((directory / "model.pkl").read_bytes())
        if kind == "catalog":
            data["features"].properties["catalog"]["entries"][0]["value"] = 77
        else:
            data["features"].species["catalog"]["entries"][0]["species"] = "replacement"
        blob = pickle.dumps(data, protocol=4)
        (directory / "model.pkl").write_bytes(blob)
        metadata["artifact_sha256"] = hashlib.sha256(blob).hexdigest()
    elif kind == "vocabulary":
        data = pickle.loads((directory / "model.pkl").read_bytes())
        data["features"].base.vocabulary = []
        (directory / "model.pkl").write_bytes(pickle.dumps(data, protocol=4))
    elif kind == "identity":
        metadata["feature_set_id"] = "F1"
    else:
        metadata["dependencies"]["numpy"] = "0"
    metadata["model_id"] = "s2-" + digest({k: v for k, v in metadata.items() if k != "model_id"})
    (directory / "manifest.json").write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="mismatch"):
        load_package(directory)


def test_existing_outputs_are_not_overwritten(experiment):
    import hashlib

    from catalyst_ai.modeling.predictor import save_package

    path, _, _, catalogs = experiment
    catalogs[0]["sha256"] = "properties"
    catalogs[1]["sha256"] = "species"
    report, fitted = run_configured(path / "config.yaml")
    run_file = path / "run" / "report.json"
    before = hashlib.sha256(run_file.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        run_configured(path / "config.yaml")
    assert hashlib.sha256(run_file.read_bytes()).hexdigest() == before
    package = path / "package"
    save_package(package, report, fitted, candidate=("F_base", "ridge"))
    before = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in package.iterdir()}
    with pytest.raises(FileExistsError):
        save_package(package, report, fitted, candidate=("F_base", "ridge"))
    assert {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in package.iterdir()} == before
