import csv
import io
import json
from dataclasses import dataclass


@dataclass
class InputRow:
    locator: str
    payload: object
    error: str | None = None
    raw_payload: object | None = None


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"JSON键重复: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"JSON非有限常量不允许: {value}")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant)


def read_rows(content: bytes, suffix: str) -> list[InputRow]:
    text = content.decode("utf-8-sig")
    if suffix.lower() == ".json":
        payload = strict_json(text)
        if not isinstance(payload, list):
            raise ValueError("JSON顶层必须为记录数组；每项必须显式标记dataset_kind")
        return [InputRow(f"$[{i}]", item) for i, item in enumerate(payload)]
    if suffix.lower() != ".csv":
        raise ValueError("只支持UTF-8 CSV/JSON")
    stream = io.StringIO(text, newline="")
    reader = csv.DictReader(stream, strict=True)
    expected = {
        "schema_version",
        "dataset_kind",
        "source",
        "extraction",
        "recipe",
        "synthesis",
        "test",
        "observations",
        "characterizations",
    }
    headers = reader.fieldnames or []
    if len(headers) != len(set(headers)) or set(headers) != expected:
        raise ValueError("CSV列必须唯一并严格匹配数据契约；见docs/data_dictionary.md")
    rows = []
    while True:
        start = reader.line_num + 1
        try:
            row = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            raise ValueError(f"CSV结构无法解析，行{reader.line_num}: {exc}") from exc
        locator = f"lines:{start}-{reader.line_num}"
        original = row.copy()
        try:
            if None in row or any(v is None for v in row.values()):
                raise ValueError("CSV字段数不匹配")
            for key in sorted(expected - {"schema_version", "dataset_kind"}):
                row[key] = strict_json(row[key])
            rows.append(InputRow(locator, row))
        except (ValueError, TypeError) as exc:
            rows.append(InputRow(locator, original, str(exc)))
    return rows
