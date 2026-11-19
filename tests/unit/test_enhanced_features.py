import json
from pathlib import Path

import pytest

from catalyst_ai.features.enhanced import EnhancedFeatures, verify_s1_binding
from catalyst_ai.features.physchem import model_values
from catalyst_ai.storage.feature_catalog import get_catalog, get_evidence


def test_s1_v4_replay_and_fold_features():
    root = Path(__file__).resolve().parents[2]
    folder = root / "artifacts/reports/s1-b-20261113-v4"
    database = root / "data/catalog.sqlite"
    if not database.exists() or not folder.exists():
        pytest.skip("S1 v4 evidence not available")

    def load(path):
        return json.loads(path.read_text(encoding="utf-8-sig"))

    selection = load(folder / "selection.json")
    features = load(folder / "features.json")
    binding = selection["content"]["binding"]
    snapshot = load(root / "data/snapshots" / (binding["snapshot_id"] + ".json"))
    qualification = load(
        root / "data/snapshots/qualifications" / (binding["qualification_id"] + ".json")
    )
    split = load(root / "artifacts/reports/themecat-i2-20261110/split-verified.json")
    properties = get_catalog(database, "properties", binding["property_version"])
    species = get_catalog(database, "species", binding["mapping_version"])
    review = get_evidence(database, binding["review_version"])
    args = (snapshot, qualification, split, properties, species, review, selection, features)
    verify_s1_binding(*args, root=root)
    records = {r["record_id"]: r["payload"] for r in snapshot["content"]["records"]}
    train = [records[i] for i in selection["content"]["retained"]["train"]]
    models = {
        name: EnhancedFeatures.fit(train, name, properties=properties, species=species)
        for name in ("F1", "F2")
    }
    assert len(features["content"]["rows"]) == 553
    for row in features["content"]["rows"]:
        for name, model in models.items():
            result = model.transform_one(records[row["record_id"]], diagnostic=True)
            assert result["derived"] == row["derived"]
            expected = model_values({k: v["value"] for k, v in row["derived"].items()}, name)
            assert result["values"][-len(expected) :] == list(expected.values())
    features["content"]["rows"].pop()
    with pytest.raises(ValueError, match="binding mismatch"):
        verify_s1_binding(*args, root=root)
