import csv
import io

import pytest

from catalyst_ai.workbench.csv_preview import FIELDS, preview_csv


def test_csv_preview_preserves_multiline_and_flags_invalid_and_duplicate():
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerow({"id": "1", "name": "催化剂", "notes": "第一行\n第二行", "conv": "NaN"})
    writer.writerow({"id": "2", "name": "催化剂", "pressure": "1"})
    writer.writerow({"id": "3", "name": "催化剂", "pressure": "1"})
    result = preview_csv(output.getvalue().encode("utf-8-sig"))
    assert not result["valid"]
    assert result["rows"][0]["raw"]["notes"] == "第一行\n第二行"
    assert any(error["field"] == "conv" for error in result["rows"][0]["errors"])
    assert any("重复" in warning["message"] for warning in result["rows"][2]["warnings"])


def test_csv_rejects_wrong_header():
    with pytest.raises(ValueError, match="header"):
        preview_csv(b"id,name\n1,test\n")
