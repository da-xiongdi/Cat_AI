"""Run the fixed R1 comparison and write a new development report directory."""

import argparse
import hashlib
import json
from pathlib import Path

from catalyst_ai.modeling.experiments import compare_r1, write_r1_comparison
from catalyst_ai.modeling.predictor import save_package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("snapshot", "qualification", "split", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument(
        "--raw",
        type=Path,
        action="append",
        default=[],
        help="Original source file; repeat as needed",
    )
    parser.add_argument("--package", type=Path, help="New prediction package directory")
    args = parser.parse_args()
    snapshot, qualification, split = (
        json.loads(path.read_text(encoding="utf-8"))
        for path in (args.snapshot, args.qualification, args.split)
    )
    raw_files = {hashlib.sha256(path.read_bytes()).hexdigest(): path for path in args.raw}
    report, fitted = compare_r1(snapshot, qualification, split, raw_files=raw_files)
    write_r1_comparison(args.output, report)
    if args.package:
        save_package(args.package, report, fitted)
    print(json.dumps({"selected": report["selected"], "content_sha256": report["content_sha256"]}))


if __name__ == "__main__":
    main()
