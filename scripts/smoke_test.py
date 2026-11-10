"""Run installed CLI commands against an isolated synthetic_demo database."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from catalyst_ai.config import Settings
from catalyst_ai.reporting.evidence import metadata, now, write_json


def run_smoke():
    root = Path(__file__).resolve().parents[1]
    steps = []
    with TemporaryDirectory(prefix="catalyst-ai-synthetic-demo-") as temp:
        directory = Path(temp)
        settings = Settings(
            database=directory / "data/catalog.sqlite",
            data_dir=directory / "data",
            report_dir=directory / "reports",
        )
        config = directory / "project.yaml"
        config.write_text(yaml.safe_dump(settings.model_dump(mode="json")), encoding="utf-8")
        prefix = [sys.executable, "-m", "catalyst_ai.cli", "--config", str(config)]

        def call(arguments, expected=0):
            result = subprocess.run(
                [*prefix, *arguments], capture_output=True, text=True, encoding="utf-8", cwd=root
            )
            if result.returncode != expected:
                raise AssertionError(
                    f"{arguments}: expected {expected}, got {result.returncode}\n"
                    + result.stdout
                    + result.stderr
                )
            steps.append(
                {
                    "arguments": arguments,
                    "expected_exit": expected,
                    "actual_exit": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )
            return json.loads(result.stdout) if result.stdout else None

        csv_path = str(root / "data/examples/synthetic_demo.csv")
        json_path = str(root / "data/examples/synthetic_demo.json")
        call(["status"])
        call(["ingest", "--input", csv_path, "--source", "literature", "--dry-run"])
        assert not settings.database.exists()
        call(["init"])
        call(["init"])
        imported = call(["ingest", "--input", csv_path, "--source", "literature"])
        assert imported["counts"]["curated"] == 1
        call(
            [
                "validate",
                "--run-id",
                imported["run_id"],
                "--report",
                str(directory / "quality.json"),
            ]
        )
        call(["ingest", "--input", json_path], expected=2)
        call(["batch", "check"])
        call(["batch", "check", "--capacity", "6", "--candidate-id", "synthetic_demo-slot"])
        call(["batch", "check", "--capacity", "7"], expected=1)
        call(
            ["batch", "check", *sum((["--candidate-id", f"demo-{i}"] for i in range(5)), [])],
            expected=1,
        )
        call(["dataset", "build", "--target", "co2_conversion"], expected=1)
        call(["dataset", "build", "--target", "co2_conversion", "--demo"], expected=1)
        definition = json.loads(Path(json_path).read_text(encoding="utf-8"))[0]["observations"][0][
            "value"
        ]["definition"]
        qualify = [
            "dataset",
            "qualify",
            "--target",
            "co2_conversion",
            "--record-id",
            imported["rows"][0]["record_id"],
            "--target-definition",
            definition,
            "--target-unit",
            "%",
            "--demo",
        ]
        eligibility = call(qualify, expected=2)
        assert eligibility["content"]["status"] == "empty"
        assert eligibility["content"]["records"][0]["reason_codes"] == ["not_reviewed"]
        call([*qualify, "--freeze"], expected=1)
        status = call(["status"])
        assert status["verified_research"] == 0
        return {
            "created_at": now(),
            "dataset_kind": "synthetic_demo",
            "result": "passed",
            "steps_passed": len(steps),
            "steps": steps,
            "metadata": metadata(settings),
            "notes": "Isolated temporary database removed. No review approvals were created.",
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_smoke()
    if args.output:
        write_json(args.output, report)
    print(f"synthetic_demo CLI smoke: {report['steps_passed']} steps passed")


if __name__ == "__main__":
    main()
