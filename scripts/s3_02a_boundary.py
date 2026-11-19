"""Check F1/F2 boundary behavior and fitted multi-model parameters."""

import copy
import json
from pathlib import Path

import yaml

from catalyst_ai.modeling.config import load_config
from catalyst_ai.modeling.experiments import run_configured
from catalyst_ai.modeling.predictor import load_package, predict_batch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/reports/s3-02-20261118-02a"
results = {}
for name in ("formal-f1", "multi"):
    scenario = json.loads((OUT / "scenarios.json").read_text(encoding="utf8"))[name]
    package = load_package(ROOT / scenario["package"])
    items = json.loads((OUT / f"{name}-input.json").read_text(encoding="utf8"))
    valid = next(
        item
        for item, pred in zip(items, predict_batch(package, items), strict=True)
        if pred["status"] == "ok"
    )
    unknown = copy.deepcopy(valid)
    unknown["components"][0]["species"] = "Unknown"
    zero = copy.deepcopy(valid)
    zero["components"].append({"role": "compound", "species": "Unknown", "mol_pct": 0})
    outside = copy.deepcopy(valid)
    outside["temperature_k"] = 100000
    predictions = predict_batch(package, [valid, unknown, zero, outside])
    assert predictions[0] == predictions[2]
    assert predictions[1]["status"] == "invalid_input"
    assert predictions[1]["validation"] == ["unsupported_species:Unknown"]
    assert predictions[1]["co2_conversion_pct"] is None
    assert predictions[3]["out_of_range"]
    results[name] = {"inputs": [valid, unknown, zero, outside], "predictions": predictions}

cfg = yaml.safe_load((ROOT / "configs/s3_20261118_02a_multi.yaml").read_text(encoding="utf8"))
cfg["output"] = str(ROOT / "artifacts/runs/s3-20261118-02a/multi-parameters")
path = ROOT / "configs/s3_20261118_02a_multi_parameters.yaml"
assert not path.exists()
path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf8")
load_config(path)
report, fitted = run_configured(path)
ridge = fitted["F2", "ridge"][1].get_params()["ridge__alpha"]
trees = fitted["F2", "extra_trees"][1].get_params()
assert ridge == 2.0 and trees["n_estimators"] == 80 and trees["n_jobs"] == 1
results["multi-fitted-parameters"] = {
    "config": str(path.relative_to(ROOT)),
    "run": str(Path(cfg["output"]).relative_to(ROOT)),
    "selected": report["selected"],
    "ridge_alpha": ridge,
    "extra_trees": {
        k: trees[k]
        for k in (
            "n_estimators",
            "n_jobs",
            "min_samples_leaf",
            "max_depth",
            "max_features",
            "random_state",
        )
    },
}
(OUT / "boundary-and-parameters.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf8"
)
print("boundary and fitted parameters verified")
