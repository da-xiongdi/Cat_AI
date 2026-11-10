#!/usr/bin/env python3
"""Read-only audit for the official TheMeCat v1 CSV.

Usage:
    python validate_themecat.py --input data/raw/TheMeCat_v1.csv --output reports/data_quality

Requires pandas. Produces JSON + CSV audit reports. Does not modify source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

EXPECTED_COLS = [
    "reference", "doi_link", "catalyst_name", "catalyst_composition_available",
    "starting_material_active_1", "active_comp_1", "active_1_percent",
    "starting_material_2", "active_comp_2", "active_2_percent",
    "support_comp_1", "support_1_percent", "support_comp_2", "support_2_percent",
    "catalyst_surface_area_m2_g", "mean_pore_diameter_nm", "temperature_k",
    "pressure_bar", "pH2_pCO2_ratio", "GHSV_nlph_gcat", "catalyst_load_g",
    "CO2_conversion", "selectivity_CH3OH", "yield_CH3OH", "STY_g_per_gcath",
]
NUMERIC = [
    "active_1_percent", "active_2_percent", "support_1_percent", "support_2_percent",
    "catalyst_surface_area_m2_g", "mean_pore_diameter_nm", "temperature_k",
    "pressure_bar", "pH2_pCO2_ratio", "GHSV_nlph_gcat", "catalyst_load_g",
    "CO2_conversion", "selectivity_CH3OH", "yield_CH3OH", "STY_g_per_gcath",
]
ZENODO_MD5 = "a0328d6773e0750ff8096a7c4e4e723e"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit TheMeCat CSV without modifying raw data")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", default=Path("reports/data_quality"), type=Path)
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"CSV not found: {args.input}. Download TheMeCat_v1.csv from Zenodo first.")
    args.output.mkdir(parents=True, exist_ok=True)

    file_bytes = args.input.read_bytes()
    source_md5 = hashlib.md5(file_bytes).hexdigest()
    df = pd.read_csv(args.input, encoding="utf-8-sig", low_memory=False)
    df.columns = [str(col).strip() for col in df.columns]
    missing_cols = [c for c in EXPECTED_COLS if c not in df.columns]
    extra_cols = [c for c in df.columns if c not in EXPECTED_COLS]
    for field in NUMERIC:
        if field in df.columns:
            df[field] = pd.to_numeric(df[field], errors="coerce")

    field_table = pd.DataFrame({
        "column": df.columns,
        "dtype": [str(df[c].dtype) for c in df.columns],
        "non_null_count": [int(df[c].notna().sum()) for c in df.columns],
        "null_count": [int(df[c].isna().sum()) for c in df.columns],
        "null_fraction": [float(df[c].isna().mean()) for c in df.columns],
        "unique_nonnull": [int(df[c].nunique(dropna=True)) for c in df.columns],
    })
    field_table.to_csv(args.output / "column_quality.csv", index=False, encoding="utf-8-sig")

    boundaries = {}
    for col in NUMERIC:
        if col in df.columns:
            series = df[col].dropna()
            boundaries[col] = {"count": int(len(series)), "min": float(series.min()) if len(series) else None,
                               "max": float(series.max()) if len(series) else None}

    composition_cols = ["active_1_percent", "active_2_percent", "support_1_percent", "support_2_percent"]
    composition_check = None
    if all(c in df.columns for c in composition_cols):
        counts = df[composition_cols].notna().sum(axis=1)
        sums = df[composition_cols].sum(axis=1, min_count=1)
        assessable = counts > 0
        comp_issues = assessable & ((sums - 100).abs() > 1.0)
        composition_check = {
            "rows_with_any_composition_percent": int(assessable.sum()),
            "rows_with_sum_outside_100_plus_minus_1_molpercent": int(comp_issues.sum()),
        }

    yield_check = None
    if all(c in df.columns for c in ["CO2_conversion", "selectivity_CH3OH", "yield_CH3OH"]):
        derived = df["CO2_conversion"] * df["selectivity_CH3OH"] / 100
        discrepancy = (df["yield_CH3OH"] - derived).abs()
        valid = discrepancy.notna()
        yield_check = {
            "comparable_rows": int(valid.sum()),
            "rows_absolute_difference_above_0_5_percentage_points": int((discrepancy[valid] > 0.5).sum()),
            "maximum_absolute_difference_percentage_points": float(discrepancy[valid].max()) if valid.any() else None,
        }

    sty_check = None
    sty_fields = ["STY_g_per_gcath", "GHSV_nlph_gcat", "yield_CH3OH", "pH2_pCO2_ratio"]
    if all(c in df.columns for c in sty_fields):
        molar_volume = 8.314462618 * 293.15 / 101325 * 1000  # L/mol
        y = df["yield_CH3OH"] / 100
        denominator = 1 + df["pH2_pCO2_ratio"]
        expected_sty = df["GHSV_nlph_gcat"] * y * 32.04 / molar_volume / denominator
        expected_sty = expected_sty.where(denominator > 0)
        discrepancy = (df["STY_g_per_gcath"] - expected_sty).abs()
        valid = discrepancy.notna()
        sty_check = {
            "comparable_rows": int(valid.sum()),
            "rows_absolute_difference_above_0_01_g_per_gcat_h": int((discrepancy[valid] > 0.01).sum()),
            "maximum_absolute_difference_g_per_gcat_h": float(discrepancy[valid].max()) if valid.any() else None,
            "note": "Potential differences need source-level review. Do not overwrite reported values.",
        }

    numeric_issues = {}
    for col in ["CO2_conversion", "selectivity_CH3OH", "yield_CH3OH"]:
        if col in df:
            numeric_issues[col] = int(((df[col] < 0) | (df[col] > 100)).sum())
    for col in ["temperature_k", "pressure_bar", "GHSV_nlph_gcat", "catalyst_load_g"]:
        if col in df:
            numeric_issues[col + "_nonpositive"] = int((df[col] <= 0).sum())

    report = {
        "source_file": str(args.input),
        "sha256": hashlib.sha256(file_bytes).hexdigest(),
        "md5": source_md5,
        "md5_matches_zenodo_v1_listing": source_md5 == ZENODO_MD5,
        "row_count": int(len(df)),
        "matches_paper_reported_822_rows": len(df) == 822,
        "column_count": int(df.shape[1]),
        "expected_columns_missing": missing_cols,
        "unexpected_columns": extra_cols,
        "unique_doi_links": int(df["doi_link"].nunique(dropna=True)) if "doi_link" in df else None,
        "full_row_duplicates": int(df.duplicated().sum()),
        "numeric_ranges": boundaries,
        "composition_sum_check": composition_check,
        "yield_relation_check": yield_check,
        "sty_relation_check": sty_check,
        "basic_range_issues": numeric_issues,
        "warning": "Audit is descriptive only; all flagged values require source-level checks.",
    }
    (args.output / "quality_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ["row_count", "column_count", "unique_doi_links", "full_row_duplicates", "md5_matches_zenodo_v1_listing", "expected_columns_missing", "unexpected_columns"]}, ensure_ascii=False, indent=2))
    print(f"Audit reports saved to: {args.output.resolve()}")


if __name__ == "__main__":
    main()
