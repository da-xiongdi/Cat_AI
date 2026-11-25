"""Rehearse and record the WB-16-05 acceptance with fixed evidence."""

import hashlib
import json
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from catalyst_ai.storage.workbench import atomic_operations
from catalyst_ai.web.config import load
from catalyst_ai.workbench import backup, index, service

ROOT = Path(__file__).resolve().parents[1]
REPORT = "docs/workbench/wb16_05_verification.md"
TASK = "WB-16-05"
EVIDENCE = "WB-16-05-acceptance-20261123"


def snapshot(db):
    with closing(sqlite3.connect(db)) as conn:
        return hashlib.sha256("\n".join(conn.iterdump()).encode()).hexdigest()


def auth(action):
    return {"actor": "Codex", "request_id": "wb16-05-accept-20261123:" + action}


def accept(db, sha):
    with atomic_operations(db):
        index.register(db, "cat-ai", EVIDENCE, "document", REPORT, **auth("register"))
        index.scan(db, "cat-ai", document_ids=[EVIDENCE])
        task = service.get_task(db, TASK)
        revision = service.transition(db, TASK, task["revision"], "ready", **auth("ready"))[
            "revision"
        ]
        revision = service.transition(db, TASK, revision, "in_progress", **auth("start"))[
            "revision"
        ]
        revision = service.submit_review(
            db,
            TASK,
            revision,
            [
                {
                    "criterion_id": "delivery",
                    "passed": True,
                    "evidence_id": EVIDENCE,
                    "evidence_version": sha,
                    "explanation": "联调与回归记录及限制见固定证据",
                }
            ],
            "跨页面联调与兼容回归通过",
            **auth("submit"),
        )["revision"]
        if hashlib.sha256((ROOT / REPORT).read_bytes()).hexdigest() != sha:
            raise RuntimeError("Evidence changed during acceptance")
        service.accept_review(db, TASK, revision, "固定证据可用，验收通过", **auth("accept"))


def main():
    _, root, db = load(ROOT / "configs/workbench.yaml")
    out = (
        ROOT
        / "artifacts"
        / ("wb16-05-accept-" + datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d-%H%M%S-%f"))
    )
    out.mkdir(parents=True)
    content = backup.create_bundle(db, root)
    preview = backup.preview_bundle(content)
    (out / "before.zip").write_bytes(content)
    sha = hashlib.sha256((ROOT / REPORT).read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="wb16-05-accept-") as temp:
        copy = Path(temp) / "rehearsal.sqlite"
        backup.backup_database(db, copy)
        before = snapshot(copy)
        accept(copy, sha)
        task = service.get_task(copy, TASK)
        assert task["status"] == "done" and not task["evidence_needs_review"]
        if snapshot(db) != before:
            raise RuntimeError("Production database changed during rehearsal")
    accept(db, sha)
    task = service.get_task(db, TASK)
    assert task["status"] == "done" and not task["evidence_needs_review"]
    after = backup.create_bundle(db, root)
    after_preview = backup.preview_bundle(after)
    (out / "after.zip").write_bytes(after)
    (out / "result.json").write_text(
        json.dumps(
            {
                "before_sha256": preview["sha256"],
                "after_sha256": after_preview["sha256"],
                "missing_before": preview["manifest"]["missing"],
                "missing_after": after_preview["manifest"]["missing"],
                "evidence_sha256": sha,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(out)


if __name__ == "__main__":
    main()
