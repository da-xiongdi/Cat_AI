"""Create and preflight first-round configuration templates without training."""

import argparse
from pathlib import Path

from catalyst_ai.modeling.research_preflight import preflight, read_json, sha
from catalyst_ai.reporting.evidence import write_json

ROOT = Path(__file__).resolve().parents[1]


def main(directory):
    directory = directory.resolve()
    template = read_json(ROOT / "configs/research_preflight_example.json")
    for seed in (42, 43, 44):
        for name in ("EXP-01", "EXP-02", "EXP-03"):
            split = directory / f"{name}-{seed}.json"
            try:
                split_path = split.relative_to(ROOT).as_posix()
            except ValueError:
                split_path = str(split)
            config = dict(template, split=split_path, split_sha256=sha(split))
            if name == "EXP-03":
                config["view"] = "artifacts/reports/s4-02-20261120-v1/cu-view.json"
            path = directory / "configs" / f"{name}-{seed}.json"
            write_json(path, config)
            preflight(path, root=ROOT)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    main(parser.parse_args().directory)
