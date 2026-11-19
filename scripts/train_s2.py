"""Train a validated S2 configuration and save a trusted prediction package."""

import argparse
import json
from pathlib import Path

from catalyst_ai.modeling.config import load_config
from catalyst_ai.modeling.experiments import run_configured
from catalyst_ai.modeling.predictor import save_package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="training YAML file")
    parser.add_argument("--package", type=Path, required=True, help="new package directory")
    parser.add_argument(
        "--candidate",
        nargs=2,
        metavar=("FEATURE", "MODEL"),
        help="save a specific trained candidate instead of the selected candidate",
    )
    args = parser.parse_args()
    load_config(args.config)
    report, fitted = run_configured(args.config)
    metadata = save_package(
        args.package, report, fitted, candidate=tuple(args.candidate) if args.candidate else None
    )
    print(
        json.dumps(
            {
                "selected": report["selected"],
                "model_id": metadata["model_id"],
                "package": str(args.package),
            },
            ensure_ascii=False,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
