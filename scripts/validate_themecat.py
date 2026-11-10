#!/usr/bin/env python3
"""Profile TheMeCat v1 without changing raw data or approving research records.

The supplied pandas script is preserved in docs/references/themecat/.
This repository version uses the standard library, preserves raw duplicate
semantics and physical line locations, and refuses to overwrite reports.
Formula diagnostics require --check-relations and never produce training labels.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from collections import Counter
from pathlib import Path

EXPECTED_COLS = [
    "reference",
    "doi_link",
    "catalyst_name",
    "catalyst_composition_available",
    "starting_material_active_1",
    "active_comp_1",
    "active_1_percent",
    "starting_material_2",
    "active_comp_2",
    "active_2_percent",
    "support_comp_1",
    "support_1_percent",
    "support_comp_2",
    "support_2_percent",
    "catalyst_surface_area_m2_g",
    "mean_pore_diameter_nm",
    "temperature_k",
    "pressure_bar",
    "pH2_pCO2_ratio",
    "GHSV_nlph_gcat",
    "catalyst_load_g",
    "CO2_conversion",
    "selectivity_CH3OH",
    "yield_CH3OH",
    "STY_g_per_gcath",
]
NUMERIC = [
    "active_1_percent",
    "active_2_percent",
    "support_1_percent",
    "support_2_percent",
    "catalyst_surface_area_m2_g",
    "mean_pore_diameter_nm",
    "temperature_k",
    "pressure_bar",
    "pH2_pCO2_ratio",
    "GHSV_nlph_gcat",
    "catalyst_load_g",
    "CO2_conversion",
    "selectivity_CH3OH",
    "yield_CH3OH",
    "STY_g_per_gcath",
]
ZENODO_MD5 = "a0328d6773e0750ff8096a7c4e4e723e"
COMPONENTS = [
    ("active_comp_1", "active_1_percent"),
    ("active_comp_2", "active_2_percent"),
    ("support_comp_1", "support_1_percent"),
    ("support_comp_2", "support_2_percent"),
]
PERCENTAGES = {"CO2_conversion", "selectivity_CH3OH", "yield_CH3OH"} | {
    amount for _, amount in COMPONENTS
}
POSITIVE = {"temperature_k", "pressure_bar", "GHSV_nlph_gcat", "catalyst_load_g"}


def missing(value):
    return value.strip().upper() in {"", "NA"}


def number(value):
    if missing(value):
        return None
    try:
        result = float(value)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def audit(content, *, check_relations=False):
    """Return summary, column profile and row diagnostics; no I/O or approvals."""
    reader = csv.reader(io.StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
    if next(reader, None) != EXPECTED_COLS:
        raise ValueError("TheMeCat v1 CSV列或顺序不匹配；拒绝静默修复表头")
    rows, empty, diagnostics, seen = [], 0, [], {}
    records = 0
    while True:
        start = reader.line_num + 1
        fields = next(reader, None)
        if fields is None:
            break
        records += 1
        locator = f"lines:{start}-{reader.line_num}"
        if not any(value.strip() for value in fields):
            empty += 1
            continue
        if len(fields) != len(EXPECTED_COLS):
            raise ValueError(f"字段数不匹配: {locator}")
        rows.append((locator, dict(zip(EXPECTED_COLS, fields, strict=True))))

    def flag(locator, row, code, field, raw_value, **details):
        diagnostics.append(
            {
                "input_locator": locator,
                "doi_link": row["doi_link"],
                "catalyst_name": row["catalyst_name"],
                "code": code,
                "field": field,
                "raw_value": raw_value,
                "details": json.dumps(details, ensure_ascii=False, allow_nan=False),
            }
        )

    profiles = []
    for column in EXPECTED_COLS:
        values = [row[column] for _, row in rows]
        present = [v for v in values if not missing(v)]
        parsed = [number(v) for v in present] if column in NUMERIC else []
        finite = [v for v in parsed if v is not None]
        profiles.append(
            {
                "column": column,
                "nonempty_rows": len(rows),
                "raw_present_count": len(present),
                "missing_count": len(values) - len(present),
                "missing_fraction": (len(values) - len(present)) / len(rows) if rows else None,
                "unique_raw_nonmissing": len(set(present)),
                "numeric_valid_count": len(finite) if column in NUMERIC else None,
                "numeric_invalid_count": len(parsed) - len(finite) if column in NUMERIC else None,
                "min": min(finite, default=None),
                "max": max(finite, default=None),
            }
        )

    relations = {
        name: {"compared_rows": 0, "flagged_rows": 0}
        for name in ("composition_sum", "yield_relation", "sty_relation")
    }

    def compare(name, locator, row, field, reported, expected, threshold):
        if not math.isfinite(expected):
            flag(locator, row, "relation_nonfinite", field, str(reported), relation=name)
            return
        discrepancy = abs(reported - expected)
        if not math.isfinite(discrepancy):
            flag(locator, row, "relation_nonfinite", field, str(reported), relation=name)
            return
        relations[name]["compared_rows"] += 1
        flagged = discrepancy > threshold
        relations[name]["flagged_rows"] += int(flagged)
        relative = discrepancy / abs(expected) if expected else None
        if relative is not None and not math.isfinite(relative):
            relative = None
        raw_value = (
            row[field]
            if field in row
            else json.dumps({amount: row[amount] for _, amount in COMPONENTS}, ensure_ascii=False)
        )
        flag(
            locator,
            row,
            name + ("_candidate" if flagged else "_comparison"),
            field,
            raw_value,
            expected=expected,
            absolute_difference=discrepancy,
            relative_difference=relative,
            threshold=threshold,
            evidence_scope="dataset_definition_assumed_not_row_verified",
        )

    for locator, row in rows:
        key = tuple(row.values())
        if key in seen:
            flag(locator, row, "exact_raw_duplicate", "$", "", first_locator=seen[key])
        else:
            seen[key] = locator
        nums = {field: number(row[field]) for field in NUMERIC}
        invalid = set()
        for field, value in nums.items():
            if value is None:
                if not missing(row[field]):
                    flag(locator, row, "numeric_invalid", field, row[field])
                invalid.add(field)
                continue
            bad = (
                (field in PERCENTAGES and not 0 <= value <= 100)
                or (field in POSITIVE and value <= 0)
                or value < 0
            )
            if bad:
                invalid.add(field)
                flag(locator, row, "numeric_range_candidate", field, row[field])
        if not check_relations:
            continue
        amounts = []
        complete = row["catalyst_composition_available"].strip().lower() == "yes"
        for species, amount in COMPONENTS:
            if not missing(row[species]):
                complete = complete and amount not in invalid
                if amount not in invalid:
                    amounts.append(nums[amount])
            elif not missing(row[amount]):
                complete = False
        if complete and amounts:
            compare("composition_sum", locator, row, "components", sum(amounts), 100.0, 0.5)
        targets = {"CO2_conversion", "selectivity_CH3OH", "yield_CH3OH"}
        if not targets & invalid:
            compare(
                "yield_relation",
                locator,
                row,
                "yield_CH3OH",
                nums["yield_CH3OH"],
                nums["CO2_conversion"] * nums["selectivity_CH3OH"] / 100,
                0.5,
            )
        sty_fields = {"STY_g_per_gcath", "GHSV_nlph_gcat", "yield_CH3OH", "pH2_pCO2_ratio"}
        if not sty_fields & invalid:
            molar_volume = 8.314462618 * 293.15 / 101325 * 1000
            expected = (
                nums["GHSV_nlph_gcat"]
                / (1 + nums["pH2_pCO2_ratio"])
                * (nums["yield_CH3OH"] / 100)
                * (32.04 / molar_volume)
            )
            compare(
                "sty_relation",
                locator,
                row,
                "STY_g_per_gcath",
                nums["STY_g_per_gcath"],
                expected,
                0.01,
            )
    counts = Counter(item["code"] for item in diagnostics)
    summary = {
        "schema_version": "themecat-audit-1",
        "sha256": hashlib.sha256(content).hexdigest(),
        "md5": hashlib.md5(content).hexdigest(),
        "md5_matches_zenodo_v1_listing": hashlib.md5(content).hexdigest() == ZENODO_MD5,
        "column_count": len(EXPECTED_COLS),
        "csv_records_after_header": records,
        "nonempty_rows": len(rows),
        "empty_rows": empty,
        "unique_doi_links_raw": len({r["doi_link"] for _, r in rows if not missing(r["doi_link"])}),
        "exact_raw_duplicates": len(rows) - len(seen),
        "paper_reported": {"rows": 822, "papers": 44},
        "paper_counts_reconciled": False,
        "diagnostic_counts": dict(sorted(counts.items())),
        "relation_checks": {
            "status": "diagnostic_only" if check_relations else "not_run",
            "assumptions": "material-component mol%; reactant-only mass-normalized flow; "
            "293.15 K, 101325 Pa; compatible X/S/Y definitions",
            "results": relations,
            "thresholds_are_research_gates": False,
        },
        "scientific_use": False,
        "approves_records": False,
        "warning": "Descriptive audit only. Dataset definitions are not row-level verification. "
        "All original rows, including duplicates, remain in profile denominators.",
    }
    return summary, profiles, diagnostics


def write_csv(path, rows, fields):
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="新的报告目录；拒绝覆盖")
    parser.add_argument("--check-relations", action="store_true", help="仅作假设性公式诊断")
    args = parser.parse_args(argv)
    try:
        summary, profiles, diagnostics = audit(
            args.input.read_bytes(), check_relations=args.check_relations
        )
        summary["source_file"] = str(args.input.resolve())
        summary["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        input_resolved, output_resolved = args.input.resolve(), args.output.resolve()
        if (
            output_resolved == input_resolved.parent
            or output_resolved in input_resolved.parents
            or input_resolved.parent in output_resolved.parents
        ):
            raise ValueError("报告目录须与原件所在目录分离")
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / "quality_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        write_csv(args.output / "column_quality.csv", profiles, list(profiles[0]))
        write_csv(
            args.output / "row_diagnostics.csv",
            diagnostics,
            [
                "input_locator",
                "doi_link",
                "catalyst_name",
                "code",
                "field",
                "raw_value",
                "details",
            ],
        )
    except (OSError, ValueError, csv.Error) as exc:
        parser.exit(1, f"审计失败: {exc}\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if summary["md5_matches_zenodo_v1_listing"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
