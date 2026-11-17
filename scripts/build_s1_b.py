"""Build and persist a verified S1-B snapshot into a new output directory."""

import argparse
from pathlib import Path

from catalyst_ai.features.build import build
from catalyst_ai.reporting.evidence import write_json
from catalyst_ai.sources.files import strict_json
from catalyst_ai.storage.feature_build import persist
from catalyst_ai.storage.feature_catalog import get_catalog, get_evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("database", "snapshot", "qualification", "split", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("properties", "species", "review"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--evidence-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output directory already exists")
    snapshot, qualification, split = (
        strict_json(p.read_text(encoding="utf-8-sig"))
        for p in (args.snapshot, args.qualification, args.split)
    )
    selection, features = build(
        snapshot,
        qualification,
        split,
        get_catalog(args.database, "properties", args.properties),
        get_catalog(args.database, "species", args.species),
        get_evidence(args.database, args.review),
        root=args.evidence_root,
    )
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "selection.json", selection)
    write_json(args.output / "features.json", features)
    persist(args.database, selection, features)
    print(features["feature_snapshot_id"])


if __name__ == "__main__":
    main()
