import csv

import pytest

from catalyst_ai.ingest import ingest
from catalyst_ai.sources.themecat import COLUMNS, adapt
from catalyst_ai.storage.db import transaction
from catalyst_ai.storage.models import StagedRow


def test_themecat_stages_raw_rows_and_blocks_duplicates(tmp_path, settings):
    path = tmp_path / "input.csv"
    raw = dict.fromkeys(COLUMNS, "NA")
    raw.update(
        reference="Example (2020)",
        doi_link="https://doi.org/10.1/example",
        catalyst_name="demo",
        active_comp_1="Cu",
        active_1_percent="50",
        temperature_k="500",
        pressure_bar="10",
        GHSV_nlph_gcat="3",
        CO2_conversion="0",
    )
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerow(raw)
        writer.writerow(raw)
        writer.writerow(dict.fromkeys(COLUMNS, ""))
    report = ingest(path, settings, adapter="themecat-v1")
    assert report["counts"] == {"total": 2, "curated": 0, "staged": 1, "duplicate": 1}
    assert report["skipped_empty_rows"] == 1
    assert report["rows"][0]["input_locator"] == "lines:2-2"
    assert {"pressure_basis_unknown", "ghsv_basis_unknown", "metric_definition_missing"} <= {
        i["code"] for i in report["rows"][0]["issues"]
    }
    with transaction(settings.database) as session:
        row = session.get(StagedRow, report["rows"][0]["record_id"])
        assert row.raw_payload == raw
        assert row.payload["test"]["ghsv"]["raw_unit"] == "NL/g_cat/h"
        assert row.payload["observations"][0]["value"]["state"] == "zero"
        assert row.payload["test"]["pressure"]["normalized_value"] is None
    again = ingest(path, settings, adapter="themecat-v1", dry_run=True)
    assert again["counts"]["duplicate"] == 2


def test_themecat_rejects_unrecognized_header():
    with pytest.raises(ValueError, match="CSV列不匹配"):
        adapt(b"wrong,header\n1,2\n")


def test_v2_replay_keeps_original_fingerprint_duplicate(tmp_path, settings):
    path = tmp_path / "input.csv"
    raw = dict.fromkeys(COLUMNS, "NA")
    raw.update(
        reference="paper", catalyst_name="sample", active_comp_1="Cu", active_1_percent="100"
    )
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerow(raw)
    ingest(path, settings, adapter="themecat-v1")
    report = ingest(path, settings, adapter="themecat-v2", dry_run=True)
    assert report["counts"]["duplicate"] == 1
    assert report["rows"][0]["semantic_rule_version"] == "2"
