"""Verify WB-15, rehearse acceptance and restoration, and apply with --apply."""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from importlib.metadata import distributions
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from zipfile import ZIP_DEFLATED, ZipFile
from zoneinfo import ZoneInfo

from close_wb13 import (
    ROOT,
    Deployment,
    file_hashes,
    files_under,
    make_bundle,
    observation,
    relative,
    require,
    run_command,
    sha,
    snapshot,
    source_refs,
    write_json,
)
from close_wb14 import changes
from fastapi.testclient import TestClient

from catalyst_ai.storage.workbench import SCHEMA_VERSION, atomic_operations
from catalyst_ai.web.app import create_app
from catalyst_ai.web.config import load
from catalyst_ai.workbench import backup, index, plans, queries, service

CONFIG = "configs/workbench.yaml"
PLAN = "docs/workbench/wb15_implementation_plan.md"
INTEGRATION = "docs/workbench/wb15_04_report.md"
BASELINE = "docs/workbench/wb15_01_baseline.md"
PLAN_ID = "WB-15-plan"
PARENT = "WB-15"
CHILDREN = tuple(f"WB-15-{i:02}" for i in range(1, 6))
CLOSE = (*CHILDREN[1:], PARENT)
CRITERIA = {
    "WB-15-02": {
        "recent": "分类、焦点、去重、历史及人工安排复核",
        "readiness": "依赖、固定证据与验收入口",
    },
    "WB-15-03": {
        "preview": "共用文档预览、章节定位与实时核对",
        "scope": "项目和引用身份、工作区边界及写入并发",
    },
    "WB-15-04": {"integration": "两类任务往返、科研路线与异常修正复核"},
    "WB-15-05": {
        "regression": "专项验收、兼容回归及版本清单",
        "restore": "隔离部署、备份恢复和科研数据保护",
    },
    PARENT: dict(
        zip(
            CHILDREN,
            (
                "基线与展示规则",
                "分类近期任务视图",
                "任务与计划章节关联",
                "联调与异常复核",
                "专项验收与交付",
            ),
            strict=True,
        )
    ),
}
TABLES = {
    "activity",
    "artifact",
    "artifact_location",
    "artifact_revision",
    "criterion",
    "evidence",
    "index_observation",
    "index_scan",
    "published_index",
    "request_log",
    "review",
    "task",
    "task_plan_verification",
}
ROUTES = {
    "/": None,
    "/next-work": "当前暂无近期任务。",
    "/next-work?category=workbench": "历史任务",
    "/tasks": None,
    "/tasks/S1A-01": None,
    "/tasks/WB-15": None,
    "/tasks/WB-15-02/plans/WB-15-02-primary-plan": 'id="plan-section"',
    "/artifacts": None,
    "/artifacts/WB-15-plan": "文件预览",
    "/documents": None,
    "/decisions": None,
    "/predictions": None,
    "/roadmap": None,
    "/foundation": None,
}


class Closeout(Deployment):
    def __init__(self, project, out, expected_files):
        self.project = project
        self.out = out
        self.expected_files = expected_files
        self.proofs = {
            CHILDREN[0]: ("WB-15-01-report", BASELINE),
            **{
                task: (f"{task}-evidence", relative(out / "acceptance-evidence.json"))
                for task in CHILDREN[1:]
            },
        }

    def apply(self, db, before):
        with atomic_operations(db) as conn:
            require(observation(conn) == before, "management database changed since backup")
            require(
                file_hashes(self.expected_files) == self.expected_files, "release files changed"
            )
            for task in CHILDREN[1:]:
                ident, path = self.proofs[task]
                index.register(db, self.project, ident, "attachment", path, **self.auth(ident))
            index.register(
                db,
                self.project,
                "WB-15-04-report",
                "document",
                INTEGRATION,
                **self.auth("integration-report"),
            )
            index.scan(
                db,
                self.project,
                document_ids=["WB-15-04-report", *(self.proofs[task][0] for task in CHILDREN[1:])],
            )
            for task in (*CHILDREN, PARENT):
                ref = f"{task}-primary-plan"
                checked = plans.inspect_task_plan_reference(db, self.project, ref)
                registered = checked["reference"]
                require(
                    registered["document_id"] == PLAN_ID
                    and registered["task_id"] == task
                    and checked["status"] == "valid"
                    and checked["current_sha256"] == self.expected_files[PLAN],
                    f"unexpected plan registration: {task}",
                )
            for task in CLOSE:
                current = service.get_task(db, task)
                criteria = CRITERIA[task]
                evidence_paths = (
                    [self.proofs[key][1] for key in criteria]
                    if task == PARENT
                    else [self.proofs[task][1]]
                )
                if task == "WB-15-04":
                    evidence_paths.append(INTEGRATION)
                service.update_task(
                    db,
                    task,
                    current["revision"],
                    {
                        "deliverables": list(
                            dict.fromkeys([*current["deliverables"], *evidence_paths])
                        ),
                        "criteria": [
                            {"id": key, "description": text} for key, text in criteria.items()
                        ],
                    },
                    **self.auth(task + ":criteria"),
                )
                self.start(db, task)
                self.accept(db, task, [(key, key if task == PARENT else task) for key in criteria])
            require(
                file_hashes(self.expected_files) == self.expected_files, "evidence files changed"
            )
            after = observation(conn)
            delta = changes(before, after, TABLES)
            for table in delta.keys() - {"task", "evidence", "published_index"}:
                require(delta[table]["prior_rows_changed"] == 0, f"prior rows changed in {table}")
            require(
                [r for r in before["task"] if r["id"] not in CLOSE]
                == [r for r in after["task"] if r["id"] not in CLOSE],
                "other tasks changed",
            )
            require(
                set(r["id"] for r in before["task"]) == set(r["id"] for r in after["task"]),
                "unexpected task registration",
            )
            require(delta["evidence"]["prior_rows_changed"] == 0, "pre-existing evidence changed")
        return delta

    def verify(self, db):
        records = {}
        for task in (*CHILDREN, PARENT):
            record = service.get_task(db, task)
            require(record["status"] == "done" and not record["evidence_needs_review"], task)
            reference = plans.inspect_task_plan_reference(db, self.project, f"{task}-primary-plan")
            require(reference["status"] == "valid", f"plan not valid: {task}")
            reviews = [r for r in record["reviews"] if r["kind"] == "acceptance"]
            require(len(reviews) == 1, f"expected a single acceptance: {task}")
            records[task] = {
                "status": record["status"],
                "revision": record["revision"],
                "acceptance_id": reviews[0]["id"],
                "accepted_at": reviews[0]["created_at"],
                "plan_sha256": reference["current_sha256"],
                "evidence": reviews[0]["results"],
            }
        return records


def smoke_routes(get, release_hash, research_empty):
    routes = {
        **ROUTES,
        "/next-work": ROUTES["/next-work"] if research_empty else "近期任务",
        f"/artifacts/{PLAN_ID}?version={release_hash}": "WB-15 下一步工作与计划交接实施方案",
        f"/artifacts/{PLAN_ID}?task=WB-15-03&reference=WB-15-03-primary-plan": 'id="plan-section"',
    }
    statuses = {}
    for path, marker in routes.items():
        status, body = get(path)
        require(status == 200 and (marker is None or marker in body), f"route not verified: {path}")
        statuses[path] = status
    return statuses


def isolated_smoke(db, settings, root, release_hash, research_empty):
    app = create_app(db, root, settings.project_id, settings.project_name)
    before = snapshot(db)
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:

        def fetch(route):
            response = client.get(route)
            return response.status_code, response.text

        statuses = smoke_routes(fetch, release_hash, research_empty)
    require(before == snapshot(db), "isolated browsing changed management data")
    return {"routes": statuses, "browse_rows_equal": True}


def configured_smoke(out, settings, release_hash, research_empty, db):
    base = f"http://127.0.0.1:{settings.port}"

    def fetch(route):
        with urlopen(base + route, timeout=3) as response:
            return response.status, response.read().decode("utf-8")

    with (out / "serve-formal.log").open("xb") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "catalyst_ai.cli", "workbench", "serve", "--config", CONFIG],
            cwd=ROOT,
            stdout=log,
            stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            for _ in range(60):
                require(proc.poll() is None, "configured workbench startup failed")
                try:
                    if fetch("/")[0] == 200:
                        break
                except URLError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("configured workbench did not respond")
            before = snapshot(db)
            statuses = smoke_routes(fetch, release_hash, research_empty)
            require(before == snapshot(db), "configured workbench browsing changed management data")
            return {"routes": statuses, "browse_rows_equal": True}
        finally:
            if proc.poll() is None:
                proc.terminate()
            proc.wait(timeout=10)


def freeze_release(out):
    paths = files_under("src", "tests") | {
        CONFIG,
        PLAN,
        BASELINE,
        INTEGRATION,
        "pyproject.toml",
        "uv.lock",
        "scripts/close_wb13.py",
        "scripts/close_wb14.py",
        "scripts/close_wb15.py",
        "scripts/register_wb15.py",
        "scripts/verify_wb15_browser.py",
        "scripts/wb15_01_samples.py",
    }
    release = file_hashes(paths)
    with ZipFile(out / "release-source.zip", "x", ZIP_DEFLATED) as archive:
        for name, digest in release.items():
            raw = (ROOT / name).read_bytes()
            require(sha(raw) == digest, f"file changed during archiving: {name}")
            archive.writestr(name, raw)
    write_json(
        out / "release.json",
        {
            "git_head": run_command(out, "git-head.txt", ["git", "rev-parse", "HEAD"])
            .decode()
            .strip(),
            "config": CONFIG,
            "schema": SCHEMA_VERSION,
            "python": sys.version,
            "installed": dict(sorted((d.metadata["Name"], d.version) for d in distributions())),
            "source_sha256": release,
            "archive_sha256": sha((out / "release-source.zip").read_bytes()),
        },
    )
    return release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    zone = ZoneInfo("Asia/Shanghai")
    out = ROOT / "artifacts" / datetime.now(zone).strftime("wb15-closeout-%Y%m%d-%H%M%S-%f")
    out.mkdir(parents=True)
    print(relative(out), flush=True)
    settings, root, live = load(ROOT / CONFIG)
    require(root == ROOT and live == ROOT / "data/workbench.sqlite", "unexpected workbench target")
    release = freeze_release(out)
    run_command(out, "pytest.txt", [sys.executable, "-m", "pytest", "-q"])
    ruff = str(Path(sys.executable).with_name("ruff.exe" if os.name == "nt" else "ruff"))
    scoped = [
        "src",
        "tests",
        "scripts/close_wb15.py",
        "scripts/verify_wb15_browser.py",
        "scripts/register_wb15.py",
        "scripts/wb15_01_samples.py",
    ]
    run_command(out, "ruff.txt", [ruff, "check", *scoped])
    run_command(out, "ruff-format.txt", [ruff, "format", "--check", *scoped])
    run_command(
        out,
        "edge.txt",
        [sys.executable, "scripts/verify_wb15_browser.py", "--evidence-dir", str(out)],
    )

    initial_db = out / "before.sqlite"
    backup.backup_database(live, initial_db)
    before = snapshot(initial_db)
    statuses = {r["id"]: r["status"] for r in before["task"]}
    require(
        all(statuses.get(t) == "done" for t in ("WB-13", "WB-14", CHILDREN[0]))
        and all(statuses.get(t) == "planned" for t in CLOSE),
        "unexpected formal task states",
    )
    protected = file_hashes(
        files_under(
            "data/raw",
            "data/staged",
            "data/curated",
            "data/snapshots",
            "artifacts/models",
            "artifacts/runs",
            "artifacts/reports",
            "artifacts/workbench-predictions",
        )
        | {"data/catalog.sqlite"}
    )
    source_hashes = file_hashes(source_refs(before))
    prior_flags = {
        ident: service.get_task(initial_db, ident)["evidence_needs_review"]
        for ident, status in statuses.items()
        if status == "done"
    }
    current = queries.query(initial_db, settings.project_id)["next_work"]
    view = {
        key: {
            "active": [r["id"] for r in v["active"]],
            "history": len(v["history"]),
            "missing_primary_plan": [
                r["id"] for r in (*v["active"], *v["history"]) if r["plan"] is None
            ],
            "focus": v["focus_id"],
        }
        for key, v in current.items()
    }
    write_json(out / "baseline.json", {"view": view, "statuses": statuses})
    before_bundle, _ = make_bundle(initial_db, root, out, "before")
    research_empty = not view["research"]["active"]
    evidence_db = out / "service-rehearsal.sqlite"
    backup.backup_database(initial_db, evidence_db)
    smoke = isolated_smoke(evidence_db, settings, root, release[PLAN], research_empty)
    write_json(out / "isolated-smoke.json", smoke)
    require(file_hashes(protected) == protected, "research files changed during rehearsal")
    write_json(
        out / "protection.json",
        {"file_sha256": protected, "prior_evidence_review_flags": prior_flags},
    )
    evidence_files = file_hashes(
        relative(out / name)
        for name in (
            "release.json",
            "pytest.txt",
            "ruff.txt",
            "ruff-format.txt",
            "edge.json",
            "edge.txt",
            "edge-1366x768.png",
            "edge-1920x1080.png",
            "edge-390x844.png",
            "baseline.json",
            "isolated-smoke.json",
            "protection.json",
        )
    )
    proof = out / "acceptance-evidence.json"
    write_json(
        proof,
        {
            "tasks": CRITERIA,
            "result": "passed",
            "files_sha256": evidence_files,
            "predeployment_restore": before_bundle,
            "integration_report": INTEGRATION,
        },
    )
    expected = {
        **release,
        **source_hashes,
        **protected,
        **evidence_files,
        relative(proof): sha(proof.read_bytes()),
    }
    closeout = Closeout(settings.project_id, out, expected)
    rehearsal = out / "acceptance-rehearsal.sqlite"
    backup.backup_database(initial_db, rehearsal)
    rehearsal_delta = closeout.apply(rehearsal, before)
    rehearsal_bundle, rehearsal_restored = make_bundle(rehearsal, root, out, "rehearsal")
    rehearsal_records = closeout.verify(rehearsal)
    require(
        closeout.verify(rehearsal_restored) == rehearsal_records, "rehearsal restore reviews differ"
    )
    result = {
        "formal": False,
        "before_restore": before_bundle,
        "rehearsal_restore": rehearsal_bundle,
        "rehearsal_records": rehearsal_records,
        "rehearsal_delta": rehearsal_delta,
    }
    write_json(out / "rehearsal-verification.json", result)
    print("Isolated acceptance and restoration verified", flush=True)

    if args.apply:
        delta = closeout.apply(live, before)
        records = closeout.verify(live)
        post_acceptance = snapshot(live)
        write_json(out / "formal-acceptance-rows.json", records)
        runtime = configured_smoke(out, settings, release[PLAN], research_empty, live)
        after_db = out / "after.sqlite"
        backup.backup_database(live, after_db)
        startup_delta = changes(post_acceptance, snapshot(after_db), {"request_log"})
        require(
            startup_delta == {"request_log": {"prior_rows_changed": 0, "new_rows": 1}},
            "unexpected formal service startup changes",
        )
        after_bundle, restored = make_bundle(after_db, root, out, "after")
        require(closeout.verify(restored) == records, "restored reviews differ")
        require(
            all(
                service.get_task(restored, ident)["evidence_needs_review"] == flag
                for ident, flag in prior_flags.items()
            ),
            "prior accepted evidence flags changed",
        )
        require(file_hashes(expected) == expected, "protected files changed during delivery")
        result.update(
            formal=True,
            records=records,
            formal_delta=delta,
            formal_runtime=runtime,
            startup_delta=startup_delta,
            after_restore=after_bundle,
            research_files_verified=len(protected),
            verified_at=datetime.now(zone).isoformat(),
        )
    write_json(out / "verification.json", result)
    print(relative(out / "verification.json"), flush=True)


if __name__ == "__main__":
    main()
