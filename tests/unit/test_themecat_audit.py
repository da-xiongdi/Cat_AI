import csv
import io
import json

import pytest

from catalyst_ai.sources.themecat import COLUMNS
from scripts.validate_themecat import EXPECTED_COLS, audit, main


def content(*rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


def record(**changes):
    return dict(dict.fromkeys(COLUMNS, "NA"), **changes)


def test_audit_counts_raw_rows_before_coercion_and_keeps_physical_locations():
    first = record(CO2_conversion="1", reference="Example\ncontinued")
    second = record(CO2_conversion="1.0", reference="Example\ncontinued")
    summary, profiles, diagnostics = audit(
        content(first, second, first, dict.fromkeys(COLUMNS, ""))
    )
    assert EXPECTED_COLS == COLUMNS
    assert summary["csv_records_after_header"] == 4
    assert summary["nonempty_rows"] == 3
    assert summary["empty_rows"] == 1
    assert summary["exact_raw_duplicates"] == 1
    assert diagnostics[0]["input_locator"] == "lines:6-7"
    assert json.loads(diagnostics[0]["details"])["first_locator"] == "lines:2-3"
    assert next(p for p in profiles if p["column"] == "CO2_conversion")["raw_present_count"] == 3


def test_invalid_is_distinct_from_missing_and_never_serializes_nonfinite_values():
    summary, profiles, diagnostics = audit(
        content(
            record(
                temperature_k="NaN",
                pressure_bar="inf",
                GHSV_nlph_gcat="-1",
                CO2_conversion="bad",
                selectivity_CH3OH="NA",
            )
        )
    )
    assert summary["diagnostic_counts"]["numeric_invalid"] == 3
    assert summary["diagnostic_counts"]["numeric_range_candidate"] == 1
    by_name = {p["column"]: p for p in profiles}
    assert by_name["CO2_conversion"]["missing_count"] == 0
    assert by_name["CO2_conversion"]["numeric_invalid_count"] == 1
    assert by_name["selectivity_CH3OH"]["missing_count"] == 1
    json.dumps([summary, profiles, diagnostics], allow_nan=False)


def test_relations_are_opt_in_and_incomplete_compositions_are_not_closed():
    raw = content(
        record(
            catalyst_composition_available="Yes",
            active_comp_1="Cu",
            active_1_percent="50",
            support_comp_1="ZnO",
            CO2_conversion="10",
            selectivity_CH3OH="50",
            yield_CH3OH="9",
            STY_g_per_gcath="1",
            GHSV_nlph_gcat="4",
            pH2_pCO2_ratio="3",
        )
    )
    default, _, _ = audit(raw)
    assert default["relation_checks"]["status"] == "not_run"
    summary, _, diagnostics = audit(raw, check_relations=True)
    checks = summary["relation_checks"]
    assert checks["status"] == "diagnostic_only"
    assert checks["results"]["composition_sum"]["compared_rows"] == 0
    assert checks["results"]["yield_relation"]["flagged_rows"] == 1
    assert checks["results"]["sty_relation"]["compared_rows"] == 1
    assert summary["scientific_use"] is False
    assert summary["approves_records"] is False
    assert all("not_row_verified" in d["details"] for d in diagnostics)


def test_report_cli_preserves_source_and_refuses_overwrite_or_raw_directory(tmp_path):
    source = tmp_path / "raw" / "input.csv"
    source.parent.mkdir()
    raw = content(record(CO2_conversion="0"))
    source.write_bytes(raw)
    output = tmp_path / "reports" / "new"
    assert main(["--input", str(source), "--output", str(output)]) == 2
    original = (output / "quality_summary.json").read_bytes()
    with pytest.raises(SystemExit, match="1"):
        main(["--input", str(source), "--output", str(output)])
    assert (output / "quality_summary.json").read_bytes() == original
    unsafe = source.parent / "reports"
    with pytest.raises(SystemExit, match="1"):
        main(["--input", str(source), "--output", str(unsafe)])
    assert not unsafe.exists()
    assert source.read_bytes() == raw


def test_schema_errors_do_not_create_output(tmp_path):
    source = tmp_path / "wrong.csv"
    source.write_bytes(b"wrong,header\n1,2\n")
    output = tmp_path / "reports"
    with pytest.raises(SystemExit, match="1"):
        main(["--input", str(source), "--output", str(output)])
    assert not output.exists()


def test_relation_preserves_raw_precision_and_extreme_ratios_remain_json_safe():
    summary, profiles, diagnostics = audit(
        content(
            record(
                CO2_conversion="1e-318",
                selectivity_CH3OH="100",
                yield_CH3OH="100.00",
            )
        ),
        check_relations=True,
    )
    comparison = next(d for d in diagnostics if d["field"] == "yield_CH3OH")
    assert comparison["raw_value"] == "100.00"
    assert json.loads(comparison["details"])["relative_difference"] is None
    json.dumps([summary, profiles, diagnostics], allow_nan=False)
