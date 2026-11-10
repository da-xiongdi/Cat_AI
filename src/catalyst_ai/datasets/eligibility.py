"""Auditable, observation-level eligibility before the strict record snapshot gate."""

import hashlib
import json
import math
from pathlib import Path

from sqlalchemy import select

from catalyst_ai.reporting.evidence import canonical, digest, metadata, write_json
from catalyst_ai.schemas.domain import ImportRecord, ImportRecordV2, ValueState
from catalyst_ai.storage.db import transaction
from catalyst_ai.storage.models import CuratedRow, ImportRunRow, ReviewRow, StagedRow
from catalyst_ai.storage.snapshots import build_verified_snapshot

RULE_VERSION = "1"
THEMECAT_ACCEPTED = "themecat-v1-published-dataset"
THEMECAT_SHA256 = "46000f00323ac64a79f63777e54c05634e83d1a6476176c8b6569122bd03dfbd"


def _time_seconds(observation, test):
    value = observation.time_on_stream
    if value.state not in {ValueState.REPORTED, ValueState.ZERO}:
        value = test.time_on_stream
    number = value.normalized_value
    factors = {"h": 3600, "min": 60}
    if (
        value.state not in {ValueState.REPORTED, ValueState.ZERO}
        or number is None
        or value.normalized_unit not in factors
        or not math.isfinite(number)
        or number < 0
    ):
        return None
    seconds = number * factors[value.normalized_unit]
    return seconds if math.isfinite(seconds) else None


def _inspect_record(session, identifier, kind, target, raw_cache, source_acceptance=None):
    staged = session.get(StagedRow, identifier)
    row = {
        "record_id": identifier,
        "payload_sha256": digest(staged.payload) if staged else None,
        "raw_payload_sha256": digest(staged.raw_payload) if staged else None,
        "input_sha256": None,
        "input_locator": staged.input_locator if staged else None,
        "review": None,
        "entities": {},
        "observations": [],
        "reason_codes": [],
        "integrity_errors": [],
        "status": "excluded",
    }
    reasons, errors = row["reason_codes"], row["integrity_errors"]
    if staged is None:
        errors.append("record_not_found")
        reasons.append("record_not_found")
        return row
    curated = session.get(CuratedRow, identifier)
    if row["raw_payload_sha256"] != staged.fingerprint:
        errors.append("raw_payload_changed")
    if curated is None:
        reasons.append("not_curated")
    if source_acceptance:
        row["governance_blocks"] = [
            issue for issue in staged.issues if issue.get("severity") == "block"
        ]
    if staged.dataset_kind != kind or (curated and curated.dataset_kind != kind):
        errors.append("dataset_kind_mismatch")
    run = session.get(ImportRunRow, staged.run_id)
    if run is None:
        errors.append("import_run_missing")
    else:
        row["input_sha256"] = run.input_sha256
        if run.id not in raw_cache:
            path = Path(run.report.get("raw_path", ""))
            try:
                raw_cache[run.id] = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                raw_cache[run.id] = None
        if raw_cache[run.id] is None:
            errors.append("raw_evidence_missing")
        elif raw_cache[run.id] != run.input_sha256:
            errors.append("raw_evidence_hash_mismatch")
        imported = next(
            (entry for entry in run.report.get("rows", []) if entry["record_id"] == identifier),
            None,
        )
        if imported is None:
            errors.append("import_evidence_missing")
        elif imported["governed_sha256"] != (
            digest(staged.payload) if staged.payload is not None else None
        ):
            errors.append("governed_payload_changed")
    review = session.scalar(
        select(ReviewRow)
        .where(ReviewRow.record_id == identifier)
        .order_by(ReviewRow.created_at.desc(), ReviewRow.id.desc())
        .limit(1)
    )
    if review:
        row["review"] = {
            "review_id": review.id,
            "decision": review.decision,
            "payload_sha256": review.payload_sha256,
            "reviewer": review.reviewer,
            "evidence": review.evidence,
            "created_at": review.created_at,
            "metadata": review.metadata_json,
        }
        if review.payload_sha256 != row["payload_sha256"]:
            errors.append("review_payload_changed")
        if review.decision == "rejected":
            errors.append("review_rejected")
    if curated:
        accepted = (
            source_acceptance == THEMECAT_ACCEPTED and run and run.input_sha256 == THEMECAT_SHA256
        )
        if curated.review_status != "verified" and not (
            accepted and curated.review_status == "pending"
        ):
            reasons.append(
                "not_reviewed" if curated.review_status == "pending" else "review_rejected"
            )
        if (review and review.decision != curated.review_status) or (
            curated.review_status in {"verified", "rejected"} and review is None
        ):
            errors.append("review_state_inconsistent")
    if staged.payload is None:
        reasons.append("payload_unavailable")
        reasons.extend(errors)
        return row
    try:
        model = ImportRecordV2 if staged.payload.get("schema_version") == "2" else ImportRecord
        record = model.model_validate(staged.payload)
    except ValueError:
        reasons.append("payload_invalid")
        if curated:
            errors.append("curated_payload_invalid")
        reasons.extend(errors)
        return row
    row["entities"] = {
        "source_id": record.source.source_id if record.source else None,
        "recipe_id": record.recipe.recipe_id,
        "synthesis_id": record.synthesis.synthesis_id,
        "test_id": record.test.test_id,
        "material_family": record.recipe.material_family,
    }
    if record.dataset_kind != kind:
        errors.append("dataset_kind_mismatch")
    if curated and (
        staged.status != "curated"
        or any(
            getattr(curated, key) != row["entities"][key]
            for key in ("source_id", "recipe_id", "synthesis_id", "test_id")
        )
    ):
        errors.append("entity_reference_mismatch")
    matches = sorted(
        (obs for obs in record.observations if obs.metric == target["metric"]),
        key=lambda obs: obs.observation_id,
    )
    if not matches:
        reasons.append("missing_target")
    times = [_time_seconds(obs, record.test) for obs in matches]
    ambiguous = len(matches) > 1 and (None in times or len(set(times)) != len(times))
    if ambiguous:
        reasons.append("ambiguous_observation_context")
    for observation, seconds in zip(matches, times, strict=True):
        value = observation.value
        failures = []
        if value.state not in {ValueState.REPORTED, ValueState.ZERO}:
            failures.append("missing_target_value")
        elif value.normalized_value is None or not math.isfinite(value.normalized_value):
            failures.append("target_not_normalized")
        if value.definition != target["definition"]:
            failures.append("target_definition_mismatch")
        if value.normalized_unit != target["unit"]:
            failures.append("target_unit_mismatch")
        row["observations"].append(
            {
                "observation_id": observation.observation_id,
                "test_id": observation.test_id,
                "time_on_stream": observation.time_on_stream.model_dump(mode="json"),
                "test_time_on_stream": record.test.time_on_stream.model_dump(mode="json"),
                "effective_time_seconds": seconds,
                "value": value.model_dump(mode="json"),
                "reason_codes": failures,
            }
        )
        reasons.extend(failures)
    reasons[:] = sorted(set(reasons + errors))
    errors[:] = sorted(set(errors))
    row["status"] = "included" if not reasons else "excluded"
    for observation in row["observations"]:
        observation["status"] = row["status"]
        observation["reason_codes"] = sorted(set(observation["reason_codes"] + reasons))
    return row


def _coverage(rows):
    return {
        name: len({row["entities"].get(name) for row in rows} - {None})
        for name in ("source_id", "recipe_id", "synthesis_id", "test_id", "material_family")
    }


def build_target_eligibility(
    settings,
    *,
    record_ids,
    target,
    target_definition,
    target_unit,
    demo=False,
    rule_version=RULE_VERSION,
    source_acceptance=None,
):
    """Read explicit records and report eligibility; no approvals or snapshots are written."""
    if not record_ids or isinstance(record_ids, str):
        raise ValueError("必须显式提供非空record_ids，不默认扫描整库")
    if any(
        not isinstance(i, str) or not i.strip() or any(c.isspace() for c in i) for i in record_ids
    ):
        raise ValueError("record_ids必须为非空、无空白的ID")
    if any(
        not isinstance(v, str) or not v.strip() for v in (target, target_definition, target_unit)
    ):
        raise ValueError("必须指定非空目标名称、定义和单位")
    if rule_version != RULE_VERSION:
        raise ValueError("不支持的资格规则版本")
    if source_acceptance not in (None, THEMECAT_ACCEPTED) or (source_acceptance and demo):
        raise ValueError("不支持的数据集来源接受策略")
    specification = {"metric": target, "definition": target_definition, "unit": target_unit}
    kind = "synthetic_demo" if demo else "research"
    with transaction(settings.database) as session:
        cache = {}
        rows = [
            _inspect_record(session, i, kind, specification, cache, source_acceptance)
            for i in sorted(set(record_ids))
        ]
    included = [row for row in rows if row["status"] == "included"]
    blocked = any(row["integrity_errors"] for row in rows)
    content = {
        "schema_version": "1",
        "rule_version": rule_version,
        "dataset_kind": kind,
        "scientific_use": not demo,
        "target": specification,
        "input_record_ids": [row["record_id"] for row in rows],
        "eligible_record_ids": [row["record_id"] for row in included],
        "records": rows,
        "counts": {
            "input_records": len(rows),
            "included_records": len(included),
            "excluded_records": len(rows) - len(included),
            "target_observations": sum(len(row["observations"]) for row in rows),
            "included_observations": sum(len(row["observations"]) for row in included),
        },
        "coverage": {"input": _coverage(rows), "included": _coverage(included)},
        "status": "blocked" if blocked else ("ready" if included else "empty"),
        "split_status": "not_performed",
        "metadata": metadata(settings),
    }
    if source_acceptance:
        content["source_acceptance"] = {
            "policy": source_acceptance,
            "input_sha256": THEMECAT_SHA256,
            "basis": "用户接受公开发表的TheMeCat v1数据集作为来源证据；不代表逐行原文核验",
        }
    content_hash = digest(content)
    return {
        "qualification_id": "qualification-" + content_hash,
        "content_sha256": content_hash,
        "content": content,
        "snapshot": None,
    }


def freeze_qualified_snapshot(settings, qualification, *, output=None):
    """Recheck the entire selection, then reuse the existing strict snapshot gate."""
    content = qualification["content"]
    content_hash = digest(content)
    if (
        content_hash != qualification["content_sha256"]
        or qualification["qualification_id"] != "qualification-" + content_hash
    ):
        raise ValueError("资格清单哈希不符")
    specification = content["target"]
    current = build_target_eligibility(
        settings,
        record_ids=content["input_record_ids"],
        target=specification["metric"],
        target_definition=specification["definition"],
        target_unit=specification["unit"],
        demo=content["dataset_kind"] == "synthetic_demo",
        rule_version=content["rule_version"],
        source_acceptance=content.get("source_acceptance", {}).get("policy"),
    )
    if current["content_sha256"] != content_hash:
        raise ValueError("资格清单已过期：记录、审核、原件或软件配置发生变化，须重新检查")
    if content["status"] == "blocked":
        raise ValueError("资格清单存在完整性阻断，禁止冻结快照")
    if not content["eligible_record_ids"]:
        raise ValueError("没有合格目标记录，停止冻结；不回退到整库选择")
    snapshot = build_verified_snapshot(
        settings,
        target=specification["metric"],
        record_ids=content["eligible_record_ids"],
        output=output,
        demo=content["dataset_kind"] == "synthetic_demo",
        source_acceptance=content.get("source_acceptance", {}).get("policy"),
    )
    receipt_path = (
        Path(snapshot["path"]).parent / "qualifications" / f"{current['qualification_id']}.json"
    )
    result = {**current, "snapshot": snapshot, "qualification_path": str(receipt_path)}
    if receipt_path.exists():
        if canonical(json.loads(receipt_path.read_text(encoding="utf-8"))) != canonical(result):
            raise ValueError("资格关联文件已存在且内容不符，拒绝覆盖")
    else:
        write_json(receipt_path, result)
    return result
