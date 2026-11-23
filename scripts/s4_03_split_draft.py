"""Produce preliminary S4-03 manifests; does not train or score models."""

import argparse
import hashlib
import json
from pathlib import Path

from s4_01_profile import ROOT, profile

from catalyst_ai.datasets.research_split import partition
from catalyst_ai.reporting.evidence import digest, write_json


def main(output, *, seeds=(42, 43, 44), train_fraction=0.8, folds=5, status="preliminary"):
    base = ROOT / "artifacts/reports/s4-02-20261120-v1"
    views = [
        json.loads((base / (name + "-view.json")).read_text(encoding="utf-8"))
        for name in ("all", "cu")
    ]
    for view in views:
        if digest(view["content"]) != view["content_sha256"] or not view["view_id"].endswith(
            view["content_sha256"]
        ):
            raise ValueError("view hash mismatch")
        for path, expected in view["content"]["binding"]["sources"].items():
            if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected:
                raise ValueError(f"frozen source mismatch: {path}")
        for name in ("ledger", "distributions"):
            if (
                hashlib.sha256((base / f"{name}.json").read_bytes()).hexdigest()
                != view["content"][f"{name}_sha256"]
            ):
                raise ValueError(f"frozen {name} mismatch")
    all_ids, cu_ids = [set(v["content"]["common_record_ids"]) for v in views]
    _, rows, _, _ = profile()
    rows = [
        dict(r, repeat_group=r["confirmed_repeat_group"]) for r in rows if r["record_id"] in all_ids
    ]
    if len(rows) != 542 or len(cu_ids) != 211 or not cu_ids <= all_ids:
        raise ValueError("view membership mismatch")
    output.mkdir(parents=True, exist_ok=False)
    if len(seeds) != len(set(seeds)):
        raise ValueError("seeds must be unique")
    for seed in seeds:
        for name, strategy in [("EXP-01", "doi"), ("EXP-02", "random")]:
            p = partition(
                rows, strategy=strategy, seed=seed, train_fraction=train_fraction, folds=folds
            )
            p.update(
                {
                    "dataset_view_id": views[0]["view_id"],
                    "status": status,
                    "protocol_version": "research-split-v1",
                    "test_purpose": "internal evaluation",
                }
            )
            p["content_sha256"] = digest(p)
            p["split_id"] = "research-split-" + p["content_sha256"]
            write_json(output / f"{name}-{seed}.json", p)
            if name == "EXP-02":
                q = dict(p, dataset_view_id=views[1]["view_id"], strategy="random_projection")
                for key in ("train", "test"):
                    q[key] = sorted(set(p[key]) & cu_ids)
                q["validation_folds"] = [sorted(set(f) & cu_ids) for f in p["validation_folds"]]
                q["groups"] = [sorted(set(g) & cu_ids) for g in p["groups"] if set(g) & cu_ids]
                q.pop("split_id")
                q.pop("content_sha256")
                q["content_sha256"] = digest(q)
                q["split_id"] = "research-split-" + q["content_sha256"]
                write_json(output / f"EXP-03-{seed}.json", q)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 43, 44])
    parser.add_argument("--train-fraction", type=float, default=0.8)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--status", choices=["preliminary", "frozen"], default="preliminary")
    args = parser.parse_args()
    main(
        args.output,
        seeds=args.seeds,
        train_fraction=args.train_fraction,
        folds=args.folds,
        status=args.status,
    )
