import pickle
from copy import deepcopy

import pytest
from test_r1_features import payload

from catalyst_ai.features.f3 import F3Features, descriptors
from catalyst_ai.features.physchem import PROPERTIES


@pytest.fixture
def catalogs():
    p = {"catalog": {"entries": [
        {"element": e, "property": k, "state": "available", "value": v}
        for e, v in (("Cu", 2.0), ("Zn", 4.0)) for k in PROPERTIES
    ]}}
    s = {"catalog": {"entries": [
        {"species": "Cu", "state": "supported", "centers": {"Cu": 1}},
        {"species": "ZnO", "state": "supported", "centers": {"Zn": 1}},
    ]}}
    return p, s


def test_center_arithmetic_and_permutation(sample, catalogs):
    p, s = catalogs
    x = payload(sample, "Cu")
    x["recipe"]["components"][0]["amount"]["normalized_value"] = 25
    z = deepcopy(x["recipe"]["components"][0])
    z["species"] = "ZnO"
    z["amount"]["normalized_value"] = 75
    x["recipe"]["components"].append(z)
    d = descriptors(x, p, s)
    assert d["reported_active_mean_covalent_radius"] == 3.5
    assert d["reported_active_variance_covalent_radius"] == .75
    assert d["reported_support_mean_covalent_radius"] is None
    y = deepcopy(x)
    part = deepcopy(y["recipe"]["components"][0])
    part["amount"]["normalized_value"] = 10
    y["recipe"]["components"][0]["amount"]["normalized_value"] = 15
    y["recipe"]["components"].append(part)
    y["recipe"]["components"].reverse()
    assert descriptors(y, p, s) == d
    for name in ("F3-P", "F3-H", "F3-I"):
        model = F3Features.fit([x], name, properties=p, species=s)
        assert model.transform_one(x) == pickle.loads(pickle.dumps(model)).transform_one(y)


def test_rejections(sample, catalogs):
    p, s = catalogs
    x = payload(sample, "Cu")
    y = deepcopy(x)
    y["recipe"]["components"][0]["role"] = "promoter"
    with pytest.raises(ValueError, match="unsupported_source_role"):
        descriptors(y, p, s)
    y = deepcopy(x)
    y["recipe"]["components"][0]["species"] = "Cu0.5Zn0.5"
    with pytest.raises(ValueError, match="unsupported_species"):
        descriptors(y, p, s)
    y = deepcopy(x)
    y["recipe"]["components"][0]["amount"]["normalized_value"] = 50
    with pytest.raises(ValueError, match="invalid_composition"):
        descriptors(y, p, s)
    y = deepcopy(x)
    y["recipe"]["components"][0]["amount"]["normalized_unit"] = "g"
    with pytest.raises(ValueError, match="invalid_composition"):
        descriptors(y, p, s)
    p["catalog"]["entries"].pop(0)
    with pytest.raises(ValueError, match="property_unavailable"):
        descriptors(x, p, s)


def test_fold_local_ranges_and_states(sample, catalogs):
    p, s = catalogs
    x = payload(sample, "Cu")
    model = F3Features.fit([x], "F3-I", properties=p, species=s)
    first = model.transform_one(x)
    assert first["derived"]["reported_active_variance_covalent_radius"]["state"] == "zero"
    assert first["derived"]["reported_support_mean_covalent_radius"]["state"] == "not_applicable"
    y = deepcopy(x)
    component = y["recipe"]["components"][0]
    component["amount"]["normalized_value"] = 50
    support = deepcopy(component)
    support["role"] = "support"
    support["species"] = "ZnO"
    y["recipe"]["components"].append(support)
    result = model.transform_one(y)
    assert result["status"] == "caution"
    assert "reported_support_mean_covalent_radius" in result["out_of_range"]
    assert "active_support_ratio" in result["out_of_range"]
    assert pickle.loads(pickle.dumps(model)).transform_one(y) == result
