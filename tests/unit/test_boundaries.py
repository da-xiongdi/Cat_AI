import copy

import pytest
from pydantic import ValidationError

from catalyst_ai.config import Settings
from catalyst_ai.governance.quality import govern
from catalyst_ai.schemas.domain import ImportRecord


def test_configurable_closure_tolerance(sample):
    sample["test"]["feed"][0]["amount"]["raw_value"] = "74.6"
    record = ImportRecord.model_validate(sample)
    assert "closure_failed" not in [i.code for i in govern(record, Settings())[1]]
    assert "closure_failed" in [
        i.code for i in govern(record, Settings(closure_tolerance_pct=0.1))[1]
    ]


@pytest.mark.parametrize(
    "missing",
    [
        "reference_temperature",
        "reference_pressure",
        "catalyst_volume_basis",
        "reference_pressure_type",
    ],
)
def test_partial_ghsv_basis_is_not_assumed(sample, missing):
    sample["test"]["ghsv_basis"].pop(missing)
    record, issues = govern(ImportRecord.model_validate(sample), Settings())
    assert "ghsv_basis_unknown" in [i.code for i in issues]
    assert record.test.ghsv.normalized_value is None


@pytest.mark.parametrize("family", ["Cu/ZnO/Al2O3", "ZnZrOx", "In2O3", "novel_open_system"])
def test_open_material_families(sample, family):
    sample["recipe"]["material_family"] = family
    assert ImportRecord.model_validate(sample).recipe.material_family == family


def test_characterization_stays_separate(sample):
    value = copy.deepcopy(sample["test"]["temperature"])
    value.update(raw_value="42", raw_unit="m2/g")
    sample["characterizations"] = [
        {
            "characterization_id": "demo-bet",
            "synthesis_id": "demo-syn-1",
            "technique": "synthetic_demo BET",
            "properties": {"specific_area": value},
        }
    ]
    record, _ = govern(ImportRecord.model_validate(sample), Settings())
    assert record.characterizations[0].properties["specific_area"].normalized_value == 42
    assert "specific_area" not in record.recipe.model_dump()
    sample["recipe"]["specific_area"] = value
    with pytest.raises(ValidationError):
        ImportRecord.model_validate(sample)


def test_imported_standard_values_do_not_override_raw(sample):
    sample["test"]["temperature"].update(normalized_value=9000, normalized_unit="K")
    record, issues = govern(ImportRecord.model_validate(sample), Settings())
    assert record.test.temperature.normalized_value == 523.15
    assert "imported_normalization_ignored" in [i.code for i in issues]


def test_foreign_id_mismatch_rejected(sample):
    sample["synthesis"]["recipe_id"] = "different"
    with pytest.raises(ValidationError, match="mismatch"):
        ImportRecord.model_validate(sample)


def test_ratio_is_not_implicitly_percent_and_negative_is_blocked(sample):
    sample["recipe"]["composition_basis"] = "ratio"
    for c in sample["recipe"]["components"]:
        c["amount"].update(raw_unit="1", raw_value="-1")
    _, issues = govern(ImportRecord.model_validate(sample), Settings())
    assert {"closure_not_assessable", "negative_composition", "ratio_zero_total"} <= {
        i.code for i in issues
    }
