"""Build immutable split and run configurations from a research plan JSON."""

import argparse
import json
from pathlib import Path

from s4_01_profile import ROOT
from s4_03_split_draft import main as make_splits

from catalyst_ai.datasets.research_prepare import prepare as prepare_split
from catalyst_ai.modeling.research_preflight import Candidate, ResearchConfig, read_json, sha
from catalyst_ai.reporting.evidence import write_json


def prepare(plan_path, output):
    plan = read_json(plan_path)
    allowed = {
        "seeds",
        "train_fraction",
        "folds",
        "experiments",
        "model_seed",
        "candidates",
        "metrics",
        "outputs",
        "dataset",
        "strategy",
    }
    if set(plan) - allowed:
        raise ValueError("unknown research plan fields")
    seeds = plan.get("seeds", [42, 43, 44])
    dataset = plan.get("dataset")
    experiments = plan.get("experiments", ["EXP-01", "EXP-02", "EXP-03"])
    if not seeds or any(type(s) is not int or s < 0 or s > 4294967295 for s in seeds):
        raise ValueError("invalid seeds")
    if dataset is None and (
        not experiments
        or len(experiments) != len(set(experiments))
        or set(experiments) - {"EXP-01", "EXP-02", "EXP-03"}
    ):
        raise ValueError("invalid experiments")
    candidates = [Candidate.model_validate(c).model_dump() for c in plan["candidates"]]
    if not candidates:
        raise ValueError("empty candidates")
    output = Path(output).resolve()
    if dataset is not None:
        if set(dataset) - {"view", "snapshot", "target", "catalog_database"} or not {
            "view",
            "snapshot",
            "target",
        } <= set(dataset):
            raise ValueError("invalid dataset configuration")
        if "experiments" in plan:
            raise ValueError("use a strategy for generic datasets")
        if len(seeds) != len(set(seeds)):
            raise ValueError("duplicate seeds")
        (output / "splits").mkdir(parents=True, exist_ok=False)
        for seed in seeds:
            split = output / "splits" / f"split-{seed}.json"
            write_json(
                split,
                prepare_split(
                    dataset["view"],
                    dataset["snapshot"],
                    root=ROOT,
                    strategy=plan.get("strategy", "random"),
                    seed=seed,
                    train_fraction=plan.get("train_fraction", 0.8),
                    folds=plan.get("folds", 5),
                ),
            )
            config = {
                "schema_version": 1,
                **dataset,
                "split": str(split),
                "split_sha256": sha(split),
                "candidates": candidates,
                "model_seed": plan.get("model_seed", 42),
                "metrics": plan.get("metrics", ["mae", "rmse", "r2", "availability"]),
                "outputs": plan.get("outputs", ["predictions", "plots"]),
            }
            config = ResearchConfig.model_validate(config).model_dump()
            write_json(output / "configs" / f"run-{seed}.json", config)
        write_json(output / "plan.json", plan)
        return {"configurations": len(seeds), "output": str(output)}
    make_splits(
        output / "splits",
        seeds=seeds,
        train_fraction=plan.get("train_fraction", 0.8),
        folds=plan.get("folds", 5),
    )
    snapshot = (
        "data/snapshots/"
        "snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json"
    )
    for seed in seeds:
        for name in experiments:
            split = output / "splits" / f"{name}-{seed}.json"
            view = "cu" if name == "EXP-03" else "all"
            config = {
                "schema_version": 1,
                "view": f"artifacts/reports/s4-02-20261120-v1/{view}-view.json",
                "snapshot": snapshot,
                "split": str(split),
                "split_sha256": sha(split),
                "target": "co2_conversion",
                "candidates": candidates,
                "model_seed": plan.get("model_seed", 42),
                "metrics": plan.get("metrics", ["mae", "rmse", "r2", "availability"]),
                "outputs": plan.get("outputs", ["predictions", "plots"]),
            }
            write_json(output / "configs" / f"{name}-{seed}.json", config)
    write_json(output / "plan.json", plan)
    return {"configurations": len(seeds) * len(experiments), "output": str(output)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.plan, args.output), ensure_ascii=False))
