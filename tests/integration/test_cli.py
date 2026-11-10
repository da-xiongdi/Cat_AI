import json
import subprocess
import sys

import yaml

from catalyst_ai.cli import main


def test_cli_init_status_and_dry_run(tmp_path, sample, settings, input_file, capsys):
    config = tmp_path / "project.yaml"
    config.write_text(yaml.safe_dump(settings.model_dump(mode="json")), encoding="utf-8")
    prefix = ["--config", str(config)]
    assert main([*prefix, "status"]) == 0
    assert json.loads(capsys.readouterr().out)["database_exists"] is False
    assert main([*prefix, "ingest", "--input", str(input_file([sample])), "--dry-run"]) == 0
    capsys.readouterr()
    assert not settings.database.exists()
    assert main([*prefix, "init"]) == 0
    capsys.readouterr()
    assert main([*prefix, "init"]) == 0
    capsys.readouterr()
    assert main([*prefix, "status"]) == 0
    assert json.loads(capsys.readouterr().out)["counts"]["curated_record"] == 0


def test_cli_report_exit_codes_and_gate(tmp_path, sample, settings, input_file, capsys):
    config = tmp_path / "project.yaml"
    config.write_text(yaml.safe_dump(settings.model_dump(mode="json")), encoding="utf-8")
    prefix = ["--config", str(config)]
    path = input_file([sample])
    assert main([*prefix, "ingest", "--input", str(path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert (
        main(
            [
                *prefix,
                "validate",
                "--run-id",
                report["run_id"],
                "--report",
                str(tmp_path / "quality.json"),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (tmp_path / "quality.txt").exists()
    assert main([*prefix, "ingest", "--input", str(path)]) == 2
    capsys.readouterr()
    assert main([*prefix, "dataset", "build", "--target", "co2_conversion"]) == 1
    assert "synthetic_demo" in capsys.readouterr().err
    assert main([*prefix, "batch", "check", "--capacity", "7"]) == 1
    capsys.readouterr()
    assert main([*prefix, "batch", "check", "--capacity", "6"]) == 0


def test_installed_cli_process_handles_utf8():
    completed = subprocess.run(
        [sys.executable, "-m", "catalyst_ai.cli", "status"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert json.loads(completed.stdout)["scientific_results"] == "无"
