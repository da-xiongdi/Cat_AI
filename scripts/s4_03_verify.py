"""Archive reproducible S4-03 checks without running formal comparisons."""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from catalyst_ai.features.pipeline import project
from catalyst_ai.modeling.predictor import load_package, predict_one
from catalyst_ai.modeling.research_preflight import preflight
from catalyst_ai.modeling.research_run import environment
from catalyst_ai.reporting.evidence import write_json

ROOT = Path(__file__).resolve().parents[1]
TESTS = [
    "tests/unit/test_research_plan.py",
    "tests/unit/test_research_run.py",
    "tests/unit/test_research_preflight.py",
    "tests/unit/test_research_split.py",
    "tests/unit/test_research_repeat_contract.py",
    "tests/integration/test_research_end_to_end.py",
    "tests/unit/test_predictor.py",
    "tests/unit/test_s2_experiments.py",
]


def verify(output):
    output.mkdir(parents=True, exist_ok=False)
    result = {
        "scope": "functional validation only; no S4-04 formal comparison",
        "environment": environment(),
    }
    try:
        check = subprocess.run(
            [sys.executable, "-m", "pytest", *TESTS, "-q"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        (output / "pytest.log").write_text(check.stdout + check.stderr, encoding="utf-8")
        if check.returncode:
            raise ValueError("functional tests failed")
        result["pytest"] = {"exit_code": check.returncode, "tests": TESTS}
        directory = ROOT / "artifacts/reports/s4-03-frozen-20261120-v2"
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "coverage.json"
            check = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/s4_03_verify_splits.py"),
                    "--directory",
                    str(directory),
                    "--output",
                    str(out),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            if check.returncode or json.loads(out.read_text(encoding="utf-8")) != json.loads(
                (directory / "coverage.json").read_text(encoding="utf-8")
            ):
                raise ValueError("split coverage replay mismatch: " + check.stderr)
        result["coverage_replay"] = "content-identical"
        result["frozen_config_counts"] = {
            p.stem: preflight(p, root=ROOT)["counts"]
            for p in sorted((directory / "configs").glob("*.json"))
        }
        if len(result["frozen_config_counts"]) != 9:
            raise ValueError("expected nine frozen configurations")
        result["preflight_counts"] = preflight(
            ROOT / "configs/research_preflight_example.json", root=ROOT
        )["counts"]
        snapshot_path = (
            ROOT
            / "data/snapshots"
            / "snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json"
        )
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        result["historical_packages"] = []
        for path in (
            "artifacts/models/themecat-r1-prediction-20261112-final",
            "artifacts/models/s3-20261118-02a/single",
        ):
            package = load_package(ROOT / path)
            for record in snapshot["content"]["records"]:
                try:
                    row = project(record["payload"])
                    item = {
                        **row["conditions"],
                        "components": [
                            {"role": a, "species": b, "mol_pct": c}
                            for (a, b), c in row["amounts"].items()
                        ],
                    }
                    prediction = predict_one(package, item)
                except ValueError:
                    continue
                if prediction["status"] in ("ok", "caution"):
                    result["historical_packages"].append(
                        {
                            "path": path,
                            "model_id": package[0]["model_id"],
                            "record_id": record["record_id"],
                            "status": prediction["status"],
                        }
                    )
                    break
            else:
                raise ValueError("no available prediction from " + path)
        files = [ROOT / p for p in TESTS] + [
            Path(__file__),
            ROOT / "scripts/s4_03_verify_splits.py",
        ]
        result["verification_files"] = {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
        }
        result["result"] = "passed"
    except Exception as error:
        result.update(result="failed", error=str(error))
        write_json(output / "verification.json", result)
        raise
    write_json(output / "verification.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(verify(args.output)["result"])
