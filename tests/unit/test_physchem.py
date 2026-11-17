import pytest

from catalyst_ai.features import physchem


def test_center_weighting_merge_and_absence(monkeypatch):
    properties = {
        "catalog": {
            "entries": [
                {"element": e, "property": p, "state": "available", "value": v}
                for e, v in (("A", 2.0), ("B", 4.0))
                for p in physchem.PROPERTIES
            ]
        }
    }
    species = {
        "catalog": {
            "entries": [
                {"species": "A2", "state": "supported", "centers": {"A": 2}},
                {"species": "B", "state": "supported", "centers": {"B": 1}},
            ]
        }
    }
    monkeypatch.setattr(
        physchem,
        "project",
        lambda _: {
            "amounts": {
                ("compound", "A2"): 25,
                ("compound", "B"): 50,
            }
        },
    )
    result = physchem.calculate({}, properties, species)
    assert result["reported_active_mean_covalent_radius"] == 3
    assert result["reported_support_mean_covalent_radius"] is None
    assert result["active_minus_support_covalent_radius"] is None
    species["catalog"]["entries"].pop()
    with pytest.raises(ValueError, match="unsupported_species"):
        physchem.calculate({}, properties, species)


def test_real_payload_permutation_and_merge(sample):
    from copy import deepcopy

    from test_r1_features import payload

    first = payload(sample, "Cu")
    component = first["recipe"]["components"][0]
    component["amount"]["normalized_value"] = 60
    second = deepcopy(component)
    second["species"] = "ZnO"
    second["amount"]["normalized_value"] = 40
    first["recipe"]["components"].append(second)
    properties = {
        "catalog": {
            "entries": [
                {"element": e, "property": p, "state": "available", "value": v}
                for e, v in (("Cu", 2.0), ("Zn", 4.0))
                for p in physchem.PROPERTIES
            ]
        }
    }
    species = {
        "catalog": {
            "entries": [
                {"species": "Cu", "state": "supported", "centers": {"Cu": 1}},
                {"species": "ZnO", "state": "supported", "centers": {"Zn": 1}},
            ]
        }
    }
    expected = physchem.calculate(first, properties, species)
    changed = deepcopy(first)
    split = deepcopy(changed["recipe"]["components"][0])
    split["amount"]["normalized_value"] = 20
    changed["recipe"]["components"][0]["amount"]["normalized_value"] = 40
    changed["recipe"]["components"].append(split)
    changed["recipe"]["components"].reverse()
    assert physchem.calculate(changed, properties, species) == expected
    changed["recipe"]["components"][0]["role"] = "promoter"
    with pytest.raises(ValueError, match="unsupported_source_role"):
        physchem.calculate(changed, properties, species)


def test_model_placeholder_values():
    values = {}
    for role in physchem.ROLES.values():
        values[role + "_material_mol_pct"] = 0
        values[role + "_species_count"] = 0
        for prop in physchem.PROPERTIES:
            values[role + "_mean_" + prop] = None
    for prop in physchem.PROPERTIES:
        values["active_minus_support_" + prop] = None
    assert len(physchem.model_values(values, "F1")) == 4
    assert list(physchem.model_values(values, "F2").values()) == [0] * 10
    assert values["reported_support_mean_covalent_radius"] is None
