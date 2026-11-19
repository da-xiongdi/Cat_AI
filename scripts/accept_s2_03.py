"""Freeze S2-03 qualification evidence; optionally register after backup and rehearsal."""

import argparse
import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path

from catalyst_ai.reporting.evidence import digest, write_json
from catalyst_ai.workbench import backup, index, service

ROOT = Path(__file__).resolve().parents[1]
SELECTION = "artifacts/reports/s1-b-20261113-v4/selection.json"
SNAPSHOT = (
    "data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json"
)
SPLIT = "artifacts/reports/themecat-i2-20261110/split-verified.json"
REPORT = "docs/s2_03_acceptance.md"
EXPLANATIONS = {
    "C1": "Adapter copies catalyst_name into material_family; no verified family labels found "
    "in the reviewed snapshot, mapping and source dispositions. Raw names are not families.",
    "C2": "No family comparison or family scores exist. Criteria are fixed before any future "
    "family comparison; prior R1/S2 overall scores were already seen. No claim of global "
    "preregistration. Verified family inventory is empty, so per-family coverage is unavailable; "
    "unclassified partition counts and DOI lists are retained instead of fabricated family zeros.",
    "C3": "Skip all A/B1 family comparisons for missing verified labels. No name-based "
    "classification, B2 or experts; unified-model S3 remains unblocked.",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def tasks(database):
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        return {row["id"]: dict(row) for row in connection.execute("SELECT * FROM task")}


def register(database, target, initial_tasks):
    initial = initial_tasks["S2-03"]
    task = service.get_task(database, "S2-03")
    if (task["status"], task["revision"], task["criteria_version"]) != (
        initial["status"],
        initial["revision"],
        initial["criteria_version"],
    ):
        raise ValueError("task changed since evidence was frozen")
    evidence_id = "S2-family-qualification-" + sha(target)[:16]
    tag = evidence_id + "-"
    index.register(
        database,
        "cat-ai",
        evidence_id,
        "attachment",
        target.relative_to(ROOT).as_posix(),
        request_id=tag + "evidence",
        actor="Codex",
    )
    index.scan(database, "cat-ai")
    service.transition(
        database,
        "S2-03",
        task["revision"],
        "in_progress",
        request_id=tag + "start",
        actor="Codex",
    )
    task = service.get_task(database, "S2-03")
    results = [
        dict(
            criterion_id=c["criterion_id"],
            passed=True,
            evidence_id=evidence_id,
            evidence_version=sha(target),
            explanation=EXPLANATIONS[c["criterion_id"]],
        )
        for c in task["criteria"]
    ]
    service.submit_review(
        database,
        "S2-03",
        task["revision"],
        results,
        "Qualification check complete; skip A/B1 for absent verified family labels. "
        "C2 concerns family scores; prior overall scores and timing limits are disclosed.",
        request_id=tag + "submit",
        actor="Codex",
    )
    task = service.get_task(database, "S2-03")
    service.accept_review(
        database,
        "S2-03",
        task["revision"],
        "Accepted qualification check and justified skip only; no family model or S3 acceptance.",
        request_id=tag + "accept",
        actor="Codex",
    )
    final = service.get_task(database, "S2-03")
    if final["status"] != "done" or final["evidence_needs_review"]:
        raise ValueError("acceptance or evidence availability failed")
    with sqlite3.connect(database) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("foreign key check failed")
    after = tasks(database)
    if any(after[k] != v for k, v in initial_tasks.items() if k != "S2-03"):
        raise ValueError("an unrelated task changed")
    return {
        k: final[k]
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--register", action="store_true")
    args = parser.parse_args()
    out = args.output.resolve()
    out.relative_to(ROOT / "artifacts/reports")
    out.mkdir(parents=True, exist_ok=False)
    database = ROOT / "data/workbench.sqlite"
    initial_tasks = tasks(database)
    initial = initial_tasks["S2-03"]
    if args.register and initial["status"] != "ready":
        raise ValueError("S2-03 must be ready; do not overwrite existing acceptance")
    selection, snapshot, split = [read(p) for p in (SELECTION, SNAPSHOT, SPLIT)]
    for obj in (selection, snapshot, split):
        if digest(obj["content"]) != obj["content_sha256"]:
            raise ValueError("input content hash mismatch")
    binding = selection["content"]["binding"]
    if (
        binding["snapshot_id"] != snapshot["snapshot_id"]
        or binding["split_id"] != split["split_id"]
        or binding["snapshot_sha256"] != snapshot["content_sha256"]
    ):
        raise ValueError("S1 snapshot/split binding mismatch")
    records = {r["record_id"]: r["payload"] for r in snapshot["content"]["records"]}
    rows, partitions, seen = [], {}, set()
    for part, ids in selection["content"]["retained"].items():
        if len(set(ids)) != len(ids) or seen.intersection(ids):
            raise ValueError("duplicate retained record")
        if not set(ids) <= set(split["content"]["splits"][part]["record_ids"]):
            raise ValueError("original partition changed")
        seen.update(ids)
        dois = set()
        for record_id in ids:
            payload = records[record_id]
            doi = payload["source"]["doi"].strip().lower()
            if not doi:
                raise ValueError("missing DOI")
            dois.add(doi)
            rows.append(
                dict(
                    record_id=record_id,
                    partition=part,
                    doi=doi,
                    raw_sample_name=payload["recipe"]["material_family"],
                    verified_family=None,
                    reason="no_verified_record_level_family_label",
                )
            )
        partitions[part] = dict(records=len(ids), doi_count=len(dois), dois=sorted(dois))
    expected = {"train": (454, 26), "validation": (47, 6), "test": (52, 4)}
    if {p: (v["records"], v["doi_count"]) for p, v in partitions.items()} != expected:
        raise ValueError("partition coverage differs from reviewed report")
    doi_sets = [set(v["dois"]) for v in partitions.values()]
    if sum(map(len, doi_sets)) != len(set.union(*doi_sets)):
        raise ValueError("DOI leakage across partitions")
    write_json(
        out / "coverage.json",
        dict(
            partitions=partitions,
            total_records=len(rows),
            total_dois=len(set.union(*doi_sets)),
            raw_sample_name_count=len({r["raw_sample_name"] for r in rows}),
            verified_families=[],
            per_family_coverage=None,
            records=rows,
        ),
    )
    source_paths = [
        SELECTION,
        SNAPSHOT,
        SPLIT,
        REPORT,
        "scripts/accept_s2_03.py",
        "src/catalyst_ai/sources/themecat.py",
        "src/catalyst_ai/schemas/domain.py",
        "configs/s1_species_mapping_v2.json",
        "configs/s1_source_review_v2.json",
    ]
    sources = {p: sha(ROOT / p) for p in source_paths}
    with zipfile.ZipFile(out / "sources.zip", "x", zipfile.ZIP_DEFLATED) as archive:
        for relative in source_paths:
            archive.write(ROOT / relative, relative)
    protected_paths = [ROOT / "data/catalog.sqlite"]
    protected_paths += list((ROOT / "data/raw").rglob("*"))
    protected_paths += list((ROOT / "data/snapshots").rglob("*"))
    protected = {p.relative_to(ROOT).as_posix(): sha(p) for p in protected_paths if p.is_file()}
    write_json(
        out / "acceptance.json",
        dict(
            scope="S2-03 qualification check and justified skip; no family model training or S3",
            actor="Codex",
            local_date="2026-11-18",
            timezone="Asia/Shanghai",
            initial_task=initial,
            sources=sources,
            protected_hashes=protected,
            coverage_sha256=sha(out / "coverage.json"),
            criterion_mapping=EXPLANATIONS,
            decision="skip_all_A_B1_missing_verified_labels",
            unified_model_blocked=False,
            review_basis="Manual source/schema/mapping/disposition review plus reproduced counts. "
            "Absence of trusted labels applies to reviewed inputs; "
            "not an exhaustive literature audit.",
            timing="No family scores generated or consulted; historical R1/S2 overall scores seen. "
            "No assertion of preregistration before all model scores.",
        ),
    )
    if args.register:
        backup.backup_database(database, out / "before.sqlite")
        backup.backup_database(database, out / "rehearsal.sqlite")
        rehearsal = register(out / "rehearsal.sqlite", out / "acceptance.json", initial_tasks)
        actual = register(database, out / "acceptance.json", initial_tasks)
        if actual != rehearsal:
            # Review timestamps can differ; compare stable task attributes below.
            for key in ("status", "revision", "criteria_version", "evidence_needs_review"):
                if actual[key] != rehearsal[key]:
                    raise ValueError("rehearsal and actual task differ")
        backup.backup_database(database, out / "after.sqlite")
        write_json(out / "registration.json", dict(rehearsal=rehearsal, actual=actual))
    if any(sha(ROOT / p) != value for p, value in protected.items()):
        raise ValueError("protected research input changed")
    if any(sha(ROOT / p) != value for p, value in sources.items()):
        raise ValueError("reviewed source changed")
    write_json(
        out / "verification.json",
        dict(
            protected_unchanged=True,
            reviewed_sources_unchanged=True,
            unrelated_tasks_unchanged=tasks(database) == initial_tasks
            if not args.register
            else all(tasks(database)[k] == v for k, v in initial_tasks.items() if k != "S2-03"),
            integrity_check="ok" if args.register else "not_run",
            foreign_key_errors=0 if args.register else None,
            artifact_hashes={p.name: sha(p) for p in out.iterdir() if p.is_file()},
        ),
    )
    print(out.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
