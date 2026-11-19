import json
import math
import subprocess
import sys
from pathlib import Path

import yaml

from catalyst_ai.features.pipeline import project
from catalyst_ai.modeling.config import load_config
from catalyst_ai.modeling.experiments import run_configured
from catalyst_ai.modeling.predictor import load_package, predict_batch, predict_one, save_package

root = Path.cwd()
out = root / "artifacts/reports/s3-02-20261118-02a"
out.mkdir(parents=True, exist_ok=True)


def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))


def write(p, x):
    Path(p).write_text(
        json.dumps(x, ensure_ascii=False, indent=2, allow_nan=False, default=str), encoding="utf8"
    )


base = yaml.safe_load((root / "configs/s2_custom.example.yaml").read_text(encoding="utf8"))
base["dataset"] = {k: str((root / "configs" / v).resolve()) for k, v in base["dataset"].items()}
configs = {}
for name in ("multi", "single"):
    c = yaml.safe_load(yaml.safe_dump(base))
    c["output"] = str(root / f"artifacts/runs/s3-20261118-02a/{name}")
    if name == "single":
        c["models"] = [{"name": "ridge", "params": {"alpha": 3.0}}]
    p = root / f"configs/s3_20261118_02a_{name}.yaml"
    p.write_text(yaml.safe_dump(c, sort_keys=False), encoding="utf8")
    if not Path(c["output"]).exists():
        load_config(p)
    configs[name] = p
pkgroot = root / "artifacts/models/s3-20261118-02a"
pkgroot = root / "artifacts/models/s3-20261118-02a"
if not (pkgroot / "single" / "manifest.json").exists():
    cmd = [
        sys.executable,
        "scripts/train_s2.py",
        "--config",
        str(configs["multi"]),
        "--package",
        str(pkgroot / "multi"),
        "--candidate",
        "F2",
        "ridge",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf8")
    (out / "multi-train.log").write_text(r.stdout + r.stderr, encoding="utf8")
    if r.returncode:
        raise RuntimeError("multi training failed")
    report, fitted = run_configured(configs["single"])
    meta = save_package(pkgroot / "single", report, fitted, candidate=("F2", "ridge"))
    assert (
        predict_batch(
            (meta, {"features": fitted["F2", "ridge"][0], "model": fitted["F2", "ridge"][1]}), []
        )
        == []
    )

scenarios = [
    ("formal-r2", "artifacts/runs/s3-20261118-01/r2", "artifacts/models/s3-20261118-01/r2"),
    ("formal-r1", "artifacts/runs/s3-20261118-01/r1", "artifacts/models/s3-20261118-01/r1"),
    (
        "formal-f1",
        "artifacts/runs/s3-20261118-01/r2",
        "artifacts/models/s3-20261118-01/r2-f1-ridge",
    ),
    ("multi", "artifacts/runs/s3-20261118-02a/multi", str(pkgroot / "multi")),
    ("single", "artifacts/runs/s3-20261118-02a/single", str(pkgroot / "single")),
]
snapshot = read(base["dataset"]["snapshot"])
records = {r["record_id"]: r["payload"] for r in snapshot["content"]["records"]}
results = {}
for name, run, path in scenarios:
    rep = read(root / run / "report.json")
    meta, obj = load_package(root / path)
    assert meta["report_sha256"] == rep["content_sha256"]
    ids = rep["selection"]["content"]["retained"]["validation"]
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
    pred = predict_batch((meta, obj), items)
    assert pred == [predict_one((meta, obj), x) for x in items]
    key = meta["feature_set_id"] + "/" + meta["model_name"]
    rows = {x["record_id"]: x for x in rep["validation"]["candidates"][key]["predictions"]}
    checks = []
    for rid, p in zip(ids, pred, strict=True):
        row = rows[rid]
        if p["raw_prediction"] is not None:
            assert math.isclose(
                p["raw_prediction"], row["raw_prediction"], rel_tol=1e-12, abs_tol=1e-12
            )
        checks.append({"record_id": rid, "prediction": p, "training_row": row})
    inp = out / (name + "-input.json")
    write(inp, items)
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/predict_r1.py",
            "--package",
            str(root / path),
            "--input",
            str(inp),
        ],
        capture_output=True,
        text=True,
        encoding="utf8",
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr)
    assert json.loads(proc.stdout) == json.loads(json.dumps(pred, allow_nan=False))
    write(out / (name + "-checks.json"), checks)
    results[name] = {
        "run": str(run),
        "package": str(path),
        "selected": rep["selected"],
        "packaged": key,
        "model_id": meta["model_id"],
        "parameters": obj["model"].get_params(),
        "validation_count": len(ids),
    }
old = root / "artifacts/reports/themecat-r1-prediction-20261112-final"
r = subprocess.run(
    [
        sys.executable,
        "scripts/predict_r1.py",
        "--package",
        "artifacts/models/themecat-r1-prediction-20261112-final",
        "--input",
        str(old / "validation-input.json"),
    ],
    capture_output=True,
    text=True,
    encoding="utf8",
)
assert r.returncode == 0 and json.loads(r.stdout) == read(old / "validation-predictions.json")
results["historical-r1"] = {
    "package": "artifacts/models/themecat-r1-prediction-20261112-final",
    "input": str(old / "validation-input.json"),
    "matches": True,
}
write(out / "scenarios.json", results)
print("completed", out)
