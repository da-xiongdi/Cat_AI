"""Research experiment operations; preflight, training and scoring are separate."""

import argparse
import json
from pathlib import Path

from catalyst_ai.modeling.research_preflight import preflight
from catalyst_ai.modeling.research_run import fit, fit_batch, score

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="operation", required=True)
    check = sub.add_parser("preflight")
    check.add_argument("config", type=Path)
    check.add_argument("--output", type=Path)
    training = sub.add_parser("train")
    training.add_argument("config", type=Path)
    training.add_argument("--output", type=Path, required=True)
    batch = sub.add_parser("train-batch")
    batch.add_argument("config_directory", type=Path)
    batch.add_argument("--output", type=Path, required=True)
    scoring = sub.add_parser("score")
    scoring.add_argument("run", type=Path)
    scoring.add_argument("--retry", action="store_true")
    args = parser.parse_args()
    if args.operation == "preflight":
        result = preflight(args.config, root=ROOT)
        if args.output and args.output.exists():
            raise ValueError("output must be a new path")
        result = {
            "counts": result["counts"],
            "hashes": result["hashes"],
            "config": result["config"],
            "feature_validation": result["feature_validation"],
        }
    elif args.operation == "train":
        result = fit(args.config, args.output, root=ROOT)
    elif args.operation == "train-batch":
        result = fit_batch(args.config_directory, args.output, root=ROOT)
    else:
        result = score(args.run, root=ROOT, retry=args.retry)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.operation == "train-batch" and any(row["status"] == "failed" for row in result):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
