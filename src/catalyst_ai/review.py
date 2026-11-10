from uuid import uuid4

from catalyst_ai.reporting.evidence import digest, metadata, now
from catalyst_ai.storage.db import transaction
from catalyst_ai.storage.models import CuratedRow, ReviewRow, StagedRow


def review_record(settings, record_id, *, reviewer, decision, evidence, acknowledge_warnings=False):
    if not reviewer.strip() or not evidence.strip():
        raise ValueError("审核必须提供非空复核人和证据定位/核对说明")
    if decision not in {"verified", "rejected"}:
        raise ValueError("decision必须为verified/rejected")
    with transaction(settings.database) as session:
        record = session.get(CuratedRow, record_id)
        if record is None:
            raise ValueError("只能复核已通过治理的curated记录；staged问题需更正后重新导入")
        staged = session.get(StagedRow, record_id)
        if decision == "verified" and staged.issues and not acknowledge_warnings:
            raise ValueError("存在warning；核对每项后须显式--acknowledge-warnings")
        review_id = uuid4().hex
        event = {
            "review_id": review_id,
            "record_id": record_id,
            "reviewer": reviewer,
            "decision": decision,
            "evidence": evidence,
            "created_at": now(),
            "payload_sha256": digest(staged.payload),
            "metadata": {
                **metadata(settings),
                "scope": "whole_record",
                "acknowledge_warnings": acknowledge_warnings,
            },
        }
        session.add(
            ReviewRow(
                id=review_id,
                record_id=record_id,
                reviewer=reviewer,
                decision=decision,
                evidence=evidence,
                created_at=event["created_at"],
                payload_sha256=event["payload_sha256"],
                metadata_json=event["metadata"],
            )
        )
        record.review_status = decision
    return event
