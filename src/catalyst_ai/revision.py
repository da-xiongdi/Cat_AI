"""Append-only, evidence-backed revision of one staged record."""

import copy
import hashlib
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from catalyst_ai.governance.quality import Issue, govern
from catalyst_ai.reporting.evidence import digest, metadata, now
from catalyst_ai.schemas.domain import ImportRecord, ImportRecordV2
from catalyst_ai.storage.db import transaction
from catalyst_ai.storage.entities import entities, insert_entities
from catalyst_ai.storage.models import (
    CuratedRow,
    ImportRunRow,
    ObservationRow,
    RevisionRow,
    StagedRow,
)


def revise(
    settings,
    parent_id,
    *,
    patch,
    expected_parent_sha256,
    reason,
    operator,
    evidence,
    base_adapter=None,
):
    if not all(
        isinstance(s, str) and s.strip()
        for s in (parent_id, expected_parent_sha256, reason, operator, evidence)
    ):
        raise ValueError("必须提供父记录、父内容哈希、理由、操作人及证据定位")
    if not isinstance(patch, dict) or (not patch and not base_adapter):
        raise ValueError("patch必须是对象；没有适配器时不得为空")
    if base_adapter not in (None, "themecat-v2"):
        raise ValueError("未知修订基线适配器")
    request = {
        "parent_record_id": parent_id,
        "expected_parent_sha256": expected_parent_sha256,
        "patch": patch,
        "reason": reason,
        "operator": operator,
        "evidence": evidence,
        "base_adapter": base_adapter,
    }
    request_hash = digest(request)
    if not settings.database.exists():
        raise ValueError("数据库不存在")
    # create_all only adds missing tables; existing rows and schemas remain untouched.
    with transaction(settings.database, initialize=True) as session:
        parent = session.get(StagedRow, parent_id)
        if parent is None or parent.payload is None:
            raise ValueError("父记录不存在或没有可修订的有效payload")
        if parent.status == "duplicate":
            raise ValueError("不能从重复导入事件修订，请选择其原始记录")
        if digest(parent.payload) != expected_parent_sha256:
            raise ValueError("父记录内容哈希不匹配")
        if digest(parent.raw_payload) != parent.fingerprint:
            raise ValueError("原始行指纹不匹配")
        parent_run = session.get(ImportRunRow, parent.run_id)
        raw_path = Path(parent_run.report["raw_path"])
        if (
            not raw_path.is_file()
            or hashlib.sha256(raw_path.read_bytes()).hexdigest() != parent_run.input_sha256
        ):
            raise ValueError("原始证据文件丢失或哈希不匹配")
        prior = session.scalar(select(RevisionRow).where(RevisionRow.parent_record_id == parent_id))
        if prior:
            if prior.request_sha256 != request_hash:
                raise ValueError("父记录已有不同的修订；请基于最新版本继续修订")
            return session.get(ImportRunRow, session.get(StagedRow, prior.id).run_id).report
        payload = copy.deepcopy(parent.payload)
        if base_adapter:
            if parent_run.report.get("adapter") != "themecat-v1":
                raise ValueError("themecat-v2基线仅支持原始themecat-v1导入记录")
            from catalyst_ai.sources.themecat import adapt_v2

            rows, _ = adapt_v2(raw_path.read_bytes())
            matches = [row for row in rows if row.locator == parent.input_locator]
            if len(matches) != 1 or digest(matches[0].raw_payload) != parent.fingerprint:
                raise ValueError("原始行定位或指纹不匹配")
            payload = matches[0].payload
        if set(patch) - set(payload):
            raise ValueError("patch含未知顶层字段")
        payload.update(copy.deepcopy(patch))
        if payload == parent.payload:
            raise ValueError("修订没有改变内容")
        if payload.get("dataset_kind") != parent.dataset_kind:
            raise ValueError("修订不能改变数据类别")
        model = ImportRecordV2 if payload.get("schema_version") == "2" else ImportRecord
        record, issues = govern(model.model_validate(payload), settings)
        if record.source and record.extraction:
            for cls, identifier, entity, _ in entities(record):
                existing = session.get(cls, identifier)
                if existing and existing.payload != entity.model_dump(mode="json"):
                    issues.append(
                        Issue(
                            code="entity_conflict",
                            severity="block",
                            path=f"{cls.__tablename__}.{identifier}",
                            message="同ID内容冲突，拒绝覆盖；请使用新版本ID",
                        )
                    )
                elif existing and cls is ObservationRow:
                    issues.append(
                        Issue(
                            code="duplicate_observation",
                            severity="block",
                            path=f"performance_observation.{identifier}",
                            message="观测ID已存在；修订需使用独立版本ID",
                        )
                    )
        status = "staged" if any(i.severity == "block" for i in issues) else "curated"
        run_id = uuid4().hex
        record_id = f"{run_id}:1"
        governed = record.model_dump(mode="json")
        meta = metadata(settings)
        details = {
            **request,
            "request_sha256": request_hash,
            "original_fingerprint": parent.fingerprint,
            "input_sha256": parent_run.input_sha256,
            "governed_sha256": digest(governed),
            "semantic_rule_version": record.schema_version,
            "metadata": meta,
        }
        entry = {
            "record_id": record_id,
            "parent_record_id": parent_id,
            "input_locator": parent.input_locator,
            "fingerprint": parent.fingerprint,
            "dataset_kind": parent.dataset_kind,
            "status": status,
            "review_status": "pending",
            "semantic_rule_version": record.schema_version,
            "governed_sha256": digest(governed),
            "issues": [i.model_dump() for i in issues],
        }
        report = {
            "run_id": run_id,
            "created_at": now(),
            "dry_run": False,
            "kind": "revision",
            "input_name": parent_run.input_name,
            "input_sha256": parent_run.input_sha256,
            "raw_path": str(raw_path),
            "metadata": meta,
            "revision": details,
            "dataset_kinds": [parent.dataset_kind],
            "rows": [entry],
            "counts": {
                "total": 1,
                "curated": int(status == "curated"),
                "staged": int(status == "staged"),
                "duplicate": 0,
            },
        }
        session.add(
            ImportRunRow(
                id=run_id,
                created_at=report["created_at"],
                input_sha256=parent_run.input_sha256,
                input_name=parent_run.input_name,
                metadata_json=meta,
                report=report,
            )
        )
        session.flush()
        session.add(
            StagedRow(
                id=record_id,
                run_id=run_id,
                input_locator=parent.input_locator,
                fingerprint=parent.fingerprint,
                dataset_kind=parent.dataset_kind,
                status=status,
                raw_payload=parent.raw_payload,
                payload=governed,
                issues=entry["issues"],
            )
        )
        session.flush()
        session.add(
            RevisionRow(
                id=record_id,
                parent_record_id=parent_id,
                request_sha256=request_hash,
                details=details,
            )
        )
        if status == "curated":
            insert_entities(session, record)
            session.add(
                CuratedRow(
                    id=record_id,
                    source_id=record.source.source_id,
                    extraction_id=record.extraction.extraction_id,
                    recipe_id=record.recipe.recipe_id,
                    synthesis_id=record.synthesis.synthesis_id,
                    test_id=record.test.test_id,
                    dataset_kind=record.dataset_kind,
                    review_status="pending",
                )
            )
    return report
