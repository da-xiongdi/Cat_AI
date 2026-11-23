"""Audit S4-01 frozen TheMeCat rows and write reproducible, read-only evidence."""

import argparse
import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from statistics import median

from catalyst_ai.datasets.split import normalize_doi
from catalyst_ai.reporting.evidence import digest, write_json, write_new
from catalyst_ai.sources.themecat import adapt_v2

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "raw": "data/raw/46000f00323ac64a79f63777e54c05634e83d1a6476176c8b6569122bd03dfbd.csv",
    "snapshot": (
        "data/snapshots/"
        "snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json"
    ),
    "selection": "artifacts/reports/s1-b-20261113-v4/selection.json",
    "mapping": "configs/s1_species_mapping_v2.json",
}
# These two nominal formulas lack S1 physical-descriptor support. The explicitly
# named elements suffice for this presence check, without using either for features.
UNSUPPORTED_FORMULAS = {"InNi3O0.5": ("In", "Ni", "O"), "CoGaAlO4": ("Co", "Ga", "Al", "O")}
RAW_ROLE_FIELDS = ("active_comp_1", "active_comp_2", "support_comp_1", "support_comp_2")
SUPPLEMENTARY = ("selectivity_CH3OH", "yield_CH3OH", "STY_g_per_gcath")
PAPER_DISPOSITIONS = {
    ("lines:54-54", "lines:55-55"): (
        "distinct_pretreatment_confirmed",
        "Bahruji et al. Table 5: 10.7/10.8% rows match 120/250 C air calcination.",
        "https://orca.cardiff.ac.uk/id/eprint/88873/1/1-s2.0-S0021951716001135-main.pdf#page=10",
    ),
}
PROFILE = (
    "temperature_k",
    "pressure_bar_abs",
    "h2_co2_ratio",
    "flow_nl_g_h",
    "conversion_pct",
    "cu_species_mol_pct",
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_csv(path, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    write_new(path, stream.getvalue().encode("utf-8-sig"))


def raw_key(row):
    return tuple(row.items())


def specimen(name):
    return "".join(name.casefold().split())


def distribution(rows):
    def range_for(field):
        values = [row[field] for row in rows if row[field] is not None]
        return (
            {"n": len(values), "min": min(values), "median": median(values), "max": max(values)}
            if values
            else {"n": 0}
        )

    return {
        "records": len(rows),
        "doi_count": len({r["doi"] for r in rows}),
        "doi_records": dict(Counter(r["doi"] for r in rows).most_common()),
        "composition_signatures": len({r["composition"] for r in rows}),
        "classification": dict(Counter(r["classification"] for r in rows)),
        "species": dict(
            Counter(s for r in rows for s in sorted(set(r["cu_species"].split(";")) - {""}))
        ),
        "source_role_signatures": dict(
            Counter(r["cu_source_fields"] for r in rows if r["cu_source_fields"])
        ),
        "historical_partition": dict(
            Counter(r["historical_partition"] or "excluded" for r in rows)
        ),
        "ranges": {f: range_for(f) for f in PROFILE},
    }


def profile():
    blobs = {key: (ROOT / path).read_bytes() for key, path in FILES.items()}
    snapshot, selection, mapping = (
        json.loads(blobs[name]) for name in ("snapshot", "selection", "mapping")
    )
    for name, doc in (("snapshot", snapshot), ("selection", selection)):
        assert digest(doc["content"]) == doc["content_sha256"], name
    binding = selection["content"]["binding"]
    assert binding["snapshot_id"] == snapshot["snapshot_id"]
    assert binding["snapshot_sha256"] == snapshot["content_sha256"]
    assert binding["mapping_sha256"] == sha(blobs["mapping"])
    assert sha(blobs["raw"]) == Path(FILES["raw"]).stem
    source_rows, _ = adapt_v2(blobs["raw"])
    raw_by_locator = {row.locator: row.raw_payload for row in source_rows}
    raw_groups = defaultdict(list)
    for locator, raw in raw_by_locator.items():
        raw_groups[raw_key(raw)].append(locator)
    partitions = {
        rid: part for part, ids in selection["content"]["retained"].items() for rid in ids
    }
    source_elements = {
        entry["species"]: entry["elements"] for entry in mapping["entries"] if entry.get("elements")
    }
    source_elements.update(UNSUPPORTED_FORMULAS)
    rows = []
    frozen_raw = {}
    for entity in snapshot["content"]["records"]:
        rid, payload = entity["record_id"], entity["payload"]
        locator = payload["extraction"]["locator"].split()[-1]
        raw = raw_by_locator[locator]
        recipe, test = payload["recipe"], payload["test"]
        doi = normalize_doi(payload["source"]["doi"])
        assert doi == normalize_doi(raw["doi_link"])
        assert recipe["material_family"] == raw["catalyst_name"].strip()
        components = recipe["components"]
        composition = sorted(
            (c["role"], c["species"], c["amount"]["normalized_value"]) for c in components
        )
        positive = [c for c in composition if c[2] is not None and c[2] > 0]
        cu_components = [c for c in positive if "Cu" in source_elements[c[1]]]
        cu_species = {c[1] for c in cu_components}
        composition_known = recipe["composition_available"] == "yes" and all(
            c[2] is not None for c in composition
        )
        classification = (
            "cu" if cu_components else "non_cu" if composition_known else "insufficient"
        )
        raw_cu_fields = [key for key in RAW_ROLE_FIELDS if raw[key].strip() in cu_species]
        assert not cu_components or raw_cu_fields
        value = next(
            o["value"]["normalized_value"]
            for o in payload["observations"]
            if o["metric"] == "co2_conversion"
        )
        assert value == float(raw["CO2_conversion"])
        assert locator not in frozen_raw
        frozen_raw[locator] = rid
        rows.append(
            {
                "record_id": rid,
                "raw_locator": locator,
                "doi": doi,
                "sample_name": recipe["material_family"],
                "classification": classification,
                "cu_species": ";".join(sorted(cu_species)),
                "cu_source_fields": ";".join(raw_cu_fields),
                "cu_species_mol_pct": sum(c[2] for c in cu_components) if cu_components else None,
                "composition": json.dumps(positive, ensure_ascii=False, separators=(",", ":")),
                "historical_partition": partitions.get(rid),
                "temperature_k": test["temperature"]["normalized_value"],
                "pressure_bar_abs": test["pressure"]["normalized_value"],
                "h2_co2_ratio": test["reactant_ratio"]["value"]["normalized_value"],
                "flow_nl_g_h": test["mass_normalized_volume_flow"]["value"]["normalized_value"],
                "conversion_pct": value,
                "catalyst_load_g": raw["catalyst_load_g"],
                "surface_area_m2_g": raw["catalyst_surface_area_m2_g"],
                "pore_diameter_nm": raw["mean_pore_diameter_nm"],
                "methanol_selectivity_raw": raw[SUPPLEMENTARY[0]],
                "methanol_yield_raw": raw[SUPPLEMENTARY[1]],
                "methanol_sty_raw": raw[SUPPLEMENTARY[2]],
                "source_batch_label": payload["synthesis"].get("batch_label"),
                "original_paper_locator": payload["extraction"].get("original_excerpt"),
                "raw_fingerprint": digest(raw),
                "matched_input_group": "",
                "confirmed_repeat_group": "",
            }
        )

    rows.sort(key=lambda r: int(r["raw_locator"].split(":")[1].split("-")[0]))
    assert len(rows) == len({r["record_id"] for r in rows}) == 593
    assert len(partitions) == sum(bool(r["historical_partition"]) for r in rows) == 553
    groups = defaultdict(list)
    for row in rows:
        key = (row["composition"], *(row[f] for f in PROFILE[:4]))
        groups[key].append(row)

    exact_raw = [
        {
            "locators": locators,
            "frozen_record_ids": [frozen_raw[i] for i in locators if i in frozen_raw],
        }
        for locators in raw_groups.values()
        if len(locators) > 1
    ]
    matched = []
    candidates = []
    across_doi = []
    for group in groups.values():
        if len(group) < 2:
            continue
        group_id = f"same-input-{len(matched) + 1:03d}"
        matched.append({"id": group_id, "record_ids": [r["record_id"] for r in group]})
        for row in group:
            row["matched_input_group"] = group_id
        for left, right in combinations(group, 2):
            delta = abs(left["conversion_pct"] - right["conversion_pct"])
            same_doi = left["doi"] == right["doi"]
            same_specimen = specimen(left["sample_name"]) == specimen(right["sample_name"])
            if not same_doi:
                across_doi.append((left["raw_locator"], right["raw_locator"]))
            if delta == 0 or (same_specimen and same_doi and delta <= 0.1000000001):
                default_status = (
                    "identity_unresolved"
                    if same_specimen and same_doi
                    else "distinct_source_labels_reviewed"
                    if same_doi
                    else "cross_source_identity_unresolved"
                )
                status, note, source = PAPER_DISPOSITIONS.get(
                    (left["raw_locator"], right["raw_locator"]), (default_status, "", "")
                )
                candidates.append(
                    {
                        "matched_input_group": group_id,
                        "left_record_id": left["record_id"],
                        "right_record_id": right["record_id"],
                        "left_locator": left["raw_locator"],
                        "right_locator": right["raw_locator"],
                        "left_sample": left["sample_name"],
                        "right_sample": right["sample_name"],
                        "left_doi": left["doi"],
                        "right_doi": right["doi"],
                        "classification": left["classification"],
                        "exact_conversion_match": delta == 0,
                        "conversion_delta_pp": round(delta, 9),
                        "same_source_sample_label": same_specimen,
                        "both_common_eligible": bool(
                            left["historical_partition"] and right["historical_partition"]
                        ),
                        "different_secondary_fields": ";".join(
                            f
                            for f in (
                                "catalyst_load_g",
                                "surface_area_m2_g",
                                "pore_diameter_nm",
                                "methanol_selectivity_raw",
                                "methanol_yield_raw",
                                "methanol_sty_raw",
                            )
                            if left[f] != right[f]
                        ),
                        "disposition": status,
                        "review_note": note,
                        "review_source": source,
                    }
                )

    eligible = [r for r in rows if r["historical_partition"]]
    cu = [r for r in rows if r["classification"] == "cu"]
    cu_eligible = [r for r in eligible if r["classification"] == "cu"]
    pending = [p for p in candidates if p["disposition"].endswith("identity_unresolved")]
    pending_eligible = [p for p in pending if p["both_common_eligible"]]
    pending_ids = {p[key] for p in pending for key in ("left_record_id", "right_record_id")}
    for row in rows:
        row["repeat_identity_status"] = (
            "pending_candidate" if row["record_id"] in pending_ids else "no_confirmed_repeat"
        )
    summary = {
        "input_files": {k: {"path": FILES[k], "sha256": sha(v)} for k, v in blobs.items()},
        "script_sha256": sha(Path(__file__).read_bytes()),
        "snapshot_id": snapshot["snapshot_id"],
        "selection_id": selection["selection_id"],
        "source_raw_rows": len(source_rows),
        "population": {
            "frozen": distribution(rows),
            "eligible": distribution(eligible),
            "cu": distribution(cu),
            "eligible_cu": distribution(cu_eligible),
        },
        "identity_audit": {
            "exact_raw_duplicate_groups": exact_raw,
            "exact_raw_duplicates_inside_snapshot": sum(
                len(d["frozen_record_ids"]) > 1 for d in exact_raw
            ),
            "source_batch_labels_available": sum(bool(r["source_batch_label"]) for r in rows),
            "original_excerpts_available": sum(bool(r["original_paper_locator"]) for r in rows),
            "same_model_input_groups": len(matched),
            "same_model_input_rows": sum(len(g["record_ids"]) for g in matched),
            "cross_doi_same_model_input_pairs": len(across_doi),
            "screened_pair_counts": dict(Counter(p["disposition"] for p in candidates)),
            "same_conversion_pairs": sum(p["exact_conversion_match"] for p in candidates),
            "candidate_pairs": len(candidates),
            "unresolved_pairs_both_eligible": len(pending_eligible),
            "unresolved_rows_both_eligible": len(
                {p[key] for p in pending_eligible for key in ("left_record_id", "right_record_id")}
            ),
            "confirmed_repeat_groups_inside_snapshot": 0,
        },
    }
    return summary, rows, candidates, matched


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary, rows, candidates, matched = profile()
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "profile.json", summary)
    write_csv(args.output / "record-audit.csv", rows)
    write_csv(args.output / "candidate-pairs.csv", candidates)
    write_json(args.output / "same-input-groups.json", matched)


if __name__ == "__main__":
    main()
