from copy import deepcopy

import numpy as np
import pytest
from test_split import inputs, rehash_snapshot

pytest.importorskip("sklearn")

from catalyst_ai.datasets.split import build_paper_split  # noqa: E402
from catalyst_ai.features.design import build_feature_table  # noqa: E402
from catalyst_ai.modeling.baseline import metrics, train_baselines  # noqa: E402


def prepared(sample, test_delta=0, validation_shift=False):
    snapshot, qualification = inputs(sample)
    content = snapshot["content"]
    content.update(
        dataset_kind="synthetic_demo",
        scientific_use=False,
        target_unit="%",
        target_definition="test definition",
    )
    for i, record in enumerate(content["records"]):
        payload = record["payload"]
        payload["recipe"]["composition_scope"] = "whole"
        for component in payload["recipe"]["components"]:
            component["amount"].update(state="reported", normalized_value=20, normalized_unit="%")
        payload["test"]["temperature"].update(
            state="reported", normalized_value=400 + i, normalized_unit="K"
        )
        target = next(o for o in payload["observations"] if o["metric"] == "co2_conversion")
        target["value"].update(
            state="reported",
            normalized_value=10 + i,
            normalized_unit="%",
            definition="test definition",
        )
    rehash_snapshot(snapshot, qualification)
    split = build_paper_split(snapshot, qualification)
    for record in content["records"]:
        if record["record_id"] in split["content"]["splits"]["test"]["record_ids"]:
            record["payload"]["observations"][0]["value"]["normalized_value"] += test_delta
        if (
            validation_shift
            and record["record_id"] in split["content"]["splits"]["validation"]["record_ids"]
        ):
            record["payload"]["test"]["temperature"]["normalized_value"] = 5000
            record["payload"]["recipe"]["components"][0]["species"] = "VALONLY"
    rehash_snapshot(snapshot, qualification)
    split = build_paper_split(snapshot, qualification)
    features = build_feature_table(snapshot, qualification, split)
    return snapshot, qualification, split, features


def test_selection_and_fit_do_not_use_held_out_target(sample):
    args = prepared(sample)
    report, models = train_baselines(*args)
    repeated, _ = train_baselines(*args)
    assert report == repeated
    changed, _ = train_baselines(*prepared(sample, test_delta=1000))
    assert report["model_selection"] == changed["model_selection"]
    assert report["training_features"] == changed["training_features"]
    assert report["metrics"]["dummy"]["test"] != changed["metrics"]["dummy"]["test"]
    assert models["models"]["ridge"].named_steps["simpleimputer"].statistics_[0] < 500
    assert report["scientific_use"] is False


def test_preprocessing_uses_training_distribution_and_vocabulary(sample):
    args = prepared(sample, validation_shift=True)
    report, fitted = train_baselines(*args)
    names = fitted["feature_names"]
    assert not any("VALONLY" in name for name in names)
    temperature_index = names.index("condition:temperature_k")
    train_rows = [r for r in args[3]["content"]["rows"] if r["partition"] == "train"]
    expected = np.median([r["values"]["temperature_k"] for r in train_rows])
    imputer = fitted["models"]["ridge"].named_steps["simpleimputer"]
    assert imputer.statistics_[temperature_index] == expected
    assert report["coverage"]["validation"]["conditions"]["temperature_k"]["range"] == [5000, 5000]


def test_feature_tampering_and_undefined_r2(sample):
    args = list(prepared(sample))
    args[3] = deepcopy(args[3])
    args[3]["content"]["rows"][0]["values"]["temperature_k"] = 9999
    with pytest.raises(ValueError, match="Feature table"):
        train_baselines(*args)
    assert metrics(np.array([1.0, 1.0]), np.array([1.0, 2.0]))["r2"] is None
