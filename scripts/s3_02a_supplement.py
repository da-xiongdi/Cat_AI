"""Supplement S3-02-A with row-level contract and in-memory replay checks."""

import json
import math
import subprocess
import sys
from collections import Counter
from pathlib import Path

import yaml

from catalyst_ai.features.pipeline import project
from catalyst_ai.modeling.config import load_config
from catalyst_ai.modeling.experiments import run_configured
from catalyst_ai.modeling.predictor import load_package, predict_batch, predict_one, save_package

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/reports/s3-02-20261118-02a"


def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))


def write(p, value):
    Path(p).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf8"
    )


def close(a, b):
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)


summary = {}
for name in ("formal-r2", "formal-r1", "formal-f1", "multi", "single"):
    checks = read(OUT / f"{name}-checks.json")
    assert len(checks) == 47
    statuses = Counter()
    for check in checks:
        row, pred = check["training_row"], check["prediction"]
        training_status = row["status"]
        if "unsupported_species_role" in training_status:
            assert pred["status"] == "unsupported_species_role"
            assert pred["validation"] == ["unsupported_species_role"]
            assert pred["raw_prediction"] is None and pred["co2_conversion_pct"] is None
        else:
            raw = row["raw_prediction"]
            assert close(pred["raw_prediction"], raw)
            if not 0 <= raw <= 100:
                assert pred["status"] == "output_out_of_range"
                assert pred["validation"] == ["output_out_of_range"]
                assert pred["co2_conversion_pct"] is None
            else:
                assert pred["status"] == training_status
                assert pred["validation"] == []
                assert close(pred["co2_conversion_pct"], raw)
        assert pred["unseen_species_roles"] == row["unseen_species_roles"]
        assert pred["out_of_range"] == row["out_of_range"]
        statuses[(training_status, pred["status"])] += 1
    summary[name] = {
        "count": len(checks),
        "status_pairs": [
            {"training": a, "entry": b, "count": n} for (a, b), n in sorted(statuses.items())
        ],
    }
    input_file = OUT / f"{name}-single-input.json"
    item = read(OUT / f"{name}-input.json")[0]
    write(input_file, item)
    package_path = read(OUT / "scenarios.json")[name]["package"]
    package = load_package(ROOT / package_path)
    cmd = [
        sys.executable,
        str(ROOT / "scripts/predict_r1.py"),
        "--package",
        str(ROOT / package_path),
        "--input",
        str(input_file),
    ]
    proc = subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf8", check=True
    )
    assert json.loads(proc.stdout) == json.loads(json.dumps(predict_one(package, item)))

# A new run preserves the earlier run and allows the trained object to be checked before reload.
cfg = yaml.safe_load((ROOT / "configs/s3_20261118_02a_single.yaml").read_text(encoding="utf8"))
cfg["output"] = str(ROOT / "artifacts/runs/s3-20261118-02a/single-reload")
cfg_path = ROOT / "configs/s3_20261118_02a_single_reload.yaml"
assert not cfg_path.exists()
cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf8")
load_config(cfg_path)
report, fitted = run_configured(cfg_path)
package_path = ROOT / "artifacts/models/s3-20261118-02a/single-reload"
metadata = save_package(package_path, report, fitted, candidate=("F2", "ridge"))
ids = report["selection"]["content"]["retained"]["validation"]
snapshot = read(cfg["dataset"]["snapshot"])
records = {r["record_id"]: r["payload"] for r in snapshot["content"]["records"]}
items = []
for rid in ids:
    row = project(records[rid])
    items.append(
        {
            **row["conditions"],
            "components": [
                dict(role=r, species=s, mol_pct=a) for (r, s), a in row["amounts"].items()
            ],
        }
    )
transform, model = fitted["F2", "ridge"]
assert model.get_params()["ridge__alpha"] == 3.0
before = predict_batch((metadata, {"features": transform, "model": model}), items)
after = predict_batch(load_package(package_path), items)
assert before == after
assert len(before) == 47
write(
    OUT / "single-reload-checks.json",
    {
        "config": str(cfg_path.relative_to(ROOT)),
        "run": str(Path(cfg["output"]).relative_to(ROOT)),
        "package": str(package_path.relative_to(ROOT)),
        "model_id": metadata["model_id"],
        "comparisons": [
            {"record_id": rid, "before_reload": a, "after_reload": b}
            for rid, a, b in zip(ids, before, after, strict=True)
        ],
    },
)
summary["single-reload"] = {
    "count": len(before),
    "identical": True,
    "alpha": model.get_params()["ridge__alpha"],
}
write(OUT / "supplement-checks.json", summary)
print(json.dumps(summary, ensure_ascii=False, indent=2))
