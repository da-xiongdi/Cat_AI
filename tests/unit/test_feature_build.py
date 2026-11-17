from copy import deepcopy

import pytest

from catalyst_ai.reporting.evidence import digest
from catalyst_ai.storage.feature_build import get_build, persist


def test_persist_replay_and_tamper(tmp_path):
    import sqlite3

    selection_content = {"retained": {"train": ["r"]}}
    sh = digest(selection_content)
    selection = {
        "selection_id": "selection-" + sh,
        "content_sha256": sh,
        "content": selection_content,
    }
    content = {
        "selection_id": selection["selection_id"],
        "rows": [{"record_id": "r", "derived": {"x": {"value": None, "state": "not_applicable"}}}],
    }
    fh = digest(content)
    features = {"feature_snapshot_id": "features-" + fh, "content_sha256": fh, "content": content}
    database = tmp_path / "test.sqlite"
    persist(database, selection, features)
    persist(database, selection, features)
    assert get_build(database, features["feature_snapshot_id"]) == (selection, features)
    invalid = deepcopy(features)
    invalid["content"]["rows"][0]["derived"]["x"]["value"] = 1
    with pytest.raises(ValueError, match="hash mismatch"):
        persist(database, selection, invalid)
    with sqlite3.connect(database) as con:
        con.execute("UPDATE feature_value_s1b SET value=1")
    with pytest.raises(ValueError, match="index mismatch"):
        get_build(database, features["feature_snapshot_id"])
