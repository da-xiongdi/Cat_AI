import hashlib
import json
from pathlib import Path

from sqlalchemy import select

from catalyst_ai.reporting.evidence import canonical, digest, metadata, now, write_json
from catalyst_ai.storage.db import transaction
from catalyst_ai.storage.models import (
    CuratedRow,
    ImportRunRow,
    ReviewRow,
    SnapshotRow,
    StagedRow,
)


def build_verified_snapshot(
    settings, *, target, record_ids=None, output=None, demo=False, source_acceptance=None
):
    """Freeze reviewed records as JSON; Parquet/feature tables are later extensions."""
    if not target.strip():
        raise ValueError("target不能为空")
    from catalyst_ai.datasets.eligibility import THEMECAT_ACCEPTED, THEMECAT_SHA256

    if source_acceptance not in (None, THEMECAT_ACCEPTED) or (source_acceptance and demo):
        raise ValueError("不支持的数据集来源接受策略")
    kind = "synthetic_demo" if demo else "research"
    with transaction(settings.database) as session:
        ids = (
            sorted(set(record_ids))
            if record_ids
            else sorted(
                session.scalars(select(CuratedRow.id).where(CuratedRow.dataset_kind == kind)).all()
            )
        )
        if not ids:
            raise ValueError("没有真实研究记录；synthetic_demo禁止进入已核验研究快照")
        records = []
        definitions = set()
        fingerprints = set()
        for identifier in ids:
            record = session.get(CuratedRow, identifier)
            if record is None:
                raise ValueError(f"记录不在curated: {identifier}")
            if record.dataset_kind != kind:
                raise ValueError("synthetic_demo禁止进入已核验研究快照；不同数据类别不能混合")
            staged = session.get(StagedRow, identifier)
            run = session.get(ImportRunRow, staged.run_id)
            accepted = (
                source_acceptance == THEMECAT_ACCEPTED
                and run.input_sha256 == THEMECAT_SHA256
                and record.review_status == "pending"
            )
            if record.review_status != "verified" and not accepted:
                raise ValueError(f"记录尚未人工核验或已拒绝: {identifier}")
            if staged.fingerprint in fingerprints:
                raise ValueError("同一原始记录的多个版本不能同时进入快照")
            fingerprints.add(staged.fingerprint)
            if staged.payload["dataset_kind"] != kind:
                raise ValueError("staged/curated的数据类别不一致")
            reviews = session.scalars(
                select(ReviewRow)
                .where(ReviewRow.record_id == identifier)
                .order_by(ReviewRow.created_at, ReviewRow.id)
            ).all()
            if accepted and reviews:
                raise ValueError("来源接受与现有审核状态不一致")
            if not accepted and (not reviews or reviews[-1].decision != "verified"):
                raise ValueError("缺少对应人工审核事件")
            if not accepted and reviews[-1].payload_sha256 != digest(staged.payload):
                raise ValueError("记录与人工核验时内容不符，须重新核验")
            if accepted:
                entry = next(
                    (e for e in run.report.get("rows", []) if e["record_id"] == identifier), None
                )
                if (
                    digest(staged.raw_payload) != staged.fingerprint
                    or not entry
                    or entry.get("governed_sha256") != digest(staged.payload)
                ):
                    raise ValueError("来源接受记录内容或原始行不一致")
            raw_path = Path(run.report["raw_path"])
            if (
                not raw_path.exists()
                or hashlib.sha256(raw_path.read_bytes()).hexdigest() != run.input_sha256
            ):
                raise ValueError("原始证据文件丢失或哈希不符")
            matches = [o for o in staged.payload["observations"] if o["metric"] == target]
            if not matches:
                raise ValueError(f"记录缺少目标{target}: {identifier}")
            for obs in matches:
                value = obs["value"]
                if value["normalized_value"] is None or not value["definition"]:
                    raise ValueError("目标缺少有效标准值或定义，不能创建目标快照")
                definitions.add((value["definition"], value["normalized_unit"]))
            records.append(
                {
                    "record_id": identifier,
                    "payload": staged.payload,
                    "payload_sha256": digest(staged.payload),
                    "input_sha256": run.input_sha256,
                    "input_locator": staged.input_locator,
                    "quality_issues": staged.issues,
                    "governance_metadata": run.metadata_json,
                    **({"revision": run.report["revision"]} if "revision" in run.report else {}),
                    "review": None
                    if accepted
                    else {
                        "review_id": reviews[-1].id,
                        "reviewer": reviews[-1].reviewer,
                        "evidence": reviews[-1].evidence,
                        "created_at": reviews[-1].created_at,
                        "metadata": reviews[-1].metadata_json,
                    },
                }
            )
        if len(definitions) != 1:
            raise ValueError("目标定义/单位不一致；须先按口径分层，不自动合并")
        definition, unit = next(iter(definitions))
        content = {
            "schema_version": "1",
            "dataset_kind": kind,
            "scientific_use": not demo,
            "target": target,
            "target_definition": definition,
            "target_unit": unit,
            "record_ids": ids,
            "records": records,
            "metadata": metadata(settings),
            "split_policy_required": ["source_id", "recipe_id", "synthesis_id"],
            "split_status": "not_performed",
            "status": "human_reviewed_demo" if demo else "human_reviewed",
            "condition_standardization": "none",
        }
        if source_acceptance:
            content["source_acceptance"] = {
                "policy": source_acceptance,
                "input_sha256": THEMECAT_SHA256,
                "basis": "用户接受公开发表的TheMeCat v1数据集作为来源证据；不代表逐行原文核验",
            }
            content["status"] = "published_dataset_accepted_not_row_verified"
        content_hash = digest(content)
        snapshot_id = ("demo-snapshot-" if demo else "snapshot-") + content_hash
        existing = session.get(SnapshotRow, snapshot_id)
        manifest = (
            existing.manifest
            if existing
            else {
                "snapshot_id": snapshot_id,
                "created_at": now(),
                "content_sha256": content_hash,
                "content": content,
            }
        )
        directory = output or settings.data_dir / "snapshots"
        path = (directory / "demo" if demo else directory) / f"{snapshot_id}.json"
        if path.exists():
            if canonical(json.loads(path.read_text(encoding="utf-8"))) != canonical(manifest):
                raise ValueError("快照文件已存在且内容不符；拒绝覆盖")
        else:
            write_json(path, manifest)
        if not existing:
            session.add(
                SnapshotRow(
                    id=snapshot_id,
                    created_at=manifest["created_at"],
                    content_sha256=content_hash,
                    manifest=manifest,
                )
            )
    return {
        "snapshot_id": snapshot_id,
        "path": str(path),
        "record_count": len(ids),
        "dataset_kind": kind,
        "content_sha256": content_hash,
    }
