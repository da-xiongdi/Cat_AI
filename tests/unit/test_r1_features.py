from copy import deepcopy

import pytest

from catalyst_ai.features.pipeline import R1Features


def payload(sample, species="Cu", amount=100):
    data = deepcopy(sample)
    data["recipe"].update(composition_basis="mol_pct", composition_scope="whole")
    component = data["recipe"]["components"][0]
    component.update(species=species, role="compound")
    component["amount"].update(state="reported", normalized_value=amount, normalized_unit="%")
    data["recipe"]["components"] = [component]
    test = data["test"]

    def measure(value, unit):
        return {
            "state": "reported",
            "normalized_value": value,
            "normalized_unit": unit,
        }

    test["temperature"] = measure(500, "K")
    test["pressure"] = measure(10, "bar(abs)")
    test["pressure_type"] = "absolute"
    test["reactant_ratio"] = {"numerator": "H2", "denominator": "CO2", "value": measure(3, "1")}
    test["mass_normalized_volume_flow"] = {
        "mass_basis": "catalyst",
        "gas_scope": "reactants_only",
        "reference_temperature": measure(293.15, "K"),
        "reference_pressure": measure(1.01325, "bar(abs)"),
        "reference_pressure_type": "absolute",
        "value": measure(5, "NL/g_cat/h"),
    }
    return data


def test_fold_vocabulary_and_diagnostics(sample):
    train = payload(sample)
    model = R1Features.fit([train])
    new = payload(sample, "ZnO")
    assert model.transform_one(new)["values"] is None
    result = model.transform_one(new, diagnostic=True)
    assert result["unseen_species_roles"] == [("compound", "ZnO")]
    assert result["values"][-1] == 0
    assert R1Features.fit([train], "F_cond").transform_one(new)["status"] == "ok"
    zero = deepcopy(train["recipe"]["components"][0])
    zero["species"] = "ZnO"
    zero["amount"]["normalized_value"] = 0
    train["recipe"]["components"].append(zero)
    assert model.transform_one(train)["status"] == "ok"


def test_validation_and_merge(sample):
    train = payload(sample)
    model = R1Features.fit([train])
    duplicate = deepcopy(train["recipe"]["components"][0])
    duplicate["amount"]["normalized_value"] = 40
    train["recipe"]["components"][0]["amount"]["normalized_value"] = 60
    train["recipe"]["components"].append(duplicate)
    assert model.transform_one(train)["values"][-1] == 100
    train["recipe"]["composition_basis"] = "wt_pct"
    with pytest.raises(ValueError, match="mol_pct"):
        model.transform_one(train)


def test_selection_preserves_split_and_rejects_tampering(sample):
    from test_split import inputs, rehash_snapshot

    from catalyst_ai.datasets.split import build_paper_split
    from catalyst_ai.features.pipeline import select_inputs

    snapshot, qualification = inputs(sample)
    for record in snapshot["content"]["records"]:
        source = payload(record["payload"])
        record["payload"] = source
    snapshot["content"]["records"][0]["payload"]["recipe"]["composition_basis"] = "wt_pct"
    rehash_snapshot(snapshot, qualification)
    split = build_paper_split(snapshot, qualification)
    selection = select_inputs(snapshot, qualification, split)
    exclusions = sum(selection["content"]["excluded"].values(), [])
    assert len(exclusions) == 1 and exclusions[0]["record_id"] == "0"
    assert sum(selection["content"]["retained"].values(), [])
    split["content"]["splits"]["train"]["record_ids"].append("0")
    with pytest.raises(ValueError, match="split"):
        select_inputs(snapshot, qualification, split)


def test_fold_fitting_and_range_warning(sample):
    first = payload(sample)
    second = payload(sample, "ZnO")
    first_model = R1Features.fit([first])
    second_model = R1Features.fit([second])
    assert first_model.vocabulary != second_model.vocabulary
    altered = deepcopy(first)
    altered["test"]["temperature"]["normalized_value"] = 510
    result = first_model.transform_one(altered)
    assert result["status"] == "caution"
    assert "temperature_k" in result["out_of_range"]
