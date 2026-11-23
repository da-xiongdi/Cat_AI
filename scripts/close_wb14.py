"""Rehearse WB-14 acceptance and apply it with --apply to the configured workbench."""

import argparse
import os
import socket
import subprocess
import sys
import time
from collections import Counter
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

from catalyst_ai.storage.workbench import SCHEMA_VERSION, atomic_operations
from catalyst_ai.web.config import load
from catalyst_ai.workbench import backup, index, plans, queries, roadmap, service

CONFIG = "configs/workbench.yaml"
PLAN = "docs/workbench/wb14_implementation_plan.md"
PLAN_ID = "WB-14-execution-plan"
PARENT = "WB-14"
CHILDREN = tuple(f"WB-14-{i:02}" for i in range(1, 7))
NAMES = (
    "基线与页面数据契约",
    "只读页面与树形列表",
    "路线画布与交互",
    "焦点与任务双向定位",
    "节点与关联维护",
    "专项验收与交付",
)
SECTION = "2. 子任务、实施顺序与交付物"
MATRIX = (
    "实际结构、空项目、多层分支",
    "状态、去重与证据失效",
    "路线画布、键盘和窄屏",
    "互定位与深链接",
    "组织操作与并发",
    "旧能力与科研数据隔离",
)
REGISTRATION_TABLES = {
    "activity",
    "artifact",
    "artifact_location",
    "artifact_revision",
    "criterion",
    "dependency",
    "document_purpose",
    "document_purpose_revision",
    "evidence",
    "index_observation",
    "index_scan",
    "published_index",
    "request_log",
    "review",
    "task",
    "task_plan_reference",
    "task_plan_reference_revision",
    "task_plan_verification",
}
ROUTE_TABLES = {
    "activity",
    "request_log",
    "research_node",
    "research_node_revision",
    "task_node_link",
    "task_node_link_revision",
}


def changes(before, after, permitted):
    delta = {}
    for table, rows in before.items():
        if rows == after[table]:
            continue
        require(table in permitted, f"unexpected changes to {table}")
        old, new = Counter(map(repr, rows)), Counter(map(repr, after[table]))
        delta[table] = {
            "prior_rows_changed": sum((old - new).values()),
            "new_rows": sum((new - old).values()),
        }
    return delta


def smoke(settings, config, out, label, include_wb14):
    log_path = out / f"serve-{label}.log"
    base = f"http://127.0.0.1:{settings.port}"
    with log_path.open("xb") as log:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "catalyst_ai.cli",
                "workbench",
                "serve",
                "--config",
                str(config),
            ],
            cwd=ROOT,
            stdout=log,
            stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            for _ in range(60):
                require(proc.poll() is None, f"configured service failed: {log_path}")
                try:
                    with urlopen(base + "/roadmap", timeout=3):
                        break
                except URLError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("configured workbench did not respond")
            routes = (
                "/",
                "/roadmap",
                "/roadmap?view=tree",
                "/tasks",
                "/tasks/S1A-01",
                "/tasks/WB-13",
                "/artifacts",
                "/documents",
                "/decisions",
                "/predictions",
                "/foundation",
                "/api/workbench/v1/prediction-jobs",
                "/api/workbench/v1/roadmap/nodes/cat-ai:stage:C/children",
                "/api/workbench/v1/query?category=workbench",
            )
            if include_wb14:
                routes += tuple(f"/tasks/{task}" for task in (PARENT, *CHILDREN))
            statuses = {}
            for route in routes:
                with urlopen(base + route, timeout=5) as response:
                    statuses[route] = response.status
                    require(response.status == 200, f"route failed: {route}")
                    if route.startswith("/tasks/WB-"):
                        require(route.rsplit("/", 1)[-1].encode() in response.read(), route)
            return statuses
        finally:
            if proc.poll() is None:
                proc.terminate()
            proc.wait(timeout=10)


class Closeout(Deployment):
    def __init__(self, project, out):
        self.project, self.out = project, out
        self.plan_hash = sha((ROOT / PLAN).read_bytes())
        self.proofs = {
            child: (f"{child}-evidence", relative(out / "acceptance-evidence.json"))
            for child in CHILDREN
        }

    def register_and_accept(self, db, initial, expected_files):
        with atomic_operations(db) as conn:
            require(observation(conn) == initial, "database changed since the deployment snapshot")
            require(
                file_hashes(expected_files) == expected_files, "release or source files changed"
            )
            index.register(db, self.project, PLAN_ID, "document", PLAN, **self.auth("plan"))
            for ident, path in self.proofs.values():
                index.register(db, self.project, ident, "attachment", path, **self.auth(ident))
            index.scan(
                db,
                self.project,
                document_ids=[PLAN_ID, *(ident for ident, _ in self.proofs.values())],
            )
            plans.save_document_purpose(
                db,
                self.project,
                "WB-14-execution-purpose",
                {"document_id": PLAN_ID, "purpose": "execution_plan", "category": "workbench"},
                0,
                "登记 WB-14 工作台执行方案。",
                **self.auth("plan:purpose"),
            )
            for i, task in enumerate((*CHILDREN, PARENT)):
                if task == PARENT:
                    title = "科研路线图"
                    criteria = dict(zip(CHILDREN, NAMES, strict=True))
                    dependencies = ()
                elif task == CHILDREN[-1]:
                    title = NAMES[i]
                    criteria = {f"matrix-{n}": label for n, label in enumerate(MATRIX, 1)}
                    dependencies = CHILDREN[:-1]
                else:
                    title = NAMES[i]
                    criteria = {"delivery": title}
                    dependencies = (CHILDREN[i - 1] if i else "WB-13",)
                created = service.create_task(
                    db,
                    {
                        "id": task,
                        "project_id": self.project,
                        "title": title,
                        "goal": f"完成 WB-14 {title}并保留可复核证据",
                        "deliverables": [f"{PLAN} · {SECTION}", "WB-14 验收证据"],
                        "criteria": [
                            {"id": key, "description": label} for key, label in criteria.items()
                        ],
                        "category": "workbench",
                        "owner": "Codex",
                    },
                    **self.auth(f"{task}:create"),
                )
                revision = created["revision"]
                for dep in dependencies:
                    revision = service.add_dependency(
                        db, task, dep, revision, **self.auth(f"{task}:dep:{dep}")
                    )["revision"]
                ref = f"{task}-primary-plan"
                saved = plans.save_task_plan_reference(
                    db,
                    self.project,
                    ref,
                    {
                        "task_id": task,
                        "document_id": PLAN_ID,
                        "path": PLAN,
                        "section_locator": SECTION,
                        "purpose": "execution_plan",
                        "is_primary": 1,
                    },
                    0,
                    f"登记 {task} 在 WB-14 实施方案中的交付范围。",
                    **self.auth(f"{task}:plan"),
                )
                plans.verify_task_plan_reference(
                    db,
                    self.project,
                    ref,
                    saved["revision"],
                    self.plan_hash,
                    **self.auth(f"{task}:verify"),
                )
                self.start(db, task)
                self.accept(db, task, [(key, key if task == PARENT else task) for key in criteria])
            require(
                file_hashes(expected_files) == expected_files, "sources changed during acceptance"
            )
            delta = changes(initial, observation(conn), REGISTRATION_TABLES)
            require(
                all(
                    row["prior_rows_changed"] == 0
                    for table, row in delta.items()
                    if table != "published_index"
                ),
                f"prior business rows changed: {delta}",
            )
        return delta

    def verify(self, db):
        query = queries.query(db, self.project, "workbench")
        records = {}
        for task in (PARENT, *CHILDREN):
            reference = query["primary_plans"][task]
            require(reference["status"] == "valid", f"{task}: primary plan invalid")
            record = service.get_task(db, task)
            require(record["status"] == "done" and not record["evidence_needs_review"], task)
            acceptance = next(r for r in record["reviews"] if r["kind"] == "acceptance")
            records[task] = {
                "status": record["status"],
                "revision": record["revision"],
                "acceptance_id": acceptance["id"],
                "accepted_at": acceptance["created_at"],
                "evidence_needs_review": record["evidence_needs_review"],
                "plan_sha256": reference["current_sha256"],
            }
        return records


def main():
    from verify_wb14_browser import run as verify_browser

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    tz = ZoneInfo("Asia/Shanghai")
    out = ROOT / "artifacts" / datetime.now(tz).strftime("wb14-closeout-%Y%m%d-%H%M%S-%f")
    out.mkdir()
    print(relative(out), flush=True)
    settings, root, live = load(ROOT / CONFIG)
    require(root == ROOT and live == ROOT / "data/workbench.sqlite", "unexpected workbench target")
    initial_db = out / "before.sqlite"
    backup.backup_database(live, initial_db)
    initial = snapshot(initial_db)
    registered = {r["id"]: r for r in initial["task"]}
    require(not set(registered).intersection((PARENT, *CHILDREN)), "WB-14 IDs already registered")
    require(registered.get("WB-13", {}).get("status") == "done", "WB-13 prerequisite not accepted")
    sources = file_hashes(source_refs(initial) | {PLAN})
    protected_files = files_under(
        "data/raw",
        "data/staged",
        "data/curated",
        "data/snapshots",
        "artifacts/models",
        "artifacts/runs",
        "artifacts/reports",
        "artifacts/workbench-predictions",
    ) | {"data/catalog.sqlite"}
    protected_files |= {
        r["path"]
        for r in initial["artifact_location"]
        if any(a["id"] == r["artifact_id"] and a["kind"] == "features" for a in initial["artifact"])
    }
    protected = file_hashes(protected_files)
    release = file_hashes(
        files_under("src", "tests")
        | {
            CONFIG,
            PLAN,
            "pyproject.toml",
            "uv.lock",
            "scripts/close_wb14.py",
            "scripts/close_wb13.py",
            "scripts/verify_wb14_browser.py",
        }
    )
    with ZipFile(out / "release-source.zip", "x", ZIP_DEFLATED) as archive:
        for name, digest in release.items():
            raw = (root / name).read_bytes()
            require(sha(raw) == digest, f"release changed: {name}")
            archive.writestr(name, raw)
    write_json(
        out / "release.json",
        {
            "git_head": run_command(out, "git-head.txt", ["git", "rev-parse", "HEAD"])
            .decode()
            .strip(),
            "config": CONFIG,
            "project": settings.project_id,
            "database": relative(live),
            "schema": SCHEMA_VERSION,
            "python": sys.version,
            "installed": dict(sorted((d.metadata["Name"], d.version) for d in distributions())),
            "source_sha256": release,
            "archive_sha256": sha((out / "release-source.zip").read_bytes()),
        },
    )
    run_command(out, "pytest.txt", [sys.executable, "-m", "pytest", "-q"])
    ruff = str(Path(sys.executable).with_name("ruff.exe" if os.name == "nt" else "ruff"))
    scoped = ["src", "tests", "scripts/close_wb14.py", "scripts/verify_wb14_browser.py"]
    run_command(out, "ruff.txt", [ruff, "check", *scoped])
    run_command(out, "ruff-format.txt", [ruff, "format", "--check", *scoped])
    baseline = roadmap.snapshot(initial_db, settings.project_id)
    require([s["stage"] for s in baseline["stages"]] == list("ABCDEF"), "unexpected stage order")
    require(all(s["registered"] for s in baseline["stages"]), "missing actual stage root")
    write_json(
        out / "baseline.json",
        {
            "source_sha256": sources,
            "stages": baseline["stages"],
            "nodes": baseline["nodes"],
            "links": baseline["links"],
            "summary": baseline["summary"],
            "pending_tasks": baseline["pending_task_ids"],
            "research_focus": baseline["focus"],
        },
    )
    before_bundle, before_restored = make_bundle(initial_db, root, out, "before")
    browser_db = out / "route-edits.sqlite"
    backup.backup_database(initial_db, browser_db)
    verify_browser(browser_db, root, settings.project_id, out, settings)
    route_delta = changes(initial, snapshot(browser_db), ROUTE_TABLES)
    route_bundle, _ = make_bundle(browser_db, root, out, "route-edits")
    require(file_hashes(protected) == protected, "research files changed during route rehearsal")
    write_json(
        out / "protection.json",
        {
            "file_sha256": protected,
            "route_rehearsal_table_delta": route_delta,
        },
    )
    original = snapshot(live)
    require(original == initial, "live database changed during verification")
    smoke_db = out / "service-rehearsal.sqlite"
    backup.backup_database(initial_db, smoke_db)
    smoke_config = out / "service-rehearsal.json"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        rehearsal_port = probe.getsockname()[1]
    write_json(
        smoke_config,
        {
            **settings.model_dump(),
            "workspace": str(root),
            "database": relative(smoke_db),
            "port": rehearsal_port,
        },
    )
    runtime_before = smoke(load(smoke_config)[0], smoke_config, out, "rehearsal", False)
    proof = out / "acceptance-evidence.json"
    write_json(
        proof,
        {
            "matrix": [
                {"check": label, "status": "passed", "files": files}
                for label, files in zip(
                    MATRIX,
                    (
                        ["baseline.json", "pytest.txt", "edge.json"],
                        ["baseline.json", "pytest.txt", "edge.json"],
                        ["edge.json", "edge-1366.png", "edge-1920.png", "edge-390.png"],
                        ["edge.json", "pytest.txt"],
                        ["edge.json", "pytest.txt", "protection.json"],
                        ["pytest.txt", "ruff.txt", "ruff-format.txt", "protection.json"],
                    ),
                    strict=True,
                )
            ],
            "release_manifest_sha256": sha((out / "release.json").read_bytes()),
            "management_backup_and_restore": before_bundle,
            "route_edit_backup_and_restore": route_bundle,
            "isolated_runtime_before_registration": runtime_before,
        },
    )
    expected = {**sources, **release, **protected, **file_hashes({relative(proof)})}
    closeout = Closeout(settings.project_id, out)
    rehearsal_db = out / "registration-rehearsal.sqlite"
    backup.backup_database(initial_db, rehearsal_db)
    rehearsal_delta = closeout.register_and_accept(rehearsal_db, initial, expected)
    rehearsal_records = closeout.verify(rehearsal_db)
    rehearsal_bundle, _ = make_bundle(rehearsal_db, root, out, "registration-rehearsal")
    print("隔离登记、验收和恢复通过", flush=True)
    final = {
        "rehearsal": rehearsal_records,
        "rehearsal_delta": rehearsal_delta,
        "rehearsal_restore": rehearsal_bundle,
        "formal": False,
    }
    if args.apply:
        print("通过工作台服务登记正式验收", flush=True)
        preexisting = {
            task: service.get_task(before_restored, task)["evidence_needs_review"]
            for task in registered
        }
        delta = closeout.register_and_accept(live, initial, expected)
        records = closeout.verify(live)
        require(
            all(
                service.get_task(live, task)["evidence_needs_review"] == flag
                for task, flag in preexisting.items()
            ),
            "existing acceptance evidence status changed",
        )
        accepted_rows = snapshot(live)
        runtime_after = smoke(settings, ROOT / CONFIG, out, "after", True)
        deployed = out / "after.sqlite"
        backup.backup_database(live, deployed)
        final_rows = snapshot(deployed)
        startup_delta = changes(accepted_rows, final_rows, {"request_log"})
        new_requests = [
            r for r in final_rows["request_log"] if r not in accepted_rows["request_log"]
        ]
        require(
            startup_delta == {"request_log": {"prior_rows_changed": 0, "new_rows": 1}}
            and new_requests[0]["request_id"].startswith("init-workspace-"),
            f"unexpected configured service startup delta: {startup_delta}",
        )
        bundle, restored = make_bundle(deployed, root, out, "after")
        require(closeout.verify(restored) == records, "restored acceptance differs")
        require(file_hashes(expected) == expected, "protected or release files changed")
        final.update(
            formal=True,
            records=records,
            deployment_delta=delta,
            runtime_after=runtime_after,
            service_startup_delta=startup_delta,
            after_restore=bundle,
            previous_task_evidence=preexisting,
            verified_at=datetime.now(tz).isoformat(timespec="seconds"),
        )
    write_json(out / "verification.json", final)
    print(relative(out / "verification.json"), flush=True)


if __name__ == "__main__":
    main()
