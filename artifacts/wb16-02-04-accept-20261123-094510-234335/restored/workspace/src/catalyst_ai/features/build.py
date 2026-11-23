"""Reproducible S1-B feature build from verified catalog and source evidence."""

import hashlib
from pathlib import Path

from catalyst_ai.features.physchem import VERSION, calculate
from catalyst_ai.features.pipeline import project, select_inputs
from catalyst_ai.features.qualification import qualify
from catalyst_ai.reporting.evidence import digest


def build(snapshot, qualification, split, properties, species, review, *, root):
    """Verify all evidence, retain original DOI partitions, and compute supported rows."""
    base = select_inputs(snapshot, qualification, split)
    coverage = qualify(snapshot, qualification, split, properties, species, review, root=root)
    records = {r["record_id"]: r["payload"] for r in snapshot["content"]["records"]}
    checks = {r["record_id"]: r for r in coverage["content"]["records"]}
    retained, excluded, rows = {}, {}, []
    for part in ("train", "validation", "test"):
        retained[part] = []
        excluded[part] = list(base["content"]["excluded"][part])
        for rid in base["content"]["retained"][part]:
            check = checks[rid]
            if not check["joint_supported"]:
                excluded[part].append({"record_id": rid, "reason": check["reasons"]})
                continue
            projected = project(records[rid])
            try:
                descriptors = calculate(records[rid], properties, species)
            except ValueError as error:
                excluded[part].append({"record_id": rid, "reason": [str(error)]})
                continue
            retained[part].append(rid)
            rows.append(
                {
                    "record_id": rid,
                    "partition": part,
                    "conditions": projected["conditions"],
                    "composition": [
                        {"role": role, "species": name, "material_mol_pct": amount}
                        for (role, name), amount in sorted(projected["amounts"].items())
                        if amount > 0
                    ],
                    "derived": {
                        name: {
                            "value": value,
                            "state": "available" if value is not None else "not_applicable",
                        }
                        for name, value in descriptors.items()
                    },
                }
            )
    binding = {
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_sha256": snapshot["content_sha256"],
        "qualification_id": qualification["qualification_id"],
        "split_id": split["split_id"],
        "property_version": properties["catalog"]["version"],
        "property_sha256": properties["sha256"],
        "mapping_version": species["catalog"]["version"],
        "mapping_sha256": species["sha256"],
        "review_version": review["review"]["version"],
        "review_sha256": review["sha256"],
        "qualification_report_id": coverage["report_id"],
        "calculation_version": VERSION,
        "implementation_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                Path(__file__),
                Path(__file__).with_name("physchem.py"),
                Path(__file__).with_name("pipeline.py"),
            )
        },
    }

    def stats(ids):
        dois = {records[i]["source"]["doi"].strip().lower() for i in ids}
        signatures = set()
        for identifier in ids:
            try:
                amounts = project(records[identifier])["amounts"]
            except ValueError:
                continue
            signatures.add(
                tuple(
                    sorted(
                        (role, name, amount)
                        for (role, name), amount in amounts.items()
                        if amount > 0
                    )
                )
            )
        return {"records": len(ids), "dois": len(dois), "composition_signatures": len(signatures)}

    counts = {}
    for part in retained:
        excluded_ids = [r["record_id"] for r in excluded[part]]
        counts[part] = {
            "retained": stats(retained[part]),
            "excluded": stats(excluded_ids),
            "parent": stats(retained[part] + excluded_ids),
        }
    selection_content = {
        "version": "s1-b-selection-v1",
        "binding": binding,
        "retained": retained,
        "excluded": excluded,
        "coverage": coverage["content"]["by_partition"],
        "counts": counts,
    }
    selection_hash = digest(selection_content)
    selection = {
        "selection_id": "selection-" + selection_hash,
        "content_sha256": selection_hash,
        "content": selection_content,
    }
    content = {
        "version": "s1-b-features-v1",
        "binding": binding,
        "selection_id": selection["selection_id"],
        "rows": rows,
    }
    feature_hash = digest(content)
    features = {
        "feature_snapshot_id": "features-" + feature_hash,
        "content_sha256": feature_hash,
        "content": content,
    }
    return selection, features
