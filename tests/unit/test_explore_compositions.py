from copy import deepcopy

import joblib
import pytest
from test_diagnostics import baseline

pytest.importorskip("shap")

from catalyst_ai.reporting.evidence import digest  # noqa: E402
from scripts import explore_compositions  # noqa: E402


def test_generation_uses_only_training_records_and_preserves_total(sample, tmp_path, monkeypatch):
    sample["recipe"]["composition_basis"] = "mol_pct"
    args, run, model_path = baseline(sample, tmp_path)
    snapshot, qualification, split, features = args
    snapshot = deepcopy(snapshot)
    train_ids = set(split["content"]["splits"]["train"]["record_ids"])
    for record in snapshot["content"]["records"]:
        if record["record_id"] in train_ids:
            for component in record["payload"]["recipe"]["components"]:
                component["amount"]["normalized_value"] = 50
        else:
            record["payload"]["recipe"]["components"][0]["species"] = "HELDOUTONLY"
    bundle = joblib.load(model_path)
    monkeypatch.setattr(
        explore_compositions,
        "verified_model",
        lambda *_: (bundle["models"]["extra_trees"], bundle["feature_names"]),
    )
    content = {"baseline_run_id": run["run_id"], "domain": {"threshold": 100000}}
    h = digest(content)
    diagnostic = {"content": content, "content_sha256": h, "diagnostic_id": "diagnostic-" + h}
    result = explore_compositions.generate(
        snapshot, qualification, split, features, run, model_path, diagnostic
    )
    assert result["content"]["candidates"]
    assert all(c["source_record_id"] in train_ids for c in result["content"]["candidates"])
    assert all(
        abs(sum(x["amount"] for x in c["composition"]["components"]) - 100) < 1e-9
        for c in result["content"]["candidates"]
    )
    assert "HELDOUTONLY" not in str(result["content"]["candidates"])
    assert result["content_sha256"] == digest(result["content"])
    assert len(result["content"]["selected_ids"]) <= 4
