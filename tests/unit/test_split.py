import json
from copy import deepcopy

import pytest

from catalyst_ai.datasets.split import build_paper_split, normalize_doi
from catalyst_ai.reporting.evidence import digest


def inputs(sample):
    records = []
    for i in range(6):
        payload = deepcopy(sample)
        payload["source"]["source_id"] = f"source-{i // 2}"
        payload["source"]["doi"] = f"https://doi.org/10.1234/PAPER{i // 2}"
        payload["source"]["title"] = f"paper {i // 2}"
        payload["test"]["temperature"]["normalized_value"] = 500.0
        payload["test"]["pressure"]["normalized_value"] = 10.0
        records.append(
            {"record_id": str(i), "payload": payload, "revision": {"original_fingerprint": str(i)}}
        )
    content = {
        "records": records,
        "record_ids": [str(i) for i in range(6)],
        "target": "co2_conversion",
    }
    h = digest(content)
    snap = {"snapshot_id": "snapshot-" + h, "content_sha256": h, "content": content}
    qc = {"eligible_record_ids": [str(i) for i in range(6)]}
    qh = digest(qc)
    qual = {
        "qualification_id": "qualification-" + qh,
        "content_sha256": qh,
        "content": qc,
        "snapshot": {"snapshot_id": snap["snapshot_id"]},
    }
    return snap, qual


def rehash_snapshot(snap, qual):
    h = digest(snap["content"])
    snap["content_sha256"] = h
    snap["snapshot_id"] = "snapshot-" + h
    qual["snapshot"]["snapshot_id"] = snap["snapshot_id"]


def test_alias_normalization_and_deterministic_group_partition(sample):
    s, q = inputs(sample)
    s["content"]["records"][1]["payload"]["source"]["doi"] = "doi.org/10.1234/paper0"
    rehash_snapshot(s, q)
    out = build_paper_split(s, q)
    assert out == build_paper_split(s, q)
    assert digest(json.loads(json.dumps(out))["content"]) == out["content_sha256"]
    assert normalize_doi("https://dx.doi.org/10.1234/PaPeR0") == "10.1234/paper0"
    assert len(out["content"]["groups"]) == 3
    parts = out["content"]["splits"]
    assert all(v["paper_group_count"] == 1 and v["record_count"] == 2 for v in parts.values())
    assert not set(parts["train"]["record_ids"]) & set(parts["test"]["record_ids"])


def test_missing_doi_insufficient_groups_and_hash_tampering_fail(sample):
    s, q = inputs(sample)
    s["content"]["records"][0]["payload"]["source"]["doi"] = None
    rehash_snapshot(s, q)
    with pytest.raises(ValueError, match="无有效DOI"):
        build_paper_split(s, q)
    s, q = inputs(sample)
    s["content"]["records"] = s["content"]["records"][:4]
    s["content"]["record_ids"] = [str(i) for i in range(4)]
    q["content"]["eligible_record_ids"] = s["content"]["record_ids"]
    q["content_sha256"] = digest(q["content"])
    q["qualification_id"] = "qualification-" + q["content_sha256"]
    rehash_snapshot(s, q)
    with pytest.raises(ValueError, match="组数不足"):
        build_paper_split(s, q)
    s["content"]["target"] = "tampered"
    with pytest.raises(ValueError, match="快照内容哈希"):
        build_paper_split(s, q)


def test_cross_paper_duplicate_and_ambiguous_reference_block(sample):
    s, q = inputs(sample)
    s["content"]["records"][2]["revision"]["original_fingerprint"] = "0"
    rehash_snapshot(s, q)
    with pytest.raises(ValueError, match="相同原始行"):
        build_paper_split(s, q)
    s, q = inputs(sample)
    s["content"]["records"][2]["payload"]["source"]["title"] = "paper 0"
    rehash_snapshot(s, q)
    with pytest.raises(ValueError, match="引用文本"):
        build_paper_split(s, q)
