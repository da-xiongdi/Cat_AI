"""Replay S2 engineering delivery; optionally register S2-06 then S2-02 acceptance."""

import argparse
import hashlib
import json
import math
import sqlite3
import subprocess
import sys
import uuid
import zipfile
from collections import Counter
from copy import deepcopy
from pathlib import Path

import yaml

from catalyst_ai.features.pipeline import project
from catalyst_ai.modeling.config import load_config
from catalyst_ai.modeling.experiments import run_configured
from catalyst_ai.modeling.predictor import load_package, predict_batch, save_package
from catalyst_ai.reporting.evidence import digest
from catalyst_ai.workbench import backup, index, service

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf8"
    )


def register(database, target, tag):
    evidence_id = "S2-integration-" + tag
    index.register(
        database,
        "cat-ai",
        evidence_id,
        "attachment",
        target.relative_to(ROOT).as_posix(),
        request_id="evidence-" + tag,
        actor="Codex",
    )
    index.scan(database, "cat-ai")
    result = {}
    for task_id in ("S2-06", "S2-02"):
        task = service.get_task(database, task_id)
        for state in ("ready", "in_progress"):
            if task["status"] == ("planned" if state == "ready" else "ready"):
                service.transition(
                    database,
                    task_id,
                    task["revision"],
                    state,
                    request_id=task_id + state + tag,
                    actor="Codex",
                )
                task = service.get_task(database, task_id)
        assert task["status"] == "in_progress", task["status"]
        results = [
            dict(
                criterion_id=c["criterion_id"],
                passed=True,
                evidence_id=evidence_id,
                evidence_version=sha(target),
                explanation="See criterion mapping and replay evidence.",
            )
            for c in task["criteria"]
        ]
        service.submit_review(
            database,
            task_id,
            task["revision"],
            results,
            "Engineering replay and regression passed; no S3 research claim.",
            request_id=task_id + "submit" + tag,
            actor="Codex",
        )
        task = service.get_task(database, task_id)
        service.accept_review(
            database,
            task_id,
            task["revision"],
            "Accepted engineering delivery only.",
            request_id=task_id + "accept" + tag,
            actor="Codex",
        )
        task = service.get_task(database, task_id)
        result[task_id] = {k: task[k] for k in ("status", "revision", "criteria_version")}
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--register", action="store_true", help="register after backup and rehearsal"
    )
    args = parser.parse_args()
    tag = "20261118-" + uuid.uuid4().hex[:8]
    out = ROOT / "artifacts/reports" / ("s2-02-acceptance-" + tag)
    out.mkdir(parents=True)

    def command(name, arguments, success=True):
        result = subprocess.run(
            [sys.executable, *arguments],
            cwd=ROOT,
            capture_output=True,
            encoding="utf8",
            errors="replace",
            timeout=300,
        )
        (out / (name + ".log")).write_text(result.stdout + result.stderr, encoding="utf8")
        assert (result.returncode == 0) == success, name + ": " + result.stderr
        return result.stdout

    protected = [ROOT / "data/catalog.sqlite"]
    for folder in ("data/raw", "data/snapshots", "artifacts/models", "artifacts/runs"):
        protected.extend(p for p in (ROOT / folder).rglob("*") if p.is_file())
    before = {p.relative_to(ROOT).as_posix(): sha(p) for p in protected}
    code = [ROOT / "pyproject.toml"]
    for folder in ("src", "scripts", "tests", "configs"):
        code.extend(
            p
            for p in (ROOT / folder).rglob("*")
            if p.is_file() and p.suffix in (".py", ".yaml", ".json")
        )
    code_hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in code}
    write(out / "code_hashes.json", code_hashes)
    with zipfile.ZipFile(out / "code.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in code:
            archive.write(path, path.relative_to(ROOT))
    command("catalog", ["scripts/validate_training_config.py", "--catalog"])
    command("schema", ["scripts/validate_training_config.py", "--schema"])
    for script in ("train_s2", "predict_r1", "validate_training_config"):
        command(script + "-help", ["scripts/" + script + ".py", "--help"])
    runs = {}
    for name in ("baseline", "custom", "single"):
        template = "baseline" if name == "baseline" else "custom"
        config = yaml.safe_load((ROOT / f"configs/s2_{template}.example.yaml").read_text("utf8"))
        config["dataset"] = {
            k: str((ROOT / "configs" / v).resolve()) for k, v in config["dataset"].items()
        }
        if name == "single":
            config["models"] = [{"name": "ridge", "params": {"alpha": 3.0}}]
        config["output"] = str(out / (name + "-run"))
        config_path = out / (name + ".yaml")
        config_path.write_text(yaml.safe_dump(config), encoding="utf8")
        load_config(config_path)
        command(
            name + "-validate",
            ["scripts/validate_training_config.py", "--validate", str(config_path)],
        )
        package_path = out / (name + "-package")
        if name == "single":
            report, fitted = run_configured(config_path)
            metadata = save_package(package_path, report, fitted)
            transform, model = fitted["F2", "ridge"]
        else:
            arguments = [
                "scripts/train_s2.py",
                "--config",
                str(config_path),
                "--package",
                str(package_path),
            ]
            if name == "custom":
                arguments += ["--candidate", "F2", "ridge"]
            command(name + "-train", arguments)
            report = read(out / (name + "-run/report.json"))
            metadata, fitted = load_package(package_path)
            transform, model = fitted["features"], fitted["model"]
        assert report["content_sha256"] == digest(
            {k: v for k, v in report.items() if k != "content_sha256"}
        )
        package = load_package(package_path)
        snapshot = read(Path(config["dataset"]["snapshot"]))
        records = {r["record_id"]: r["payload"] for r in snapshot["content"]["records"]}
        ids = report["selection"]["content"]["retained"]["validation"]
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
        expected = predict_batch((metadata, dict(features=transform, model=model)), items)
        assert expected == predict_batch(package, items)
        candidates = report["validation"]["candidates"]
        rows = {
            r["record_id"]: r
            for r in candidates[metadata["feature_set_id"] + "/" + metadata["model_name"]][
                "predictions"
            ]
        }
        differences = []
        for rid, prediction in zip(ids, expected, strict=True):
            if prediction["raw_prediction"] is not None:
                actual, trained = prediction["raw_prediction"], rows[rid]["raw_prediction"]
                assert math.isclose(actual, trained, rel_tol=1e-12, abs_tol=1e-12)
                differences.append(abs(actual - trained))
        usable = next(
            item for item, result in zip(items, expected, strict=True) if result["status"] == "ok"
        )
        zero = deepcopy(usable)
        zero["components"].append(dict(role="compound", species="Unknown", mol_pct=0))
        unknown = deepcopy(usable)
        unknown["components"][0]["species"] = "Unknown"
        outside = deepcopy(usable)
        outside["temperature_k"] = 100000
        mixed = [usable, {}, unknown, zero, outside, None]
        for label, inputs in (("single", usable), ("batch", mixed), ("validation", items)):
            input_path = out / (name + "-" + label + "-input.json")
            write(input_path, inputs)
            output = json.loads(
                command(
                    name + "-" + label,
                    [
                        "scripts/predict_r1.py",
                        "--package",
                        str(package_path),
                        "--input",
                        str(input_path),
                    ],
                )
            )
            python_output = (
                predict_batch(package, inputs)
                if isinstance(inputs, list)
                else predict_batch(package, [inputs])[0]
            )
            assert output == json.loads(json.dumps(python_output, allow_nan=False))
        results = predict_batch(package, mixed)
        assert results[0] == results[3]
        assert results[1]["status"] == results[5]["status"] == "invalid_input"
        assert results[2]["co2_conversion_pct"] is None and results[4]["out_of_range"]
        runs[name] = dict(
            training_prediction_max_abs_difference=max(differences, default=0),
            model_id=metadata["model_id"],
            selected=report["selected"],
            packaged=[metadata["feature_set_id"], metadata["model_name"]],
            report_sha256=report["content_sha256"],
            validation_statuses=dict(Counter(r["status"] for r in expected)),
            mixed_statuses=[r["status"] for r in results],
        )
        command(
            name + "-reject-overwrite",
            ["scripts/validate_training_config.py", "--validate", str(config_path)],
            success=False,
        )
    assert len({r["model_id"] for r in runs.values()}) == 3
    old = ROOT / "artifacts/reports/themecat-r1-prediction-20261112-final"
    replay = json.loads(
        command(
            "r1-replay",
            [
                "scripts/predict_r1.py",
                "--package",
                "artifacts/models/themecat-r1-prediction-20261112-final",
                "--input",
                str(old / "validation-input.json"),
            ],
        )
    )
    assert replay == read(old / "validation-predictions.json")
    command("pytest", ["-m", "pytest", "-q", "--junitxml=" + str(out / "tests.xml")])
    command("ruff", ["-m", "ruff", "check", "src", "tests", "scripts"])
    command("format", ["-m", "ruff", "format", "--check", "src", "tests", "scripts"])
    assert before == {p.relative_to(ROOT).as_posix(): sha(p) for p in protected}
    assert code_hashes == {p.relative_to(ROOT).as_posix(): sha(p) for p in code}
    evidence = dict(
        scope="S2 engineering acceptance; no S3 formal comparison or MAE threshold",
        runs=runs,
        r1_replay_records=len(replay),
        protected_unchanged=True,
        protected_hashes=before,
        code_hashes=code_hashes,
        criteria={
            "S2-06/C1": "run manifests, single alpha=3 vs custom alpha=2; R1 replay",
            "S2-06/C2": "validation predictions within 1e-12; test_s2_rejects_rebound_package",
            "S2-06/C3": "mixed CLI batches; test_enhanced_prediction_boundaries",
            "S2-02/C1": "baseline/custom CLI and single Python replay; independent directories",
            "S2-02/C2": "help/catalog/schema, JSON CLI; config/prediction regression; R1 replay",
            "S2-02/C3": "pytest.log, ruff.log, format.log, code.zip, code_hashes.json",
        },
        limitations=[
            "Historical test only",
            "Source acceptance is not row verification",
            "Pressure assumed absolute",
        ],
    )
    evidence["files"] = {
        p.relative_to(out).as_posix(): sha(p) for p in out.rglob("*") if p.is_file()
    }
    write(out / "acceptance.json", evidence)
    if args.register:
        database = ROOT / "data/workbench.sqlite"
        backup.backup_database(database, out / "before.sqlite")
        backup.backup_database(database, out / "rehearsal.sqlite")
        rehearsed = register(out / "rehearsal.sqlite", out / "acceptance.json", tag)
        actual = register(database, out / "acceptance.json", tag)
        assert actual == rehearsed
        backup.backup_database(database, out / "after.sqlite")
        write(out / "registration.json", actual)
    print(str(out))


if __name__ == "__main__":
    main()
