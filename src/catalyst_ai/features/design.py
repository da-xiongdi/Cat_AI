"""Versioned, train-fitted design features; no outcome or characterization inputs."""

import hashlib
import math
import re
from pathlib import Path

from catalyst_ai.datasets.split import build_paper_split
from catalyst_ai.reporting.evidence import canonical, digest

VERSION = "design-features-v1"
# Explicit units prevent the same numeric column from silently combining incompatible quantities.
CONDITIONS = {
    "temperature_k": ("temperature", "K"),
    "pressure_bar_abs": ("pressure", "bar(abs)"),
    "catalyst_mass_g": ("catalyst_mass", "g"),
}
PLAN_UNITS = {
    "calcination_temperature_k": "K",
    "calcination_time_h": "h",
    "reduction_temperature_k": "K",
    "reduction_time_h": "h",
}


def measurement(value, unit):
    value = value or {}
    number = value.get("normalized_value")
    if (
        value.get("state") not in ("reported", "zero")
        or isinstance(number, bool)
        or not isinstance(number, (int, float))
        or not math.isfinite(number)
        or value.get("normalized_unit") != unit
    ):
        return None, value.get("state", "not_reported") if number is None else "unavailable"
    return number, value["state"]


def composition(recipe):
    basis, scope = recipe.get("composition_basis"), recipe.get("composition_scope")
    if basis not in ("mol_pct", "wt_pct", "atomic_pct") or scope not in (
        "whole catalyst material",
        "whole catalyst",
        "whole",
    ):
        return None, "unknown_basis_or_scope"
    components = []
    for c in recipe.get("components", []):
        amount, state = measurement(c.get("amount"), "%")
        if (
            not isinstance(c.get("species"), str)
            or not re.fullmatch(r"[A-Za-z0-9().+/_-]{1,80}", c["species"])
            or c.get("role") not in ("element", "compound", "support", "promoter")
            or amount is None
            or not 0 <= amount <= 100
        ):
            return None, "incomplete_or_invalid_components"
        components.append({"species": c["species"], "role": c["role"], "amount": amount})
    if not components or recipe.get("orphan_amount_fields"):
        return None, "incomplete_or_invalid_components"
    components.sort(key=canonical)
    return {"basis": basis, "scope": scope, "components": components}, "available"


def design_input(payload, *, planned_synthesis=None):
    """Project only explicit design-time fields; historical synthesis is never presumed planned.

    planned_synthesis is an explicitly supplied mapping of PLAN_UNITS keys to Measurement
    objects. Caller is responsible for establishing its design-time provenance.
    """
    plan = planned_synthesis or {}
    if set(plan) - set(PLAN_UNITS):
        raise ValueError("不支持的计划合成字段")
    comp, comp_state = composition(payload.get("recipe") or {})
    test = payload.get("test") or {}
    values, states = {}, {}
    for name, (key, unit) in CONDITIONS.items():
        values[name], states[name] = measurement(test.get(key), unit)
    if test.get("pressure_type") != "absolute":
        values["pressure_bar_abs"], states["pressure_bar_abs"] = None, "unavailable"
    flow = test.get("mass_normalized_volume_flow") or {}
    flow_ok = (
        flow.get("mass_basis") == "catalyst"
        and flow.get("gas_scope") == "reactants_only"
        and measurement(flow.get("reference_temperature"), "K")[0] == 293.15
        and measurement(flow.get("reference_pressure"), "bar(abs)")[0] == 1.01325
        and flow.get("reference_pressure_type") == "absolute"
    )
    values["reactants_flow_nl_g_h"], states["reactants_flow_nl_g_h"] = (
        measurement(flow.get("value"), "NL/g_cat/h") if flow_ok else (None, "unavailable")
    )
    ratio = test.get("reactant_ratio") or {}
    values["h2_co2_ratio"], states["h2_co2_ratio"] = (
        measurement(ratio.get("value"), "1")
        if ratio.get("numerator") == "H2" and ratio.get("denominator") == "CO2"
        else (None, "unavailable")
    )
    for name, unit in PLAN_UNITS.items():
        values[name], states[name] = measurement(plan.get(name), unit)
    return {
        "composition": comp,
        "composition_state": comp_state,
        "values": values,
        "states": states,
    }


def build_feature_table(snapshot, qualification, split):
    # Reconstruct the split, including source and leakage checks, instead of trusting assignments.
    split_content = split.get("content", {})
    if split != build_paper_split(snapshot, qualification, seed=split_content.get("seed", 42)):
        raise ValueError("划分清单与输入不一致或已损坏")
    records = {r["record_id"]: r for r in snapshot["content"]["records"]}
    raw = {i: design_input(r["payload"]) for i, r in records.items()}
    train_ids = split_content["splits"]["train"]["record_ids"]
    vocabulary = set()
    for i in train_ids:
        comp = raw[i]["composition"]
        if comp:
            for item in comp["components"]:
                vocabulary.add(
                    canonical([comp["basis"], comp["scope"], item["role"], item["species"]])
                )
    vocabulary = sorted(vocabulary)
    rows = []
    for partition in ("train", "validation", "test"):
        for i in split_content["splits"][partition]["record_ids"]:
            item = raw[i]
            comp = item["composition"]
            amounts = {}
            if comp:
                for component in comp["components"]:
                    key = canonical(
                        [comp["basis"], comp["scope"], component["role"], component["species"]]
                    )
                    amounts[key] = amounts.get(key, 0) + component["amount"]
            # An unlisted species is not evidence of a measured zero.
            encoded = {key: amounts.get(key) if comp else None for key in vocabulary}
            rows.append(
                {
                    "record_id": i,
                    "partition": partition,
                    "composition_signature": digest(comp) if comp else None,
                    "composition_state": item["composition_state"],
                    "composition_values": encoded,
                    "unseen_component_count": len(set(amounts) - set(vocabulary)) if comp else None,
                    "values": item["values"],
                    "states": item["states"],
                }
            )
    content = {
        "feature_version": VERSION,
        "snapshot_id": snapshot["snapshot_id"],
        "split_id": split["split_id"],
        "qualification_id": qualification["qualification_id"],
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "vocabulary_fit_partition": "train",
        "imputation": "none",
        "composition_vocabulary": vocabulary,
        "field_sources": {
            "composition_values": (
                "recipe.components; recipe.composition_basis; recipe.composition_scope"
            ),
            "values": (
                "test.temperature, pressure, catalyst_mass, mass_normalized_volume_flow, "
                "reactant_ratio; explicit planned synthesis only"
            ),
        },
        "availability": {
            "composition_values": "design",
            "values": "planned test conditions; explicit planned synthesis",
        },
        "limitations": [
            "historical synthesis and test time excluded",
            "unknown composition is not normalized",
            "paper split does not establish sample independence",
            "snapshot source acceptance and pressure assumptions remain applicable",
        ],
        "rows": rows,
    }
    h = digest(content)
    return {"feature_table_id": "features-" + h, "content_sha256": h, "content": content}
