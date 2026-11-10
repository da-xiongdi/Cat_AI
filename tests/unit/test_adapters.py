import json

import pytest

from catalyst_ai.sources.files import read_rows


def test_json_bom_and_nonobject_rows():
    rows = read_rows(b"\xef\xbb\xbf[null, 3]", ".json")
    assert [r.locator for r in rows] == ["$[0]", "$[1]"]


@pytest.mark.parametrize("payload", [b"{}", b"[{", b'[{"a":1,"a":2}]', b"[NaN]"])
def test_invalid_json_rejected(payload):
    with pytest.raises(ValueError):
        read_rows(payload, ".json")


def test_invalid_csv_headers_and_nested_cells():
    with pytest.raises(ValueError, match="CSV列"):
        read_rows(b"source,source\n1,2", ".csv")
    fields = [
        "schema_version",
        "dataset_kind",
        "source",
        "extraction",
        "recipe",
        "synthesis",
        "test",
        "observations",
        "characterizations",
    ]
    rows = read_rows(
        (",".join(fields) + "\n1,synthetic_demo,bad,null,{},{},{},[],[]").encode(), ".csv"
    )
    assert rows[0].error
    assert rows[0].payload["dataset_kind"] == "synthetic_demo"


def test_json_raw_number_must_be_text(sample):
    from pydantic import ValidationError

    from catalyst_ai.schemas.domain import ImportRecord

    sample["test"]["temperature"]["raw_value"] = 250
    with pytest.raises(ValidationError):
        ImportRecord.model_validate(json.loads(json.dumps(sample)))
