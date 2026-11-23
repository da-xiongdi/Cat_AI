import json

import pytest

from catalyst_ai.datasets.research_prepare import prepare
from catalyst_ai.modeling.research_preflight import preflight, sha
from catalyst_ai.reporting.evidence import digest


def save(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def test_confirmed_repeats_link_dois_and_reject_leakage(tmp_path):
    records = [
        {"record_id": str(i), "payload": {"source": {"doi": f"10.1234/p{i}"}}} for i in range(12)
    ]
    content = {"target": "co2_conversion", "records": records}
    snapshot = {
        "snapshot_id": "snapshot-" + digest(content),
        "content_sha256": digest(content),
        "content": content,
    }
    save(tmp_path / "snapshot.json", snapshot)
    ledger = [
        {
            "record_id": str(i),
            "repeat_identity_status": "confirmed_repeat" if i in (0, 1) else "no_confirmed_repeat",
            "confirmed_repeat_group": "cross-paper-repeat" if i in (0, 1) else "",
        }
        for i in range(12)
    ]
    save(tmp_path / "ledger.json", {"records": ledger})
    save(tmp_path / "distributions.json", {})
    view_content = {
        "binding": {
            "parent_snapshot_id": snapshot["snapshot_id"],
            "parent_content_sha256": snapshot["content_sha256"],
            "sources": {},
        },
        "common_record_ids": [str(i) for i in range(12)],
        "ledger_sha256": sha(tmp_path / "ledger.json"),
        "distributions_sha256": sha(tmp_path / "distributions.json"),
    }
    view = {
        "view_id": "view-" + digest(view_content),
        "content_sha256": digest(view_content),
        "content": view_content,
    }
    save(tmp_path / "view.json", view)
    split = prepare("view.json", "snapshot.json", root=tmp_path, strategy="doi", folds=3)
    assert any({"0", "1"} <= set(g) for g in split["groups"])
    save(tmp_path / "split.json", split)
    config = {
        "view": "view.json",
        "snapshot": "snapshot.json",
        "split": "split.json",
        "split_sha256": sha(tmp_path / "split.json"),
        "candidates": [{"feature": "F_base", "model": "dummy"}],
    }
    save(tmp_path / "config.json", config)
    preflight(tmp_path / "config.json", root=tmp_path)
    source = "train" if "0" in split["train"] else "test"
    other = "test" if source == "train" else "train"
    split[source].remove("0")
    split[other].append("0")
    if source == "train":
        next(f for f in split["validation_folds"] if "0" in f).remove("0")
    else:
        split["validation_folds"][0].append("0")
    split.pop("split_id")
    split.pop("content_sha256")
    split["content_sha256"] = digest(split)
    split["split_id"] = "research-split-" + split["content_sha256"]
    save(tmp_path / "split.json", split)
    config["split_sha256"] = sha(tmp_path / "split.json")
    save(tmp_path / "config.json", config)
    with pytest.raises(ValueError, match="repeat group"):
        preflight(tmp_path / "config.json", root=tmp_path)
