import hashlib
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select

from catalyst_ai.governance.quality import Issue, govern
from catalyst_ai.reporting.evidence import digest, metadata, now, summary, write_json, write_new
from catalyst_ai.schemas.domain import ImportRecord, ImportRecordV2
from catalyst_ai.sources.files import read_rows
from catalyst_ai.storage.db import transaction
from catalyst_ai.storage.entities import entities, insert_entities
from catalyst_ai.storage.models import CuratedRow, ImportRunRow, ObservationRow, StagedRow


def ingest(
    input_path: Path, settings, *, dry_run=False, source_kind=None, report_path=None, adapter=None
):
    if dry_run and report_path:
        raise ValueError("dry-run不写文件，请从标准输出读取报告；勿同时指定--report")
    if report_path and report_path.suffix.lower() != ".json":
        raise ValueError("--report必须使用.json后缀")
    if report_path and (report_path.exists() or report_path.with_suffix(".txt").exists()):
        raise ValueError("报告路径已存在，拒绝覆盖")
    content = input_path.read_bytes()
    skipped_empty = 0
    if adapter in {"themecat-v1", "themecat-v2"}:
        from catalyst_ai.sources.themecat import adapt, adapt_v2

        rows, skipped_empty = (adapt_v2 if adapter == "themecat-v2" else adapt)(content)
    else:
        rows = read_rows(content, input_path.suffix)
    if not rows:
        raise ValueError("输入没有数据记录")
    run_id = uuid4().hex
    report = {
        "run_id": run_id,
        "created_at": now(),
        "dry_run": dry_run,
        "input_name": input_path.name,
        "adapter": adapter,
        "skipped_empty_rows": skipped_empty,
        "input_sha256": hashlib.sha256(content).hexdigest(),
        "metadata": metadata(settings),
        "dataset_kinds": [],
        "rows": [],
        "counts": {"total": len(rows), "curated": 0, "staged": 0, "duplicate": 0},
    }
    staged = []
    curated = []
    registry = {}
    seen = set()
    context = (
        transaction(settings.database, initialize=not dry_run)
        if not dry_run or settings.database.exists()
        else nullcontext(None)
    )
    with context as session:
        for i, row in enumerate(rows):
            record_id = f"{run_id}:{i + 1}"
            original = row.raw_payload if row.raw_payload is not None else row.payload
            fingerprint = digest(original)
            issues = []
            record = None
            try:
                if row.error:
                    raise ValueError(row.error)
                model = (
                    ImportRecordV2
                    if isinstance(row.payload, dict) and row.payload.get("schema_version") == "2"
                    else ImportRecord
                )
                record = model.model_validate(row.payload)
                record, issues = govern(record, settings)
                if source_kind and record.source and record.source.kind != source_kind:
                    issues.append(
                        Issue(
                            code="source_kind_mismatch",
                            severity="block",
                            path="source",
                            message="--source与记录来源类型不符",
                        )
                    )
            except (ValidationError, ValueError) as exc:
                issues = [
                    Issue(code="schema_invalid", severity="block", path="$", message=str(exc))
                ]
            duplicate = fingerprint in seen or (
                session is not None
                and session.scalar(
                    select(StagedRow.id).where(StagedRow.fingerprint == fingerprint).limit(1)
                )
            )
            if duplicate:
                issues.append(
                    Issue(
                        code="duplicate_record",
                        severity="block",
                        path="$",
                        message="与本文件/历史导入完全重复；保留导入事件，不重复实体",
                    )
                )
            seen.add(fingerprint)
            if record and record.source and record.extraction:
                for cls, identifier, model, _ in entities(record):
                    key = (cls.__tablename__, identifier)
                    payload = model.model_dump(mode="json")
                    existing = session.get(cls, identifier) if session is not None else None
                    previous = registry.get(key, existing.payload if existing else None)
                    if previous is not None and previous != payload:
                        issues.append(
                            Issue(
                                code="entity_conflict",
                                severity="block",
                                path=f"{key[0]}.{identifier}",
                                message="同ID内容冲突，拒绝覆盖；请审核或使用新版本ID",
                            )
                        )
                    elif cls is ObservationRow and previous is not None and not duplicate:
                        issues.append(
                            Issue(
                                code="duplicate_observation",
                                severity="block",
                                path=f"performance_observation.{identifier}",
                                message="观测ID已存在，不重复计入治理记录",
                            )
                        )
            status = (
                "duplicate"
                if duplicate
                else ("staged" if any(issue.severity == "block" for issue in issues) else "curated")
            )
            if status == "curated":
                for cls, identifier, model, _ in entities(record):
                    registry[(cls.__tablename__, identifier)] = model.model_dump(mode="json")
                curated.append((record_id, record))
            dataset_kind = (
                record.dataset_kind
                if record
                else (
                    row.payload.get("dataset_kind", "unknown")
                    if isinstance(row.payload, dict)
                    else "unknown"
                )
            )
            if dataset_kind not in {"synthetic_demo", "research"}:
                dataset_kind = "unknown"
            report["counts"][status] += 1
            if dataset_kind not in report["dataset_kinds"]:
                report["dataset_kinds"].append(dataset_kind)
            entry = {
                "record_id": record_id,
                "input_locator": row.locator,
                "fingerprint": fingerprint,
                "dataset_kind": dataset_kind,
                "semantic_rule_version": record.schema_version if record else None,
                "status": status,
                "review_status": "pending",
                "governed_sha256": digest(record.model_dump(mode="json")) if record else None,
                "issues": [v.model_dump() for v in issues],
            }
            report["rows"].append(entry)
            staged.append(
                StagedRow(
                    id=record_id,
                    run_id=run_id,
                    input_locator=row.locator,
                    fingerprint=fingerprint,
                    dataset_kind=dataset_kind,
                    status=status,
                    raw_payload=original,
                    payload=record.model_dump(mode="json") if record else None,
                    issues=entry["issues"],
                )
            )
        if not dry_run:
            raw_path = (
                settings.data_dir / "raw" / (report["input_sha256"] + input_path.suffix.lower())
            )
            if raw_path.exists():
                if raw_path.read_bytes() != content:
                    raise ValueError("原始文件哈希路径内容冲突")
            else:
                write_new(raw_path, content)
            report["raw_path"] = str(raw_path.resolve())
            session.add(
                ImportRunRow(
                    id=run_id,
                    created_at=report["created_at"],
                    input_sha256=report["input_sha256"],
                    input_name=input_path.name,
                    metadata_json=report["metadata"],
                    report=report,
                )
            )
            session.flush()
            session.add_all(staged)
            session.flush()
            for record_id, record in curated:
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
    if not dry_run:
        write_json(
            settings.data_dir / "staged" / f"{run_id}.json",
            {
                "report": report,
                "records": [
                    {"record_id": r.id, "raw_payload": r.raw_payload, "payload": r.payload}
                    for r in staged
                ],
            },
        )
        write_json(
            settings.data_dir / "curated" / f"{run_id}.json",
            {
                "run_id": run_id,
                "created_at": report["created_at"],
                "metadata": report["metadata"],
                "review_status": "pending",
                "records": [
                    {"record_id": i, "payload": r.model_dump(mode="json")} for i, r in curated
                ],
            },
        )
        output = report_path or settings.report_dir / f"quality-{run_id}.json"
        write_json(output, report)
        write_new(output.with_suffix(".txt"), summary(report).encode("utf-8"))
    return report
