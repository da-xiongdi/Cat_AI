"""Deterministic paper-held-out split of a frozen qualification."""

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote

from catalyst_ai.reporting.evidence import digest


def normalize_doi(value):
    if not isinstance(value, str):
        return None
    value = unquote(value.strip()).lower()
    value = re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value).strip()
    return value if re.fullmatch(r"10\.\d{4,9}/\S+", value) else None


def build_paper_split(snapshot, qualification, *, seed=42):
    content = snapshot.get("content", {})
    h = digest(content)
    if snapshot.get("content_sha256") != h or snapshot.get("snapshot_id") not in {
        "snapshot-" + h,
        "demo-snapshot-" + h,
    }:
        raise ValueError("快照内容哈希不匹配")
    qc = qualification.get("content", {})
    qh = digest(qc)
    if (
        qualification.get("content_sha256") != qh
        or qualification.get("qualification_id") != "qualification-" + qh
    ):
        raise ValueError("资格清单哈希不匹配")
    if (qualification.get("snapshot") or {}).get("snapshot_id") != snapshot["snapshot_id"]:
        raise ValueError("资格清单与快照不关联")
    records = content.get("records", [])
    ids = [r["record_id"] for r in records]
    if (
        len(ids) != len(set(ids))
        or set(ids) != set(qc.get("eligible_record_ids", []))
        or set(ids) != set(content.get("record_ids", []))
    ):
        raise ValueError("快照与资格记录集合不一致")
    groups = defaultdict(list)
    source_dois, title_dois, fingerprints = defaultdict(set), defaultdict(set), defaultdict(set)
    unresolved = []
    for row in records:
        source = row["payload"].get("source") or {}
        doi = normalize_doi(source.get("doi"))
        if not doi or not source.get("source_id"):
            unresolved.append(row["record_id"])
            continue
        source_dois[source["source_id"]].add(doi)
        title = " ".join(source.get("title", "").casefold().split())
        if title:
            title_dois[title].add(doi)
        fingerprint = (row.get("revision") or {}).get("original_fingerprint")
        if fingerprint:
            fingerprints[fingerprint].add(doi)
        groups[doi].append(row)
    if unresolved:
        raise ValueError(f"存在无有效DOI或来源ID的记录，不能进行论文分组: {len(unresolved)}")
    if any(len(v) > 1 for v in source_dois.values()):
        raise ValueError("同一来源ID对应多个DOI，需先解决来源冲突")
    if any(len(v) > 1 for v in fingerprints.values()):
        raise ValueError("相同原始行跨多个DOI，需先解决重复关系")
    conflicts = {k: sorted(v) for k, v in title_dois.items() if len(v) > 1}
    if conflicts:
        raise ValueError("相同来源引用文本对应多个DOI，需先核对别名")
    n = len(groups)
    if n < 3:
        raise ValueError(f"论文组数不足，至少需要3组，实际{n}；不回退随机记录划分")
    ordered = sorted(groups, key=lambda doi: hashlib.sha256(f"{seed}:{doi}".encode()).hexdigest())
    train_n = max(1, min(n - 2, round(n * 0.70)))
    val_n = max(1, min(n - train_n - 1, round(n * 0.15)))
    divisions = {
        "train": ordered[:train_n],
        "validation": ordered[train_n : train_n + val_n],
        "test": ordered[train_n + val_n :],
    }
    splits = {}
    for name, dois in divisions.items():
        subset = [r for doi in dois for r in groups[doi]]
        temperatures = [r["payload"]["test"]["temperature"]["normalized_value"] for r in subset]
        pressures = [r["payload"]["test"]["pressure"]["normalized_value"] for r in subset]
        splits[name] = {
            "record_ids": sorted(r["record_id"] for r in subset),
            "dois": sorted(dois),
            "record_count": len(subset),
            "paper_group_count": len(dois),
            "source_ids": sorted({r["payload"]["source"]["source_id"] for r in subset}),
            "material_families": sorted(
                {r["payload"]["recipe"]["material_family"] for r in subset}
            ),
            "temperature_k_range": [min(temperatures), max(temperatures)],
            "pressure_bar_abs_range": [min(pressures), max(pressures)],
        }
    paper_groups = [
        {
            "doi": doi,
            "record_ids": sorted(r["record_id"] for r in rows),
            "source_ids": sorted({r["payload"]["source"]["source_id"] for r in rows}),
            "reference_labels": sorted({r["payload"]["source"]["title"] for r in rows}),
            "raw_dois": sorted({r["payload"]["source"]["doi"] for r in rows}),
            "count": len(rows),
        }
        for doi, rows in sorted(groups.items())
    ]
    intersections = {}
    for left, right in (("train", "validation"), ("train", "test"), ("validation", "test")):
        a, b = splits[left], splits[right]
        overlap = {
            "record_ids": sorted(set(a["record_ids"]) & set(b["record_ids"])),
            "dois": sorted(set(a["dois"]) & set(b["dois"])),
            "source_ids": sorted(set(a["source_ids"]) & set(b["source_ids"])),
            "shared_material_family_labels": sorted(
                set(a["material_families"]) & set(b["material_families"])
            ),
        }
        if overlap["record_ids"] or overlap["dois"] or overlap["source_ids"]:
            raise ValueError("集合存在跨组记录或论文来源，禁止输出划分")
        intersections[left + "_vs_" + right] = overlap
    result = {
        "schema_version": "1",
        "strategy": "paper_doi",
        "seed": seed,
        "allocation": "sha256(seed:doi), 70/15/15 by group count rounded; no target stratification",
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_content_sha256": h,
        "qualification_id": qualification["qualification_id"],
        "target": content["target"],
        "groups": paper_groups,
        "splits": splits,
        "checks": {
            "unique_doi_assignment": True,
            "source_id_conflicts": [],
            "identical_reference_multiple_dois": [],
            "same_fingerprint_multiple_dois": [],
            "unresolved_record_ids": [],
            "assigned_record_count": len(ids),
            "fingerprints_missing": sum(
                not (r.get("revision") or {}).get("original_fingerprint") for r in records
            ),
            "pairwise_intersections": intersections,
        },
        "limitations": [
            "DOI normalization is not independent verification of source metadata",
            "row-derived recipe and synthesis IDs do not establish sample or batch identity",
            "unconfirmed cross-paper sample identity and duplicate relationships remain unresolved",
            "shared material family labels do not establish sample identity",
            "pressure type is user-assumed absolute; records are not individually verified",
        ],
        "group_size_distribution": {
            str(size): count
            for size, count in sorted(Counter(len(v) for v in groups.values()).items())
        },
        "sample_identity_verified": False,
        "training_performed": False,
    }
    return {
        "split_id": "split-" + digest(result),
        "content_sha256": digest(result),
        "content": result,
    }


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))
