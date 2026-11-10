import csv
import io

from catalyst_ai.config import Settings
from catalyst_ai.governance.quality import govern
from catalyst_ai.schemas.domain import ImportRecordV2
from catalyst_ai.sources.themecat import COLUMNS, adapt_v2


def make_record(**changes):
    raw = dict.fromkeys(COLUMNS, "NA")
    raw.update(
        reference="paper",
        doi_link="https://doi.org/10.1/example",
        catalyst_name="sample",
        catalyst_composition_available="Yes",
        starting_material_active_1="CuO",
        active_comp_1="Cu",
        active_1_percent="100",
        temperature_k="500",
        pressure_bar="10",
        pH2_pCO2_ratio="3",
        GHSV_nlph_gcat="5",
    )
    raw.update(changes)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerow(raw)
    row = adapt_v2(stream.getvalue().encode())[0][0]
    return row, ImportRecordV2.model_validate(row.payload)


def test_v2_preserves_semantic_layers_and_unknown_pressure():
    row, record = make_record()
    governed, issues = govern(record, Settings())
    codes = {i.code for i in issues}
    assert governed.synthesis.initial_materials == ["CuO"]
    assert governed.synthesis.precursors == []
    assert governed.recipe.composition_basis == "mol_pct"
    assert governed.test.mass_normalized_volume_flow.value.normalized_unit == "NL/g_cat/h"
    assert governed.test.ghsv.normalized_value is None
    assert governed.test.reactant_ratio.value.normalized_value == 3
    assert "pressure_basis_unknown" in codes and "metric_definition_missing" in codes
    assert "full_feed_not_reported" in codes
    assert not {"ghsv_basis_unknown", "composition_missing"} & codes
    assert row.raw_payload["starting_material_active_1"] == "CuO"
    assert "dataset paper" in governed.test.mass_normalized_volume_flow.definition_source


def test_v2_missing_flow_basis_and_ratio_block_without_converting_units():
    _, record = make_record(pH2_pCO2_ratio="NA")
    record.test.mass_normalized_volume_flow.mass_basis = "unknown"
    governed, issues = govern(record, Settings())
    assert {"mass_flow_basis_unknown", "critical_value_missing"} <= {i.code for i in issues}
    assert governed.test.mass_normalized_volume_flow.value.normalized_value is None
    assert governed.test.ghsv.normalized_value is None


def test_v2_composition_availability_and_orphan_block():
    _, record = make_record(catalyst_composition_available="No", support_1_percent="5")
    _, issues = govern(record, Settings())
    assert {"composition_availability_unconfirmed", "orphan_composition_amount"} <= {
        i.code for i in issues
    }


def test_v2_valid_mass_mode_does_not_relax_other_blocks():
    _, record = make_record(
        CO2_conversion="10", selectivity_CH3OH="20", yield_CH3OH="2", STY_g_per_gcath="0.1"
    )
    record.test.pressure_type = "absolute"
    for observation in record.observations:
        observation.value.definition = "explicit source definition"
    governed, issues = govern(record, Settings())
    assert not [issue for issue in issues if issue.severity == "block"]
    assert governed.test.mass_normalized_volume_flow.value.normalized_unit == "NL/g_cat/h"
    record.test.mass_normalized_volume_flow.value.raw_unit = "h^-1"
    _, issues = govern(record, Settings())
    assert any(i.code == "unit_unknown" and i.severity == "block" for i in issues)


def test_v2_rejects_conflicting_volume_flow():
    _, record = make_record()
    record.test.ghsv.raw_value = "5"
    record.test.ghsv.raw_unit = "h^-1"
    record.test.ghsv.state = "reported"
    _, issues = govern(record, Settings())
    assert "conflicting_flow_modes" in {i.code for i in issues}


def test_missing_observation_is_not_a_unit_error():
    _, record = make_record(CO2_conversion="10", selectivity_CH3OH="20", yield_CH3OH="2")
    record.test.pressure_type = "absolute"
    for obs in record.observations:
        obs.value.definition = "dataset definition"
    governed, issues = govern(record, Settings())
    assert governed.observations[3].value.normalized_value is None
    assert not any(i.code in {"sty_basis_unknown", "metric_unit_unknown"} for i in issues)
    assert any(i.code == "value_unknown" and i.path == "observations[3].value" for i in issues)
