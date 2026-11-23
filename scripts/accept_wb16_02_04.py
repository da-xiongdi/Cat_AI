"""Accept WB-16-02 through 04 after rehearsal on a consistent backup."""

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from catalyst_ai.storage.workbench import atomic_operations
from catalyst_ai.web.config import load
from catalyst_ai.workbench import backup, index, service

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "cat-ai"
REPORT = "docs/workbench/wb16_02_04_acceptance.md"


def auth(action):
    return {"actor": "Codex", "request_id": "wb16-02-04-accept-20261123:" + action}


def snapshot(path):
    with sqlite3.connect(path) as conn:
        return hashlib.sha256("\n".join(conn.iterdump()).encode()).hexdigest()


def accept(db, sha):
    with atomic_operations(db):
        for i in (2, 3, 4):
            task = f"WB-16-{i:02d}"
            artifact = task + "-acceptance-20261123"
            index.register(db, PROJECT, artifact, "document", REPORT, **auth(artifact))
            index.scan(db, PROJECT, document_ids=[artifact])
            item = service.get_task(db, task)
            revision = service.transition(
                db, task, item["revision"], "ready", **auth(task + ":ready")
            )["revision"]
            revision = service.transition(
                db, task, revision, "in_progress", **auth(task + ":start")
            )["revision"]
            revision = service.submit_review(
                db,
                task,
                revision,
                [
                    {
                        "criterion_id": "delivery",
                        "passed": True,
                        "evidence_id": artifact,
                        "evidence_version": sha,
                        "explanation": "验收复核及固定版本见报告",
                    }
                ],
                "交付与验证通过",
                **auth(task + ":submit"),
            )["revision"]
            service.accept_review(
                db, task, revision, "固定证据可用，验收通过", **auth(task + ":accept")
            )
        if hashlib.sha256((ROOT / REPORT).read_bytes()).hexdigest() != sha:
            raise RuntimeError("Evidence changed during acceptance")


def main():
    _, root, db = load(ROOT / "configs/workbench.yaml")
    out = (
        ROOT
        / "artifacts"
        / (
            "wb16-02-04-accept-"
            + datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d-%H%M%S-%f")
        )
    )
    out.mkdir(parents=True)
    content = backup.create_bundle(db, root)
    preview = backup.preview_bundle(content)
    (out / "before.zip").write_bytes(content)
    backup.restore_bundle(content, out / "restored", preview["sha256"])
    # Use a database copy whose configured workspace remains the live workspace,
    # so rehearsal observes the same indexed evidence as the eventual operation.
    rehearsal = out / "rehearsal.sqlite"
    backup.backup_database(db, rehearsal)
    before = snapshot(rehearsal)
    sha = hashlib.sha256((ROOT / REPORT).read_bytes()).hexdigest()
    accept(rehearsal, sha)
    for i in (2, 3, 4):
        t = service.get_task(rehearsal, f"WB-16-{i:02d}")
        assert t["status"] == "done" and not t["evidence_needs_review"]
    if snapshot(db) != before:
        raise RuntimeError("Production database changed since rehearsal snapshot")
    accept(db, sha)
    for i in (2, 3, 4):
        t = service.get_task(db, f"WB-16-{i:02d}")
        assert t["status"] == "done" and not t["evidence_needs_review"]
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
    print("missing before:", len(preview["manifest"]["missing"]))
    print("missing after:", len(after_preview["manifest"]["missing"]))


if __name__ == "__main__":
    main()
