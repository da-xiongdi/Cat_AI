import json

import numpy as np
import pytest
from test_experiments import prepared

from catalyst_ai.modeling.experiments import compare_r1
from catalyst_ai.modeling.predictor import load_package, predict_batch, predict_one, save_package


def test_package_roundtrip_and_failures(sample, tmp_path):
    snapshot, qualification, split = prepared(sample)
    report, fitted = compare_r1(snapshot, qualification, split)
    directory = tmp_path / "package"
    metadata = save_package(directory, report, fitted)
    package = load_package(directory)
    record_id = report["selection"]["content"]["retained"]["train"][0]
    record = next(r for r in snapshot["content"]["records"] if r["record_id"] == record_id)
    from catalyst_ai.features.pipeline import project

    row = project(record["payload"])
    item = {
        **row["conditions"],
        "components": [
            {"role": role, "species": species, "mol_pct": amount}
            for (role, species), amount in row["amounts"].items()
        ],
    }
    result = predict_one(package, item)
    expected = fitted["model"].predict(
        [fitted["features"].transform_one(record["payload"])["values"]]
    )[0]
    assert result["co2_conversion_pct"] == pytest.approx(expected)
    assert result["model_id"] == metadata["model_id"]
    assert predict_batch(package, [item, {}])[1]["status"] == "invalid_input"
    item["components"][0]["species"] = "Unseen"
    assert predict_one(package, item)["status"] == "unsupported_species_role"
    item["components"][0]["species"] = next(iter(row["amounts"]))[1]

    class Model:
        def __init__(self, value):
            self.value = value

        def predict(self, values):
            return np.array([self.value])

    for value, status in [(101, "output_out_of_range"), (float("nan"), "nonfinite_prediction")]:
        result = predict_one(
            (metadata, {"features": fitted["features"], "model": Model(value)}), item
        )
        assert result["status"] == status
        assert result["co2_conversion_pct"] is None
        json.dumps(result, allow_nan=False)
    (directory / "model.pkl").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_package(directory)
