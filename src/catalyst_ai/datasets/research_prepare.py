"""Build a split over a versioned dataset view without training."""

from pathlib import Path

from catalyst_ai.datasets.research_split import partition
from catalyst_ai.datasets.split import normalize_doi
from catalyst_ai.modeling.research_preflight import read_json, sha
from catalyst_ai.reporting.evidence import digest


def prepare(
    view_path, snapshot_path, *, root, strategy="random", train_fraction=0.8, folds=5, seed=42
):
    root = Path(root).resolve()
    view_path, snapshot_path = (root / view_path).resolve(), (root / snapshot_path).resolve()
    view, snapshot = read_json(view_path), read_json(snapshot_path)
    content = view["content"]
    binding = content["binding"]
    if digest(content) != view["content_sha256"] or not view["view_id"].endswith(
        view["content_sha256"]
    ):
        raise ValueError("view identity mismatch")
    if (
        digest(snapshot["content"]) != snapshot["content_sha256"]
        or snapshot["snapshot_id"] != binding["parent_snapshot_id"]
        or snapshot["content_sha256"] != binding["parent_content_sha256"]
    ):
        raise ValueError("snapshot identity mismatch")
    for name, expected in binding["sources"].items():
        if sha(root / name) != expected:
            raise ValueError(f"frozen source mismatch: {name}")
    if sha(view_path.parent / "ledger.json") != content["ledger_sha256"]:
        raise ValueError("ledger hash mismatch")
    ids = content["common_record_ids"]
    ledger = {r["record_id"]: r for r in read_json(view_path.parent / "ledger.json")["records"]}
    records = {r["record_id"]: r for r in snapshot["content"]["records"]}
    if len(ids) != len(set(ids)) or not set(ids) <= records.keys() or not set(ids) <= ledger.keys():
        raise ValueError("view membership invalid")
    rows = []
    for i in ids:
        evidence = ledger[i]
        status = evidence["repeat_identity_status"]
        if status not in ("no_confirmed_repeat", "confirmed_repeat"):
            raise ValueError("unresolved repeat identity")
        group = evidence.get("confirmed_repeat_group") if status == "confirmed_repeat" else None
        if status == "confirmed_repeat" and not group:
            raise ValueError("confirmed repeat group missing")
        rows.append(
            {
                "record_id": i,
                "doi": normalize_doi(records[i]["payload"]["source"]["doi"]),
                "repeat_group": group,
            }
        )
    result = partition(
        rows, strategy=strategy, train_fraction=train_fraction, folds=folds, seed=seed
    )
    result.update(
        {
            "dataset_view_id": view["view_id"],
            "status": "preliminary",
            "protocol_version": "research-split-v1",
            "test_purpose": "internal evaluation",
        }
    )
    result["content_sha256"] = digest(result)
    result["split_id"] = "research-split-" + result["content_sha256"]
    return result
