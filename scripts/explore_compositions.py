"""Explore known training compositions and small variants, not laboratory plans."""

import argparse
import hashlib
from collections import Counter
from copy import deepcopy
from pathlib import Path

import numpy as np
from sklearn.metrics import pairwise_distances

from catalyst_ai.datasets.split import load_json
from catalyst_ai.features.design import design_input
from catalyst_ai.modeling.baseline import feature_matrix
from catalyst_ai.modeling.diagnostics import estimate_spread, verified_model
from catalyst_ai.modeling.screening import CONDITIONS
from catalyst_ai.reporting.evidence import canonical, digest, write_json


def generate(snapshot, qualification, split, features, run, model_path, diagnostic):
    if diagnostic.get("content_sha256") != digest(diagnostic.get("content")) or diagnostic.get(
        "diagnostic_id"
    ) != "diagnostic-" + diagnostic.get("content_sha256", ""):
        raise ValueError("Invalid diagnostic digest")
    if diagnostic["content"]["baseline_run_id"] != run["run_id"]:
        raise ValueError("Diagnostic and baseline mismatch")
    model, names = verified_model(run, model_path, snapshot, qualification, split, features)
    rows = [r for r in features["content"]["rows"] if r["partition"] == "train"]
    records = {r["record_id"]: r for r in snapshot["content"]["records"]}
    modes = Counter(
        tuple(row["values"][k] for k in CONDITIONS)
        for row in rows
        if all(row["values"][k] is not None and row["values"][k] > 0 for k in CONDITIONS)
    )
    if not modes:
        raise ValueError("No complete training conditions")
    frequency = max(modes.values())
    fixed = min(key for key, count in modes.items() if count == frequency)
    fixed_values = dict(zip(CONDITIONS, fixed, strict=True))
    fixed_papers = Counter(
        records[row["record_id"]]["payload"]["source"]["doi"]
        for row in rows
        if all(row["values"][key] == value for key, value in fixed_values.items())
    )
    threshold = diagnostic["content"]["domain"]["threshold"]
    train_z = model[:-1].transform(feature_matrix(rows, names))
    vocabulary = set(features["content"]["composition_vocabulary"])
    known = {}
    for row in sorted(rows, key=lambda x: x["record_id"]):
        record = records[row["record_id"]]
        comp = design_input(record["payload"])["composition"]
        if comp is None or comp["basis"] != "mol_pct":
            continue
        if abs(sum(c["amount"] for c in comp["components"]) - 100) > 0.5:
            continue
        pairs = [(c["role"], c["species"]) for c in comp["components"]]
        if len(set(pairs)) != len(pairs):
            continue
        known.setdefault(canonical(comp), (comp, row["record_id"]))
    generated = {}
    for key, (comp, parent_id) in sorted(known.items()):
        generated.setdefault(key, (comp, parent_id, "observed_training_composition", None))
        for i, donor in enumerate(comp["components"]):
            for j, receiver in enumerate(comp["components"]):
                if i == j or donor["amount"] <= 5 or receiver["amount"] + 5 > 100:
                    continue
                variant = deepcopy(comp)
                variant["components"][i]["amount"] = round(donor["amount"] - 5, 10)
                variant["components"][j]["amount"] = round(receiver["amount"] + 5, 10)
                variant["components"].sort(key=canonical)
                variant_key = canonical(variant)
                generated.setdefault(
                    variant_key,
                    (
                        variant,
                        parent_id,
                        "training_neighborhood_variant",
                        {
                            "from": donor["species"],
                            "to": receiver["species"],
                            "mol_percentage_points": 5,
                        },
                    ),
                )
    candidates, excluded = [], 0
    for key, (comp, parent_id, origin, change) in sorted(generated.items()):
        # If a generated variant is already observed, label it accordingly.
        if key in known:
            comp, parent_id = known[key]
            origin, change = "observed_training_composition", None
        amounts = {
            canonical([comp["basis"], comp["scope"], c["role"], c["species"]]): c["amount"]
            for c in comp["components"]
        }
        if set(amounts) - vocabulary:
            excluded += 1
            continue
        values = {name: None for name in rows[0]["values"]}
        values.update(fixed_values)
        row = {"values": values, "composition_values": {k: amounts.get(k) for k in vocabulary}}
        x = feature_matrix([row], names)
        distances = pairwise_distances(model[:-1].transform(x), train_z)[0]
        nearest = rows[int(np.argmin(distances))]["record_id"]
        distance = float(distances.min())
        if distance > threshold:
            excluded += 1
            continue
        mean, spread = estimate_spread(model, x)
        parent = records[parent_id]
        candidates.append(
            {
                "candidate_id": "explore-" + digest(comp)[:12],
                "composition": comp,
                "origin": origin,
                "change": change,
                "source_record_id": parent_id,
                "source_locator": parent["input_locator"],
                "source_doi": parent["payload"]["source"].get("doi"),
                "nearest_training_record_id": nearest,
                "nearest_distance": distance,
                "predicted_co2_conversion_pct": float(mean[0]),
                "tree_spread_percentage_points": float(spread[0]),
                "uncertainty_calibrated": False,
            }
        )
    candidates.sort(key=lambda c: (-c["predicted_co2_conversion_pct"], c["candidate_id"]))
    selected, families = [], set()
    for item in candidates:
        family = tuple(sorted((c["role"], c["species"]) for c in item["composition"]["components"]))
        if family not in families:
            selected.append(item["candidate_id"])
            families.add(family)
        if len(selected) == 4:
            break
    content = {
        "schema_version": "exploratory-compositions-v1",
        "baseline_run_id": run["run_id"],
        "diagnostic_id": diagnostic["diagnostic_id"],
        "snapshot_id": snapshot["snapshot_id"],
        "split_id": split["split_id"],
        "feature_table_id": features["feature_table_id"],
        "fixed_conditions": fixed_values,
        "fixed_conditions_training_record_count": frequency,
        "fixed_conditions_training_paper_count": len(fixed_papers),
        "fixed_conditions_training_papers": dict(sorted(fixed_papers.items())),
        "fixed_conditions_selection": "most frequent complete training tuple; "
        "ascending tuple breaks ties",
        "generation": "training mol% compositions within 0.5 percentage point of closure; "
        "transfer 5 percentage points between existing species",
        "known_training_composition_count": len(known),
        "generated_unique_count": len(generated),
        "excluded_by_unknown_species_or_distance": excluded,
        "eligible_count": len(candidates),
        "selection": "highest predicted CO2 conversion, at most one per exact "
        "species-role set; up to four",
        "selected_ids": selected,
        "candidates": candidates,
        "limitations": [
            "research comparison only, not an experimental plan or screening approval",
            "no synthesis route, precursor availability, compatibility, equipment, "
            "cost or safety verification",
            "source records accepted as published dataset, not individually verified; "
            "pressure type assumed absolute",
            "CO2 conversion is not methanol yield or selectivity; model uncertainty not calibrated",
            "training distance is a heuristic and does not establish applicability",
        ],
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    h = digest(content)
    return {"exploration_id": "exploration-" + h, "content_sha256": h, "content": content}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "snapshot",
        "qualification",
        "split",
        "features",
        "run",
        "model",
        "diagnostic",
        "output",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.suffix.lower() != ".json":
        raise ValueError("Output must be a new JSON file")
    result = generate(
        load_json(args.snapshot),
        load_json(args.qualification),
        load_json(args.split),
        load_json(args.features),
        load_json(args.run),
        args.model,
        load_json(args.diagnostic),
    )
    write_json(args.output, result)
    print(result["exploration_id"], len(result["content"]["selected_ids"]))


if __name__ == "__main__":
    main()
