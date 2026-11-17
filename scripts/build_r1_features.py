"""Build an R1 selection and train-fitted diagnostic feature table."""

import argparse
import json
from pathlib import Path

from catalyst_ai.features.pipeline import R1Features, select_inputs
from catalyst_ai.reporting.evidence import digest, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("snapshot", "qualification", "split", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    snapshot, qualification, split = (
        json.loads(p.read_text(encoding="utf-8"))
        for p in (args.snapshot, args.qualification, args.split)
    )
    selection = select_inputs(snapshot, qualification, split)
    records = {r["record_id"]: r["payload"] for r in snapshot["content"]["records"]}
    partitions = selection["content"]["retained"]
    models = {
        name: R1Features.fit([records[i] for i in partitions["train"]], name)
        for name in ("F_cond", "F_base")
    }
    content = {
        "feature_version": "r1-features-v1",
        "selection_id": selection["selection_id"],
        "vocabulary_fit_partition": "train",
        "composition_vocabulary": [list(k) for k in models["F_base"].vocabulary],
        "rows": [
            {
                "record_id": identifier,
                "partition": partition,
                "features": {
                    name: model.transform_one(records[identifier], diagnostic=True)
                    for name, model in models.items()
                },
            }
            for partition, ids in partitions.items()
            for identifier in ids
        ],
    }
    feature_hash = digest(content)
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "selection.json", selection)
    write_json(args.output / "features.json", {"content_sha256": feature_hash, "content": content})


if __name__ == "__main__":
    main()
