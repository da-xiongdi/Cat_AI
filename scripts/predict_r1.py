"""Predict one JSON object or an array using a trusted R1 or S2 package."""

import argparse
import json
from pathlib import Path

from catalyst_ai.modeling.predictor import load_package, predict_batch, predict_one


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    package = load_package(args.package)
    item = json.loads(args.input.read_text(encoding="utf-8"))
    result = predict_batch(package, item) if isinstance(item, list) else predict_one(package, item)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
