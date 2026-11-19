"""Verify frozen S3-02 evidence and register acceptance after rehearsal."""

import json
import zipfile
from pathlib import Path

from accept_s3_01 import check_db, read, sha, tasks

from catalyst_ai.reporting.evidence import write_json
from catalyst_ai.workbench import backup, index, service

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data/workbench.sqlite"
SOURCE = ROOT / "artifacts/reports/s3-02-20261118-02c"
OUT = ROOT / "artifacts/reports/s3-02-20261118-02d"
TARGET = OUT / "acceptance.json"


def register(db, initial):
    task = service.get_task(db, "S3-02")
    assert (task["status"], task["revision"], task["criteria_version"]) == initial
    version = sha(TARGET)
    eid = "S3-02-end-to-end-" + version[:16]
    index.register(
        db,
        "cat-ai",
        eid,
        "attachment",
        TARGET.relative_to(ROOT).as_posix(),
        request_id=eid + "-evidence",
        actor="Codex",
    )
    index.scan(db, "cat-ai")
    for status in ("ready", "in_progress"):
        task = service.get_task(db, "S3-02")
        service.transition(
            db, "S3-02", task["revision"], status, request_id=eid + "-" + status, actor="Codex"
        )
    task = service.get_task(db, "S3-02")
    results = [
        dict(criterion_id=k, passed=True, evidence_id=eid, evidence_version=version, explanation=v)
        for k, v in {
            "C1": (
                "Real default and custom training, specified packages, "
                "replay and failure paths verified."
            ),
            "C2": (
                "Frozen configurations, bindings, code and environment, "
                "hashes and test evidence verified."
            ),
        }.items()
    ]
    service.submit_review(
        db,
        "S3-02",
        task["revision"],
        results,
        "End-to-end acceptance evidence verified.",
        request_id=eid + "-submit",
        actor="Codex",
    )
    task = service.get_task(db, "S3-02")
    service.accept_review(
        db, "S3-02", task["revision"], "Accept S3-02.", request_id=eid + "-accept", actor="Codex"
    )
    task = service.get_task(db, "S3-02")
    assert task["status"] == "done" and not task["evidence_needs_review"]
    check_db(db)
    return {
        k: task[k]
        for k in (
            "id",
            "status",
            "revision",
            "criteria_version",
            "evidence_needs_review",
            "reviews",
        )
    }


def main():
    assert not OUT.exists()
    before_tasks = tasks(DB)
    initial = before_tasks["S3-02"]
    assert initial["status"] == "planned" and initial["criteria_version"] == 2
    assert all(before_tasks[t]["status"] == "done" for t in ("S2-02", "S3-01"))
    check_db(DB)
    evidence = read(SOURCE / "evidence_hashes.json")
    protected = read(ROOT / "artifacts/reports/s3-01-20261118-01/protected_hashes.json")
    for manifest in (evidence, protected):
        assert all((ROOT / p).is_file() and sha(ROOT / p) == h for p, h in manifest.items())
    code = read(SOURCE / "code_hashes.json")
    with zipfile.ZipFile(SOURCE / "code.zip") as archive:
        import hashlib

        assert all(
            hashlib.sha256(archive.read(p.replace("\\", "/"))).hexdigest() == h
            for p, h in code.items()
        )
    replay = read(SOURCE / "replay-checks.json")
    assert len(replay) == 5 and all(
        r["equal"] and r["count"] == 47 and r["returncode"] == 0 for r in replay.values()
    )
    assert all(
        (SOURCE / (name + ".exit")).read_text().strip() == "0"
        for name in ("pytest", "ruff", "format")
    )
    files = [
        p
        for folder in (
            SOURCE,
            ROOT / "artifacts/reports/s3-02-20261118-02a",
            ROOT / "artifacts/reports/s3-02-20261118-02b",
        )
        for p in folder.rglob("*")
        if p.is_file()
    ]
    hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in files}
    OUT.mkdir()
    write_json(
        TARGET,
        {
            "scope": "S3-02 end-to-end acceptance",
            "task_before": initial,
            "criteria": {
                "C1": "training, prediction and failures",
                "C2": "configuration, bindings, versions, hashes and tests",
            },
            "evidence_sha256": hashes,
            "protected_manifest_sha256": sha(
                ROOT / "artifacts/reports/s3-01-20261118-01/protected_hashes.json"
            ),
            "code_snapshot_changes": [
                p for p, h in code.items() if not (ROOT / p).is_file() or sha(ROOT / p) != h
            ],
        },
    )
    backup.backup_database(DB, OUT / "before.sqlite")
    backup.backup_database(OUT / "before.sqlite", OUT / "rehearsal.sqlite")
    state = (initial["status"], initial["revision"], initial["criteria_version"])
    trial = register(OUT / "rehearsal.sqlite", state)
    assert all(
        tasks(OUT / "rehearsal.sqlite")[k] == v for k, v in before_tasks.items() if k != "S3-02"
    )
    assert tasks(DB) == before_tasks
    assert all(sha(ROOT / p) == h for p, h in {**evidence, **protected, **hashes}.items())
    actual = register(DB, state)
    assert all(
        trial[k] == actual[k]
        for k in ("status", "revision", "criteria_version", "evidence_needs_review")
    )
    assert all(tasks(DB)[k] == v for k, v in before_tasks.items() if k != "S3-02")
    backup.backup_database(DB, OUT / "after.sqlite")
    assert all(sha(ROOT / p) == h for p, h in {**evidence, **protected, **hashes}.items())
    write_json(OUT / "registration.json", {"rehearsal": trial, "actual": actual})
    write_json(
        OUT / "verification.json",
        {
            "integrity_check": "ok",
            "foreign_key_errors": 0,
            "protected_unchanged": True,
            "evidence_unchanged": True,
            "unrelated_tasks_unchanged": True,
            "acceptance_sha256": sha(TARGET),
            "snapshots_sha256": {
                n: sha(OUT / n) for n in ("before.sqlite", "rehearsal.sqlite", "after.sqlite")
            },
        },
    )
    print(json.dumps({k: actual[k] for k in ("id", "status", "revision", "criteria_version")}))


if __name__ == "__main__":
    main()
