"""Parse prototype CSV files without changing either workbench or domain data."""

import csv
import io
import math

FIELDS = (
    "id",
    "name",
    "origin",
    "sourceId",
    "family",
    "composition",
    "support",
    "method",
    "calcination",
    "temp",
    "pressure",
    "ghsv",
    "feed",
    "conv",
    "sel",
    "sty",
    "replicates",
    "status",
    "notes",
)
NUMERIC = ("calcination", "temp", "pressure", "ghsv", "conv", "sel", "sty", "replicates")
DOMAIN_MAPPING = {
    "id": "TestRun.test_id",
    "name": "staging.name",
    "origin": "staging.origin",
    "sourceId": "ExtractionRecord.source_id",
    "family": "Recipe.material_family",
    "composition": "Recipe.components",
    "support": "Recipe.supports",
    "method": "SynthesisRun.route",
    "calcination": "SynthesisRun.steps[].parameters.calcination_c",
    "temp": "TestRun.temperature",
    "pressure": "TestRun.pressure",
    "ghsv": "TestRun.ghsv",
    "feed": "TestRun.feed",
    "conv": "Observation[co2_conversion].value",
    "sel": "Observation[methanol_selectivity].value",
    "sty": "Observation[methanol_sty].value",
    "replicates": "extension.replicate_n",
    "status": "staging.original_status",
    "notes": "ExtractionRecord.locator",
}


def preview_csv(content: bytes) -> dict:
    """Return raw rows, validation findings and conservative duplicate hints.

    CSV values remain strings: units and missing values must be reviewed before
    any domain import. The parser never interprets prototype status as approval.
    """
    try:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        header = reader.fieldnames
        if not header or len(header) != len(set(header)) or set(header) != set(FIELDS):
            raise ValueError("CSV header must contain exactly the prototype fields")
        rows = []
        seen = {}
        seen_ids = set()
        for record in reader:
            line = reader.line_num
            if None in record or any(value is None for value in record.values()):
                raise ValueError(f"CSV column count mismatch at line {line}")
            errors, warnings = [], []
            if not record["name"].strip():
                errors.append({"field": "name", "message": "缺少名称"})
            if not record["sourceId"].strip():
                errors.append({"field": "sourceId", "message": "缺少来源"})
            record_id = record["id"].strip()
            if record_id and record_id in seen_ids:
                errors.append({"field": "id", "message": "导入文件内 ID 重复"})
            seen_ids.add(record_id)
            for field in NUMERIC:
                value = record[field].strip()
                if not value:
                    continue
                try:
                    number = float(value)
                    if not math.isfinite(number):
                        raise ValueError
                    if field == "replicates" and (number < 1 or not number.is_integer()):
                        raise ValueError
                    if field in ("conv", "sel") and not 0 <= number <= 100:
                        raise ValueError
                except ValueError:
                    errors.append({"field": field, "message": "无效数值"})
            for field in ("temp", "pressure", "ghsv"):
                if record[field].strip():
                    warnings.append({"field": field, "message": "需核对单位及基准"})
            key = tuple(
                record[field].strip().casefold()
                for field in ("sourceId", "name", "composition", "temp", "pressure", "ghsv", "feed")
            )
            if any(key) and key in seen:
                warnings.append({"field": "", "message": f"疑似与第 {seen[key]} 行重复"})
            elif any(key):
                seen[key] = line
            rows.append(
                {
                    "line": line,
                    "raw": record,
                    "status": "待治理",
                    "errors": errors,
                    "warnings": warnings,
                }
            )
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError(f"invalid UTF-8 CSV: {exc}") from exc
    return {
        "rows": rows,
        "valid": all(not row["errors"] for row in rows),
        "field_mapping": DOMAIN_MAPPING,
    }
