"""S1-A record/component qualification; no feature aggregation or model fitting."""

import hashlib
from collections import Counter
from pathlib import Path

from catalyst_ai.datasets.split import normalize_doi
from catalyst_ai.features.pipeline import project, select_inputs
from catalyst_ai.features.stoichiometry import formula_counts
from catalyst_ai.reporting.evidence import digest
from catalyst_ai.storage.feature_catalog import _UNITS, coverage

ALLOWED = {"dataset_accepted", "confirmed_original", "correction_rejected"}
STATES = ALLOWED | {"evidence_insufficient", "source_conflict"}


def validate_review(review):
    if (
        type(review.get("schema_version")) is not int
        or review["schema_version"] != 1
        or not isinstance(review.get("version"), str)
        or not review["version"].strip()
    ):
        raise ValueError("invalid review schema/version")
    for key in ("parent_snapshot_id", "parent_content_sha256", "rule_version", "reviewer"):
        if not isinstance(review.get(key), str) or not review[key].strip():
            raise ValueError("missing review " + key)
    if not review.get("evidence") or not isinstance(review.get("components"), list):
        raise ValueError("missing review evidence/components")
    for ref in review["evidence"]:
        if not ref.get("path") or len(ref.get("sha256", "")) != 64 or not ref.get("type"):
            raise ValueError("invalid evidence reference")
    seen = set()
    for row in review["components"]:
        key = (row["record_id"], row["component_index"])
        if type(key[1]) is not int or key[1] < 0 or key in seen:
            raise ValueError("duplicate/invalid component identity")
        seen.add(key)
        for field in (
            "original_species",
            "role",
            "source_doi",
            "dataset_sample_name",
            "dataset_locator",
            "rationale",
            "evidence_location",
        ):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError("missing component " + field)
        if row.get("status") not in STATES:
            raise ValueError("unresolved/invalid review status")
        if not isinstance(row.get("evidence_sha256"), list) or not row["evidence_sha256"]:
            raise ValueError("missing component evidence")
        if not set(row["evidence_sha256"]) <= {e["sha256"] for e in review["evidence"]}:
            raise ValueError("unbound component evidence")
        # A correction candidate is never an effective formula.
        if row.get("candidate_species") and row["status"] in ALLOWED:
            raise ValueError("candidate correction cannot confer eligibility")
    return review


def verify_evidence(review, root):
    validate_review(review)
    for ref in review["evidence"]:
        if hashlib.sha256((Path(root) / ref["path"]).read_bytes()).hexdigest() != ref["sha256"]:
            raise ValueError("external evidence hash mismatch: " + ref["path"])


def _summary(rows):
    keys = ("formula_parseable", "source_eligible", "mapping_supported", *_UNITS, "joint_supported")
    return {
        "denominator_records": len(rows),
        "denominator_species": len({c["species"] for r in rows for c in r["components"]}),
        "denominator_dois": len({r["doi"] for r in rows}),
        "records": {k: sum(r[k] for r in rows) for k in keys},
        "unique_species_all_occurrences_supported": {
            k: sum(
                all(c[k] for r in rows for c in r["components"] if c["species"] == name)
                for name in {c["species"] for r in rows for c in r["components"]}
            )
            for k in keys
        },
        "dois_all_records_supported": {
            k: sum(all(r[k] for r in rows if r["doi"] == doi) for doi in {r["doi"] for r in rows})
            for k in keys
        },
        "source_status_component_counts": dict(
            sorted(Counter(c["source_status"] for r in rows for c in r["components"]).items())
        ),
        "reason_record_counts": dict(
            sorted(Counter(reason for r in rows for reason in set(r["reasons"])).items())
        ),
    }


def qualify(snapshot, qualification, split, properties, species, review_package, *, root):
    """Validate all bindings, then report each layer with its original denominator."""
    selection = select_inputs(snapshot, qualification, split)
    review = review_package["review"]
    verify_evidence(review, root)
    if (
        review["parent_snapshot_id"] != snapshot["snapshot_id"]
        or review["parent_content_sha256"] != snapshot["content_sha256"]
    ):
        raise ValueError("review parent mismatch")
    # Legacy calculation also validates snapshot identity and catalog kinds.
    coverage(snapshot, properties, species)
    props = {(r["element"], r["property"]): r for r in properties["catalog"]["entries"]}
    mappings = {r["species"]: r for r in species["catalog"]["entries"]}
    ledger = {(r["record_id"], r["component_index"]): r for r in review["components"]}
    partitions = {
        rid: part for part, data in split["content"]["splits"].items() for rid in data["record_ids"]
    }
    expected = {
        (r["record_id"], i)
        for r in snapshot["content"]["records"]
        for i, _ in enumerate(r["payload"]["recipe"]["components"])
    }
    if set(ledger) != expected:
        raise ValueError("review scope mismatch")
    rows = []
    for record in sorted(snapshot["content"]["records"], key=lambda r: r["record_id"]):
        rid, payload = record["record_id"], record["payload"]
        doi = normalize_doi(payload["source"]["doi"])
        reasons, components = [], []
        try:
            projected = project(payload)
        except ValueError as exc:
            projected = None
            reasons.append(str(exc))
        for i, c in enumerate(payload["recipe"]["components"]):
            audit = ledger[rid, i]
            if (
                audit["original_species"] != c["species"]
                or audit["role"] != c["role"]
                or normalize_doi(audit["source_doi"]) != doi
                or audit["dataset_sample_name"] != payload["recipe"]["material_family"]
                or audit["dataset_locator"] != payload["extraction"]["locator"]
            ):
                raise ValueError("review component/source identity mismatch")
            amount = c["amount"]["normalized_value"]
            if amount is not None and amount == 0:
                continue
            name = c["species"]
            try:
                formula_counts(name)
                parsed = True
            except ValueError:
                parsed = False
            mapping = mappings.get(name, {})
            supported = mapping.get("state") == "supported"
            source_ok = audit["status"] in ALLOWED
            status = {
                "component_index": i,
                "species": name,
                "role": c["role"],
                "source_status": audit["status"],
                "formula_parseable": parsed,
                "source_eligible": source_ok,
                "mapping_supported": supported,
            }
            for prop in _UNITS:
                status[prop] = supported and all(
                    props.get((e, prop), {}).get("state") == "available"
                    for e in mapping.get("centers", {})
                )
            status["joint_supported"] = all(
                status[k]
                for k in ("formula_parseable", "source_eligible", "mapping_supported", *_UNITS)
            )
            components.append(status)
            if not parsed:
                reasons.append("formula_unsupported:" + name)
            if not source_ok:
                reasons.append(audit["status"] + ":" + name)
            if not supported:
                reasons.append("unsupported_species:" + name)
            for prop in _UNITS:
                if not status[prop]:
                    reasons.append("property_unavailable:" + name + ":" + prop)
        row = {
            "record_id": rid,
            "doi": doi,
            "partition": partitions[rid],
            "components": components,
            "reasons": sorted(set(reasons)),
            "roles": {
                role: "present" if any(c["role"] == role for c in components) else "not_applicable"
                for role in ("compound", "support")
            },
        }
        for key in (
            "formula_parseable",
            "source_eligible",
            "mapping_supported",
            *_UNITS,
            "joint_supported",
        ):
            row[key] = (
                projected is not None and bool(components) and all(c[key] for c in components)
            )
        rows.append(row)
    content = {
        "rule_version": review["rule_version"],
        "review_version": review["version"],
        "snapshot_id": snapshot["snapshot_id"],
        "qualification_id": qualification["qualification_id"],
        "split_id": split["split_id"],
        "input_selection_id": selection["selection_id"],
        "property_version": properties["catalog"]["version"],
        "mapping_version": species["catalog"]["version"],
        "property_sha256": properties["sha256"],
        "mapping_sha256": species["sha256"],
        "review_sha256": review_package["sha256"],
        "implementation_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                Path(__file__),
                Path(__file__).with_name("stoichiometry.py"),
                Path(__file__).parents[1] / "storage/feature_catalog.py",
            )
        },
        "coverage_kind": "data_mapping_qualification_not_computed_features",
        ("denominator_definition"): (
            "positive components; species/DOI pass only if all occurrences pass"
        ),
        "summary": _summary(rows),
        "by_partition": {
            part: _summary([r for r in rows if r["partition"] == part])
            for part in ("train", "validation", "test")
        },
        "by_doi": {
            doi: _summary([r for r in rows if r["doi"] == doi])
            for doi in sorted({r["doi"] for r in rows})
        },
        "by_species": _species_summary(rows),
        "records": rows,
    }
    return {
        "content": content,
        "content_sha256": digest(content),
        "report_id": "s1-qualification-" + digest(content),
    }


def _species_summary(rows):
    result = {}
    for name in sorted({c["species"] for r in rows for c in r["components"]}):
        occurrences = [c for r in rows for c in r["components"] if c["species"] == name]
        records = [r for r in rows if any(c["species"] == name for c in r["components"])]
        result[name] = {
            "denominator_component_occurrences": len(occurrences),
            "denominator_records": len(records),
            "denominator_dois": len({r["doi"] for r in records}),
            "partition_record_counts": dict(Counter(r["partition"] for r in records)),
            "source_status_counts": dict(Counter(c["source_status"] for c in occurrences)),
            "supported_occurrences": {
                key: sum(c[key] for c in occurrences)
                for key in (
                    "formula_parseable",
                    "source_eligible",
                    "mapping_supported",
                    *_UNITS,
                    "joint_supported",
                )
            },
        }
    return result
