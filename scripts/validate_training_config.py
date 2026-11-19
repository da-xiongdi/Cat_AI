"""Inspect the S2 configuration catalog or validate a configuration without training."""

import argparse
import json

from catalyst_ai.modeling.config import TrainingConfig, catalog, load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--catalog", action="store_true", help="show models and parameter rules")
    group.add_argument("--schema", action="store_true", help="show configuration JSON Schema")
    group.add_argument("--validate", metavar="FILE", help="validate configuration and dependencies")
    args = parser.parse_args()
    result = (
        catalog()
        if args.catalog
        else (TrainingConfig.model_json_schema() if args.schema else load_config(args.validate))
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
