import json
import os
import subprocess
import sys
from pathlib import Path

from catalyst_ai.modeling.research_preflight import preflight

ROOT = Path(__file__).resolve().parents[2]


def test_configured_split_plan_and_projection(tmp_path):
    plan = json.loads((ROOT / "configs/research_plan_example.json").read_text(encoding="utf-8"))
    plan.update(seeds=[51, 52], train_fraction=0.75, folds=3)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    output = tmp_path / "outputs"
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/configure_research_experiments.py"),
            str(plan_path),
            "--output",
            str(output),
        ],
        check=True,
        cwd=ROOT,
        env=env,
    )
    for seed in (51, 52):
        checks = [
            preflight(output / "configs" / f"{name}-{seed}.json", root=ROOT)
            for name in ("EXP-01", "EXP-02", "EXP-03")
        ]
        assert all(len(c["split"]["validation_folds"]) == 3 for c in checks)
        cu = set(checks[2]["view"]["content"]["common_record_ids"])
        assert set(checks[1]["split"]["test"]) & cu == set(checks[2]["split"]["test"])


def test_generic_dataset_plan(tmp_path):
    example = json.loads(
        (ROOT / "configs/research_preflight_example.json").read_text(encoding="utf-8")
    )
    plan = {
        "dataset": {k: example[k] for k in ("view", "snapshot", "target")},
        "strategy": "doi",
        "seeds": [11],
        "folds": 3,
        "candidates": [{"feature": "F_base", "model": "dummy"}],
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    output = tmp_path / "generic"
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/configure_research_experiments.py"),
            str(path),
            "--output",
            str(output),
        ],
        check=True,
        cwd=ROOT,
        env=env,
    )
    checked = preflight(output / "configs/run-11.json", root=ROOT)
    assert checked["split"]["strategy"] == "doi"
    assert checked["counts"]["train"] + checked["counts"]["test"] == 542
