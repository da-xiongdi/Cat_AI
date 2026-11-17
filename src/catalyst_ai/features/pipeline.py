"""Fold-fitted R1 features, independent of the historical design-features-v1."""

import math
from dataclasses import dataclass

from catalyst_ai.features.design import design_input

VERSION = "r1-features-v1"
CONDITIONS = ("temperature_k", "pressure_bar_abs", "h2_co2_ratio", "reactants_flow_nl_g_h")


def project(payload):
    """Validate and project a governed payload into complete R1 inputs."""
    item = design_input(payload)
    comp = item["composition"]
    if comp is None:
        raise ValueError("invalid_composition: " + item["composition_state"])
    if comp["basis"] != "mol_pct":
        raise ValueError("invalid_composition: material mol_pct required")
    amounts = {}
    for component in comp["components"]:
        key = (component["role"], component["species"])
        amounts[key] = amounts.get(key, 0.0) + component["amount"]
    if abs(sum(amounts.values()) - 100) > 0.5:
        raise ValueError("invalid_composition: amounts do not close to 100%")
    values = item["values"]
    for name in CONDITIONS:
        if values[name] is None or not math.isfinite(values[name]) or values[name] <= 0:
            raise ValueError("invalid_condition: " + name)
    return {"conditions": {name: values[name] for name in CONDITIONS}, "amounts": amounts}


@dataclass
class R1Features:
    """Fit on training payloads only; transform supports explicit diagnostic mode."""

    feature_set: str
    vocabulary: tuple
    ranges: dict

    @classmethod
    def fit(cls, payloads, feature_set="F_base"):
        if feature_set not in ("F_cond", "F_base"):
            raise ValueError("unsupported feature set")
        rows = [project(payload) for payload in payloads]
        if not rows:
            raise ValueError("training inputs are empty")
        vocabulary = tuple(
            sorted({key for row in rows for key, v in row["amounts"].items() if v > 0})
        )
        ranges = {}
        for name in CONDITIONS:
            values = [row["conditions"][name] for row in rows]
            ranges[name] = (min(values), max(values))
        for key in vocabulary:
            values = [row["amounts"].get(key, 0) for row in rows]
            ranges[key] = (min(values), max(values))
        return cls(feature_set, vocabulary, ranges)

    def transform_one(self, payload, *, diagnostic=False):
        row = project(payload)
        unseen = sorted(
            key for key, value in row["amounts"].items() if value > 0 and key not in self.vocabulary
        )
        warnings = []
        for name in CONDITIONS:
            low, high = self.ranges[name]
            if not low <= row["conditions"][name] <= high:
                warnings.append(name)
        if self.feature_set == "F_base":
            for key in self.vocabulary:
                low, high = self.ranges[key]
                if not low <= row["amounts"].get(key, 0) <= high:
                    warnings.append(key)
        values = [row["conditions"][name] for name in CONDITIONS]
        if self.feature_set == "F_base":
            values += [row["amounts"].get(key, 0) for key in self.vocabulary]
        unsupported = bool(unseen) and self.feature_set == "F_base"
        return {
            "status": "unsupported_species_role"
            if unsupported
            else "caution"
            if warnings
            else "ok",
            "values": values if diagnostic or not unsupported else None,
            "unseen_species_roles": unseen if self.feature_set == "F_base" else [],
            "out_of_range": warnings,
            "fully_encoded": not unsupported,
        }


def select_inputs(snapshot, qualification, split):
    """Select complete inputs while retaining the validated, original paper partitions."""
    from catalyst_ai.datasets.split import build_paper_split, normalize_doi
    from catalyst_ai.reporting.evidence import digest

    if split != build_paper_split(
        snapshot, qualification, seed=split.get("content", {}).get("seed", 42)
    ):
        raise ValueError("split does not match validated inputs")
    records = {r["record_id"]: r for r in snapshot["content"]["records"]}
    selected, excluded, counts = {}, {}, {}
    for partition in ("train", "validation", "test"):
        selected[partition], excluded[partition] = [], []
        for identifier in split["content"]["splits"][partition]["record_ids"]:
            try:
                project(records[identifier]["payload"])
            except ValueError as error:
                excluded[partition].append({"record_id": identifier, "reason": str(error)})
            else:
                selected[partition].append(identifier)
        counts[partition] = {
            "retained_records": len(selected[partition]),
            "excluded_records": len(excluded[partition]),
            "retained_papers": len(
                {normalize_doi(records[i]["payload"]["source"]["doi"]) for i in selected[partition]}
            ),
        }
    content = {
        "selection_version": "r1-selection-v1",
        "snapshot_id": snapshot["snapshot_id"],
        "qualification_id": qualification["qualification_id"],
        "split_id": split["split_id"],
        "retained": selected,
        "excluded": excluded,
        "counts": counts,
    }
    h = digest(content)
    return {"selection_id": "selection-" + h, "content_sha256": h, "content": content}
