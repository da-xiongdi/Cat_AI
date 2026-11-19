"""Freeze S3-01 evidence, rehearse and register acceptance through the workbench."""

import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path

from catalyst_ai.reporting.evidence import write_json
from catalyst_ai.workbench import backup, index, service

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/reports/s3-01-20261118-01"
DB = ROOT / "data/workbench.sqlite"
TARGET = OUT / "acceptance.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def tasks(db):
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as c:
        c.row_factory = sqlite3.Row
        return {r["id"]: dict(r) for r in c.execute("SELECT * FROM task")}


def check_db(db):
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as c:
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not c.execute("PRAGMA foreign_key_check").fetchall()


def register(db, initial):
    task = service.get_task(db, "S3-01")
    assert (task["status"], task["revision"], task["criteria_version"]) == initial
    assert {c["criterion_id"] for c in task["criteria"]} == {"C1", "C2"}
    version = sha(TARGET)
    evidence_id = "S3-01-comparison-" + version[:16]
    tag = evidence_id + "-"
    index.register(
        db,
        "cat-ai",
        evidence_id,
        "attachment",
        TARGET.relative_to(ROOT).as_posix(),
        request_id=tag + "evidence",
        actor="Codex",
    )
    index.scan(db, "cat-ai")
    for status in ("ready", "in_progress"):
        task = service.get_task(db, "S3-01")
        service.transition(
            db, "S3-01", task["revision"], status, request_id=tag + status, actor="Codex"
        )
    task = service.get_task(db, "S3-01")
    explanations = {
        "C1": (
            "Same frozen snapshot, 553 S1 v4 records, original partitions, paired folds and model "
            "parameters; bindings and fold isolation checked."
        ),
        "C2": (
            "Independent row-level DOI-equal OOF calculation and three-layer reporting; "
            "F_base/extra_trees wins, validation is not used for selection and test is historical."
        ),
    }
    results = [
        dict(
            criterion_id=k,
            passed=True,
            evidence_id=evidence_id,
            evidence_version=version,
            explanation=v,
        )
        for k, v in explanations.items()
    ]
    service.submit_review(
        db,
        "S3-01",
        task["revision"],
        results,
        "Formal paired comparison and independent recalculation completed.",
        request_id=tag + "submit",
        actor="Codex",
    )
    task = service.get_task(db, "S3-01")
    service.accept_review(
        db,
        "S3-01",
        task["revision"],
        "Accept S3-01 only; F_base selected. S3-02 remains separate.",
        request_id=tag + "accept",
        actor="Codex",
    )
    task = service.get_task(db, "S3-01")
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
    for name in (
        "acceptance.json",
        "before.sqlite",
        "rehearsal.sqlite",
        "after.sqlite",
        "registration.json",
        "verification.json",
    ):
        if (OUT / name).exists():
            raise FileExistsError(OUT / name)
    initial_tasks = tasks(DB)
    initial = initial_tasks["S3-01"]
    assert initial["status"] == "planned" and initial["criteria_version"] == 2
    assert initial_tasks["S2-02"]["status"] == "done"
    check_db(DB)
    code_hashes = read(OUT / "code_hashes.json")
    with zipfile.ZipFile(OUT / "code.zip") as archive:
        for name, expected in code_hashes.items():
            assert hashlib.sha256(archive.read(name.replace("\\", "/"))).hexdigest() == expected
    protected = read(OUT / "protected_hashes.json")
    assert all((ROOT / p).is_file() and sha(ROOT / p) == h for p, h in protected.items())
    comparison = read(OUT / "verification-01c.json")
    assert comparison["prediction_rows_match_reports"] and comparison["all_primary_metrics_match"]
    for p, h in comparison["inputs_sha256"].items():
        assert sha(ROOT / p) == h
    assert comparison["checks"][1]["selected"] == {"feature_set": "F_base", "model": "extra_trees"}
    files = [p for p in OUT.iterdir() if p.is_file() and p.suffix not in (".sqlite", ".backup")]
    for folder in (
        ROOT / "artifacts/runs/s3-20261118-01",
        ROOT / "artifacts/models/s3-20261118-01",
    ):
        files.extend(p for p in folder.rglob("*") if p.is_file())
    files += [
        ROOT / p
        for p in (
            "configs/s3_20261118_01_r1.yaml",
            "configs/s3_20261118_01_r2.yaml",
            "docs/s3_01_comparison.md",
            "docs/s3_01_acceptance.md",
            "scripts/accept_s3_01.py",
        )
    ]
    hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in files}
    changed = [p for p, h in code_hashes.items() if not (ROOT / p).is_file() or sha(ROOT / p) != h]
    write_json(
        TARGET,
        dict(
            scope="S3-01 formal comparison only",
            task_before=initial,
            criteria={
                "C1": "same bound input and paired design",
                "C2": "row-level recalculation, reporting and truthful selection",
            },
            selected={"feature_set": "F_base", "model": "extra_trees"},
            r2_oof_paper_equal_mae=5.373463976413471,
            current_code_changes_since_training=changed,
            files_sha256=hashes,
            protected_manifest_sha256=sha(OUT / "protected_hashes.json"),
        ),
    )
    before = OUT / "before.sqlite"
    rehearsal = OUT / "rehearsal.sqlite"
    backup.backup_database(DB, before)
    backup.backup_database(before, rehearsal)
    state = (initial["status"], initial["revision"], initial["criteria_version"])
    trial = register(rehearsal, state)
    assert all(tasks(rehearsal)[k] == v for k, v in initial_tasks.items() if k != "S3-01")
    assert tasks(DB) == initial_tasks, "actual database changed during rehearsal"
    assert all(sha(ROOT / p) == h for p, h in hashes.items())
    actual = register(DB, state)
    for k in ("status", "revision", "criteria_version", "evidence_needs_review"):
        assert trial[k] == actual[k]
    assert all(tasks(DB)[k] == v for k, v in initial_tasks.items() if k != "S3-01")
    backup.backup_database(DB, OUT / "after.sqlite")
    write_json(OUT / "registration.json", dict(rehearsal=trial, actual=actual))
    assert all(sha(ROOT / p) == h for p, h in hashes.items())
    assert all(sha(ROOT / p) == h for p, h in protected.items())
    write_json(
        OUT / "verification.json",
        dict(
            integrity_check="ok",
            foreign_key_errors=0,
            protected_unchanged=True,
            frozen_files_unchanged=True,
            unrelated_tasks_unchanged=True,
            evidence_available=True,
            acceptance_sha256=sha(TARGET),
            snapshots_sha256={
                name: sha(OUT / name)
                for name in ("before.sqlite", "rehearsal.sqlite", "after.sqlite")
            },
        ),
    )
    print(
        json.dumps(
            {
                k: actual[k]
                for k in ("id", "status", "revision", "criteria_version", "evidence_needs_review")
            }
        )
    )


if __name__ == "__main__":
    main()
