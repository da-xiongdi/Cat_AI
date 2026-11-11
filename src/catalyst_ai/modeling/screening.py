"""Screen explicitly specified designs; never infer synthesis plans or constraints."""

import hashlib
import math
from pathlib import Path

import numpy as np
from sklearn.metrics import pairwise_distances

from catalyst_ai.features.design import design_input
from catalyst_ai.modeling.baseline import feature_matrix
from catalyst_ai.modeling.diagnostics import estimate_spread, verified_model
from catalyst_ai.reporting.evidence import canonical, digest

CONDITIONS = (
    "temperature_k",
    "pressure_bar_abs",
    "catalyst_mass_g",
    "h2_co2_ratio",
    "reactants_flow_nl_g_h",
)
REVIEW = ("equipment", "chemistry_compatibility", "precursors", "cost_risk")


def screen(spec, diagnostic, run, model_path, snapshot, qualification, split, features):
    """Rank supplied complete designs at fixed test conditions under supplied bounds.

    The constraint review is an operator assertion, not a claim of independent verification.
    """
    if not isinstance(spec, dict):
        raise ValueError("Screening spec must be an object")
    if diagnostic.get("content_sha256") != digest(diagnostic.get("content")) or diagnostic.get(
        "diagnostic_id"
    ) != "diagnostic-" + diagnostic.get("content_sha256", ""):
        raise ValueError("Diagnostic report hash mismatch")
    diagnostic_content = diagnostic["content"]
    if diagnostic_content["baseline_run_id"] != run["run_id"]:
        raise ValueError("Diagnostic and baseline mismatch")
    if run["target"]["metric"] != "co2_conversion" or run["target"]["unit"] != "%":
        raise ValueError("This screening version requires CO2 conversion in percent")
    model, names = verified_model(run, model_path, snapshot, qualification, split, features)
    capacity = spec.get("capacity", 4)
    if isinstance(capacity, bool) or not isinstance(capacity, int) or not 1 <= capacity <= 6:
        raise ValueError("capacity must be an integer from 1 to 6")
    candidates = spec.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidate designs must be provided")
    reviews = spec.get("constraint_evidence") or {}
    if not isinstance(reviews, dict):
        raise ValueError("constraint_evidence must be an object")
    if any(not isinstance(reviews.get(k), str) or not reviews[k].strip() for k in REVIEW):
        raise ValueError("equipment, compatibility, precursors and cost/risk evidence required")
    allowed = spec.get("allowed_species")
    if (
        not isinstance(allowed, list)
        or not allowed
        or any(not isinstance(v, str) or not v for v in allowed)
    ):
        raise ValueError("allowed_species must be a nonempty list")
    bounds = spec.get("condition_bounds") or {}
    if not isinstance(bounds, dict):
        raise ValueError("condition_bounds must be an object")
    for key in CONDITIONS:
        interval = bounds.get(key)
        if (
            not isinstance(interval, list)
            or len(interval) != 2
            or any(
                isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
                for x in interval
            )
            or interval[0] > interval[1]
        ):
            raise ValueError("Invalid explicit condition bounds: " + key)
    test = spec.get("fixed_test")
    if not isinstance(test, dict):
        raise ValueError("fixed_test is required")
    train_rows = [r for r in features["content"]["rows"] if r["partition"] == "train"]
    train_z = model[:-1].transform(feature_matrix(train_rows, names))
    records = {r["record_id"]: r for r in snapshot["content"]["records"]}
    vocabulary = set(features["content"]["composition_vocabulary"])
    ids, accepted, rejected = set(), [], []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("Each candidate must be an object")
        identifier = candidate.get("candidate_id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in ids:
            raise ValueError("Candidate IDs must be nonempty and unique")
        ids.add(identifier)
        reasons = []
        plan = candidate.get("planned_synthesis") or {}
        if not isinstance(plan, dict):
            rejected.append({"candidate_id": identifier, "reasons": ["invalid_plan"]})
            continue
        if not isinstance(candidate.get("recipe"), dict) or not isinstance(
            plan.get("parameters") or {}, dict
        ):
            rejected.append({"candidate_id": identifier, "reasons": ["invalid_design"]})
            continue
        if not isinstance(plan.get("route"), str) or not plan["route"].strip():
            reasons.append("missing_explicit_synthesis_route")
        if not isinstance(plan.get("evidence"), str) or not plan["evidence"].strip():
            reasons.append("missing_synthesis_plan_evidence")
        try:
            projected = design_input(
                {"recipe": candidate.get("recipe") or {}, "test": test},
                planned_synthesis=plan.get("parameters") or {},
            )
        except (ValueError, TypeError):
            rejected.append({"candidate_id": identifier, "reasons": ["invalid_plan"]})
            continue
        composition = projected["composition"]
        if composition is None:
            reasons.append("invalid_or_missing_composition")
            amounts = {}
        else:
            if composition["basis"] not in ("mol_pct", "wt_pct", "atomic_pct"):
                reasons.append("unsupported_composition_basis")
            if abs(sum(c["amount"] for c in composition["components"]) - 100) > 0.5:
                reasons.append("composition_not_closed")
            amounts = {}
            for component in composition["components"]:
                key = canonical(
                    [
                        composition["basis"],
                        composition["scope"],
                        component["role"],
                        component["species"],
                    ]
                )
                amounts[key] = amounts.get(key, 0) + component["amount"]
                if component["species"] not in allowed:
                    reasons.append("species_not_allowed")
            if set(amounts) - vocabulary:
                reasons.append("unseen_component")
        for key in CONDITIONS:
            value = projected["values"][key]
            if value is None or value <= 0 or not bounds[key][0] <= value <= bounds[key][1]:
                reasons.append("condition_missing_or_outside_configured_bounds:" + key)
            train_range = run["coverage"]["train"]["conditions"][key]["range"]
            if value is not None and train_range and not train_range[0] <= value <= train_range[1]:
                reasons.append("condition_outside_training_range:" + key)
        if reasons:
            rejected.append({"candidate_id": identifier, "reasons": sorted(set(reasons))})
            continue
        row = {
            "values": projected["values"],
            "composition_values": {k: amounts.get(k) for k in vocabulary},
        }
        x = feature_matrix([row], names)
        distances = pairwise_distances(model[:-1].transform(x), train_z)[0]
        nearest = train_rows[int(np.argmin(distances))]["record_id"]
        distance = float(distances.min())
        if distance > diagnostic_content["domain"]["threshold"]:
            rejected.append(
                {
                    "candidate_id": identifier,
                    "reasons": ["outside_distance_heuristic"],
                    "nearest_training_distance": distance,
                }
            )
            continue
        mean, sd = estimate_spread(model, x)
        accepted.append(
            {
                "candidate_id": identifier,
                "status": "proposed",
                "composition": composition,
                "planned_synthesis": plan,
                "fixed_conditions": {k: projected["values"][k] for k in CONDITIONS},
                "predicted_co2_conversion_pct": float(mean[0]),
                "tree_spread_pct_points": float(sd[0]),
                "uncertainty_calibrated": False,
                "nearest_training_distance": distance,
                "domain_status": "caution",
                "nearest_reference": {
                    "record_id": nearest,
                    "input_locator": records[nearest]["input_locator"],
                    "doi": records[nearest]["payload"]["source"].get("doi"),
                },
                "constraint_evidence": reviews,
                "limitations": [
                    "constraint evidence is operator supplied, not independently verified",
                    "synthesis plan parameters absent in training are not modeled",
                    "prediction is not measured performance",
                    "domain and uncertainty are not validated guarantees",
                ],
            }
        )
    accepted.sort(key=lambda c: (-c["predicted_co2_conversion_pct"], c["candidate_id"]))
    return {
        "schema_version": "i5-screen-v1",
        "baseline_run_id": run["run_id"],
        "dataset_kind": run["dataset_kind"],
        "scientific_use": run["scientific_use"],
        "diagnostic_id": diagnostic["diagnostic_id"],
        "spec_sha256": digest(spec),
        "spec": spec,
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "dependencies": diagnostic_content.get("dependencies"),
        "capacity": capacity,
        "ranking": "predicted conversion descending; candidate ID tie break",
        "selected": accepted[:capacity],
        "other_eligible": accepted[capacity:],
        "rejected": rejected,
        "limitation": "No uncertainty coverage or applicability guarantee; "
        "no experimental approval",
    }
