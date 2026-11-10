from copy import deepcopy

import pytest
from test_split import inputs, rehash_snapshot

from catalyst_ai.datasets.split import build_paper_split
from catalyst_ai.features.design import build_feature_table, design_input
from catalyst_ai.reporting.evidence import digest


def test_design_boundary_and_order(sample):
    source = deepcopy(sample)
    source["recipe"]["composition_basis"] = "mol_pct"
    source["recipe"]["composition_scope"] = "whole catalyst"
    for component in source["recipe"]["components"]:
        component["amount"].update(state="reported", normalized_value=25, normalized_unit="%")
    before = design_input(source)
    assert before["composition"] is not None
    assert len(before["composition"]["components"]) > 1
    changed = deepcopy(source)
    changed["recipe"]["components"].reverse()
    changed["observations"] = [{"value": {"normalized_value": 999}}]
    changed["characterizations"] = [{"properties": {"BET": 999}}]
    changed["synthesis"]["route"] = "result-bearing text"
    assert design_input(changed) == before
    changed["recipe"]["composition_basis"] = "unknown"
    assert design_input(changed)["composition"] is None
    assert design_input(changed)["composition_state"] == "unknown_basis_or_scope"
    plan = {
        "calcination_temperature_k": {
            "state": "reported",
            "normalized_value": 600,
            "normalized_unit": "K",
        }
    }
    assert (
        design_input(source, planned_synthesis=plan)["values"]["calcination_temperature_k"] == 600
    )
    with pytest.raises(ValueError):
        design_input(source, planned_synthesis={"result": plan})


def test_train_vocabulary_and_tamper(sample):
    snap, qual = inputs(sample)
    split = build_paper_split(snap, qual)
    test_id = split["content"]["splits"]["test"]["record_ids"][0]
    row = next(r for r in snap["content"]["records"] if r["record_id"] == test_id)
    row["payload"]["recipe"]["composition_basis"] = "mol_pct"
    row["payload"]["recipe"]["composition_scope"] = "whole"
    row["payload"]["recipe"]["components"] = row["payload"]["recipe"]["components"][:1]
    row["payload"]["recipe"]["components"][0]["species"] = "TEST_ONLY"
    row["payload"]["recipe"]["components"][0]["amount"].update(
        state="reported", normalized_value=30, normalized_unit="%"
    )
    rehash_snapshot(snap, qual)
    split = build_paper_split(snap, qual)
    out = build_feature_table(snap, qual, split)
    assert digest(out["content"]) == out["content_sha256"]
    assert "TEST_ONLY" not in str(out["content"]["composition_vocabulary"])
    assert (
        next(r for r in out["content"]["rows"] if r["record_id"] == test_id)[
            "unseen_component_count"
        ]
        >= 1
    )
    split["content"]["splits"]["train"]["record_ids"].append(test_id)
    with pytest.raises(ValueError, match="划分清单"):
        build_feature_table(snap, qual, split)
