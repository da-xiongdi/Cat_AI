import pytest

from catalyst_ai.config import Settings
from catalyst_ai.governance.quality import govern
from catalyst_ai.schemas.domain import ImportRecord


def evaluate(sample):
    return govern(ImportRecord.model_validate(sample), Settings())


def test_normalization_keeps_raw_and_does_not_derive(sample):
    record, issues = evaluate(sample)
    assert not any(i.severity == "block" for i in issues)
    assert record.test.temperature.raw_value == "250.00"
    assert record.test.temperature.normalized_value == 523.15
    assert record.test.pressure.raw_value == "3.0"
    assert record.test.pressure.normalized_value == 30
    assert [o.metric for o in record.observations] == ["co2_conversion", "methanol_selectivity"]


@pytest.mark.parametrize(
    "field,change,code",
    [
        ("temperature", {"raw_unit": "mystery"}, "unit_unknown"),
        ("temperature", {"raw_value": "-274"}, "physical_range"),
        ("pressure", {"raw_unit": "psi"}, "unit_unknown"),
        ("ghsv", {"raw_value": "-3"}, "physical_range"),
        ("temperature", {"raw_value": "NaN"}, "invalid_number"),
        ("temperature", {"raw_value": "0"}, "zero_state_mismatch"),
    ],
)
def test_invalid_units_and_values(sample, field, change, code):
    sample["test"][field].update(change)
    _, issues = evaluate(sample)
    assert code in [i.code for i in issues]


def test_missing_and_unknown_pressure_basis(sample):
    sample["test"]["temperature"] = {"state": "not_reported"}
    sample["test"]["pressure_type"] = "gauge"
    sample["test"]["ghsv_basis"] = None
    record, issues = evaluate(sample)
    assert record.test.temperature.normalized_value is None
    assert record.test.pressure.normalized_value is None
    assert record.test.ghsv.normalized_value is None
    assert {"critical_value_missing", "pressure_basis_unknown", "ghsv_basis_unknown"} <= {
        i.code for i in issues
    }


def test_percentages_and_closure(sample):
    sample["observations"][0]["value"]["raw_value"] = "110"
    sample["recipe"]["components"][0]["amount"]["raw_value"] = "25"
    sample["test"]["feed"][0]["amount"]["raw_value"] = "20"
    _, issues = evaluate(sample)
    assert "percentage_range" in [i.code for i in issues]
    assert len([i for i in issues if i.code == "closure_failed"]) == 2


def test_source_and_review_not_trusted(sample):
    sample["source"] = None
    sample["extraction"] = None
    sample["observations"][0]["value"]["extraction_status"] = "verified"
    _, issues = evaluate(sample)
    assert {"source_missing", "locator_missing", "untrusted_review"} <= {i.code for i in issues}


def test_metric_definition_required(sample):
    sample["observations"][1]["value"]["definition"] = None
    _, issues = evaluate(sample)
    assert "metric_definition_missing" in [i.code for i in issues]
