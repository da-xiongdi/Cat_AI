"""Rehearse WB-13 closeout and optionally apply it to the configured local workbench."""

import argparse
import hashlib
import io
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from contextlib import closing
from datetime import datetime
from importlib.metadata import distributions
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from zipfile import ZIP_DEFLATED, ZipFile
from zoneinfo import ZoneInfo

from catalyst_ai.storage.workbench import SCHEMA_VERSION, atomic_operations
from catalyst_ai.web.config import load
from catalyst_ai.workbench import (
    backup,
    category_context,
    deliveries,
    index,
    plans,
    queries,
    research_nodes,
    service,
)
from catalyst_ai.workbench.adapters import safe_path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path("configs/workbench.yaml")
PLAN = "docs/workbench/wb13_implementation_plan.md"
PARENT = "WB-13"
CHILDREN = tuple(f"WB-13-{n:02}" for n in range(1, 9))
CLOSEOUT = CHILDREN[-1]
PLAN_ID = "WB-13-execution-plan"
TASKS = (
    ("基线盘点与数据契约", "固定管理库基线和数据契约", (), "wb13_01_baseline_contract.md"),
    ("增量迁移与任务分类", "核对可重放迁移和旧任务兼容", (1,), "wb13_02_report.md"),
    ("历史建设交付承接", "核对历史交付范围、剩余项及版本", (2,), "wb13_03_report.md"),
    ("科研节点与任务关联", "核对节点层级、关联约束与去重", (2,), "wb13_04_report.md"),
    ("执行计划与文档引用", "核对主计划、章节和版本历史", (2,), "wb13_05_acceptance.md"),
    ("分类焦点与近期安排", "核对分类隔离、旧焦点及近期顺序", (2,), "wb13_06_acceptance.md"),
    ("共用查询与兼容接入", "核对分类查询、Web 和 CLI 兼容", (3, 4, 5, 6), "wb13_07_acceptance.md"),
    ("专项验收与部署收口", "核对正式部署、恢复和既有数据保护", (7,), None),
)


def require(condition, detail):
    if not condition:
        raise RuntimeError(detail)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def write_json(path, payload):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def relative(path):
    return path.relative_to(ROOT).as_posix()


def observation(db):
    schema = db.execute("PRAGMA user_version").fetchone()[0]
    integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
    require(schema == SCHEMA_VERSION and integrity == "ok", (schema, integrity))
    require(not db.execute("PRAGMA foreign_key_check").fetchall(), "foreign key check failed")
    return {
        name: sorted((dict(row) for row in db.execute(f'SELECT * FROM "{name}"')), key=repr)
        for (name,) in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        )
    }


def snapshot(path):
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        return observation(db)


def verify_preserved(before, after, legacy_expected):
    updates = {
        "workbench_delivery": {"source_sha256", "revision"},
        "research_node": {"source_sha256", "revision"},
        "project": {"focus_task_id"},
        "published_index": {"scan_id"},
    }
    for table, rows in before.items():
        ignore = updates.get(table, set())

        def key(row, ignore=ignore):
            return tuple((name, value) for name, value in row.items() if name not in ignore)

        original = Counter(map(key, rows))
        current = Counter(map(key, after[table]))
        require(
            original <= current, f"existing rows changed in {table}: {list(original - current)[:2]}"
        )
    require(
        [row["focus_task_id"] for row in after["project"]] == [legacy_expected],
        "unexpected legacy focus",
    )
    for table in (
        "task_node_link",
        "model_run",
        "model_run_revision",
        "research_record",
        "prediction_job",
        "prediction_event",
    ):
        require(before[table] == after[table], f"unexpected writes to {table}")


def source_refs(rows):
    return {
        r["source_path"] for table in ("workbench_delivery", "research_node") for r in rows[table]
    } | {r["path"] for r in rows["task_plan_reference"]}


def section(path, raw, heading):
    lines = raw.decode("utf-8-sig").splitlines()
    found = []
    for i, line in enumerate(lines):
        match = re.fullmatch(r"(#{1,6})\s+" + re.escape(heading) + r"\s*", line)
        if match:
            found.append((i, len(match[1])))
    require(len(found) == 1, f"{path}: expected one section {heading!r}")
    start, level = found[0]
    end = next(
        (i for i in range(start + 1, len(lines)) if re.match(rf"^#{{1,{level}}}\s", lines[i])),
        len(lines),
    )
    return "\n".join(lines[start:end]).strip()


def review_sources(path, project, plan_bytes, out):
    earlier = {
        "docs/s2_implementation_plan.md": "artifacts/wb13-02-evidence-v2/referenced-files.zip",
        "docs/architecture/system_design.md": "artifacts/wb13-08-evidence/references.zip",
        "docs/architecture/project_workbench_plan.md": "artifacts/wb13-08-evidence/references.zip",
    }
    old_files = {}
    for source, archive in earlier.items():
        with ZipFile(ROOT / archive) as saved:
            old_files[source] = saved.read(source)
    with ZipFile(out / "historical-sources.zip", "x", ZIP_DEFLATED) as archive:
        for name, raw in old_files.items():
            archive.writestr(name, raw)
    current = queries.query(path, project)
    preview = {
        item["original_wb_id"]: item
        for item in deliveries.preview_historical_deliveries(path, project)
    }
    history = []
    nodes = []
    for kind, rows, target in (
        ("delivery", current["historical_deliveries"], history),
        ("node", current["research_nodes"]["nodes"], nodes),
    ):
        for row in rows:
            source = row["source_path"]
            raw = safe_path(ROOT, source).read_bytes()
            current_hash = sha(raw)
            if row["source_status"] == "valid":
                continue
            old = old_files.get(source)
            heading = row["source_section"]
            require(
                old is not None and sha(old) == row["source_sha256"],
                f"old source missing: {row['id']}",
            )
            require(
                row["source_status"] == "changed"
                and section(source, old, heading) == section(source, raw, heading),
                f"source section changed: {row['id']}",
            )
            if kind == "delivery":
                expected = preview[row["original_wb_id"]]
                require(
                    all(row[k] == expected[k] for k in ("delivered_scope", "remaining_scope")),
                    f"delivery scope changed: {row['id']}",
                )
            target.append(
                {
                    **row,
                    "previous_source_sha256": row["source_sha256"],
                    "source_sha256": current_hash,
                }
            )
    for heading in headings().values():
        section(PLAN, plan_bytes, heading)
    return history, nodes


def headings():
    return {
        PARENT: "5. 任务登记与交付约定",
        **{
            task: f"{task}：{definition[0]}"
            for task, definition in zip(CHILDREN, TASKS, strict=True)
        },
    }


def make_bundle(path, root, out, label):
    rows = snapshot(path)
    content = backup.create_bundle(path, root)
    verified = backup.preview_bundle(content)
    manifest = verified["manifest"]
    require(not manifest["missing"], f"backup files missing: {manifest['missing']}")
    result = io.BytesIO()
    sources = {}
    with ZipFile(io.BytesIO(content)) as original, ZipFile(result, "w", ZIP_DEFLATED) as amended:
        for name in manifest["files"]:
            amended.writestr(name, original.read(name))
        for name in sorted(source_refs(rows)):
            raw = safe_path(root, name).read_bytes()
            alias = "workspace/" + name
            sources[name] = sha(raw)
            if alias in manifest["files"]:
                require(
                    manifest["files"][alias] == sources[name], f"source changed in backup: {name}"
                )
            else:
                amended.writestr(alias, raw)
                manifest["files"][alias] = sources[name]
        amended.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
    content = result.getvalue()
    bundle_path = out / f"{label}-bundle.zip"
    bundle_path.write_bytes(content)
    digest = sha(content)
    restored = out / f"{label}-restored"
    try:
        backup.restore_bundle(content, restored, digest)
    except PermissionError:
        # Windows scanners can briefly hold the staging directory open.
        time.sleep(1)
        backup.restore_bundle(content, restored, digest)
    restored_db = restored / "workbench.sqlite"
    restored_rows = snapshot(restored_db)
    expected_root = [
        {"project_id": r["project_id"], "root": str(restored / "workspace")}
        for r in rows["index_workspace"]
    ]
    require(restored_rows["index_workspace"] == expected_root, "restored workspace not relocated")
    require(
        all(rows[t] == restored_rows[t] for t in rows if t != "index_workspace"),
        "restore changed business rows",
    )
    for name, digest_value in sources.items():
        require(
            sha((restored / "workspace" / name).read_bytes()) == digest_value,
            f"restored source differs: {name}",
        )
    return {
        "path": relative(bundle_path),
        "sha256": digest,
        "missing": manifest["missing"],
        "files": len(manifest["files"]) - 1,
        "sources": sources,
        "table_counts": {table: len(values) for table, values in rows.items()},
        "rows_equal_except_relocated_workspace": True,
        "integrity": "ok",
        "foreign_key_errors": 0,
    }, restored_db


class Deployment:
    def __init__(self, project, out, initial, history, nodes):
        self.project, self.out, self.initial = project, out, initial
        self.history, self.nodes = history, nodes
        self.plan_hash = sha((ROOT / PLAN).read_bytes())
        self.proofs = {
            child: (f"{child}-evidence", "docs/workbench/" + definition[3])
            for child, definition in zip(CHILDREN[:-1], TASKS[:-1], strict=True)
        }
        self.proofs[CLOSEOUT] = (
            "WB-13-08-deployment-evidence",
            relative(out / "deployment-checks.json"),
        )

    def auth(self, key):
        return {"actor": "Codex", "request_id": f"{self.out.name}:{key}"}

    def start(self, db, task):
        rev = service.get_task(db, task)["revision"]
        rev = service.transition(db, task, rev, "ready", **self.auth(f"{task}:ready"))["revision"]
        return service.transition(db, task, rev, "in_progress", **self.auth(f"{task}:start"))

    def accept(self, db, task, criteria):
        results = []
        for criterion, source_task in criteria:
            ident, source = self.proofs[source_task]
            results.append(
                dict(
                    criterion_id=criterion,
                    passed=True,
                    evidence_id=ident,
                    evidence_version=sha((ROOT / source).read_bytes()),
                    explanation=f"已核对 {source_task} 对应的交付及固定证据。",
                )
            )
        current = service.get_task(db, task)
        submission = service.submit_review(
            db,
            task,
            current["revision"],
            results,
            "交付物与验收判据核对完成。",
            **self.auth(f"{task}:submit"),
        )
        service.accept_review(
            db,
            task,
            submission["revision"],
            "固定证据可用，必验项通过。",
            **self.auth(f"{task}:accept"),
        )

    def register(self, db, expected_sources):
        project = self.project
        with atomic_operations(db) as conn:
            require(observation(conn) == self.initial, "activity database changed since snapshot")
            require(
                file_hashes(expected_sources) == expected_sources,
                "deployment source version changed",
            )
            for row in self.history:
                deliveries.upsert_workbench_delivery(
                    db,
                    project,
                    row,
                    row["revision"],
                    "对照固定来源，交付范围与剩余范围一致。",
                    **self.auth(f"delivery:{row['id']}"),
                )
            for row in self.nodes:
                research_nodes.save_research_node(
                    db,
                    project,
                    row["id"],
                    row,
                    row["revision"],
                    "对照固定来源，节点章节内容一致。",
                    **self.auth(f"node:{row['id']}"),
                )
            index.register(db, project, PLAN_ID, "document", PLAN, **self.auth("plan:artifact"))
            for child, (ident, source) in self.proofs.items():
                if child != CLOSEOUT:
                    index.register(db, project, ident, "document", source, **self.auth(ident))
            index.scan(
                db,
                project,
                document_ids=[PLAN_ID, *(self.proofs[task][0] for task in CHILDREN[:-1])],
            )
            require(
                file_hashes(expected_sources) == expected_sources,
                "deployment sources changed during scan",
            )
            plans.save_document_purpose(
                db,
                project,
                "WB-13-execution-purpose",
                {"document_id": PLAN_ID, "purpose": "execution_plan", "category": "workbench"},
                0,
                "登记 WB-13 工作台执行方案。",
                **self.auth("plan:purpose"),
            )
            for task, heading in headings().items():
                if task == PARENT:
                    title, goal, deps = "管理分类与关联基础", "汇总 WB-13 八项交付和正式验收", ()
                    criteria = [
                        {"id": child, "description": f"{child} {definition[1]}通过并可追溯。"}
                        for child, definition in zip(CHILDREN, TASKS, strict=True)
                    ]
                else:
                    title, goal, deps, _ = TASKS[CHILDREN.index(task)]
                    criteria = [{"id": "delivery", "description": goal + "，固定证据可追溯。"}]
                created = service.create_task(
                    db,
                    dict(
                        id=task,
                        project_id=project,
                        title=title,
                        goal=goal,
                        deliverables=[f"{PLAN} · {heading}", "固定交付及验收证据"],
                        criteria=criteria,
                        category="workbench",
                        priority="urgent",
                        owner="Codex",
                    ),
                    **self.auth(f"{task}:create"),
                )
                rev = created["revision"]
                for dep in deps:
                    prerequisite = CHILDREN[dep - 1]
                    rev = service.add_dependency(
                        db,
                        task,
                        prerequisite,
                        rev,
                        **self.auth(f"{task}:dep:{prerequisite}"),
                    )["revision"]
                ref = f"{task}-primary-plan"
                saved = plans.save_task_plan_reference(
                    db,
                    project,
                    ref,
                    dict(
                        task_id=task,
                        document_id=PLAN_ID,
                        path=PLAN,
                        section_locator=heading,
                        purpose="execution_plan",
                        is_primary=1,
                    ),
                    0,
                    "登记实施章节及 WB-13 分组归属。",
                    **self.auth(f"{task}:reference"),
                )
                plans.verify_task_plan_reference(
                    db,
                    project,
                    ref,
                    saved["revision"],
                    self.plan_hash,
                    **self.auth(f"{task}:verify"),
                )
            for task in CHILDREN[:-1]:
                self.start(db, task)
                self.accept(db, task, [("delivery", task)])
            self.start(db, CLOSEOUT)
            self.start(db, PARENT)
            category_context.set_category_focus(
                db,
                project,
                "workbench",
                CLOSEOUT,
                0,
                "执行正式部署验收。",
                **self.auth("focus:set"),
            )
            category_context.save_recent_task(
                db,
                project,
                "workbench",
                CLOSEOUT,
                0,
                1,
                0,
                "安排正式部署核对。",
                **self.auth("recent:set"),
            )
            verify_preserved(self.initial, observation(conn), CLOSEOUT)

    def finish(self, db, deployed, expected_sources):
        with atomic_operations(db) as conn:
            require(observation(conn) == deployed, "activity database changed before acceptance")
            require(
                file_hashes(expected_sources) == expected_sources,
                "acceptance source version changed",
            )
            ident, source = self.proofs[CLOSEOUT]
            index.register(db, self.project, ident, "attachment", source, **self.auth(ident))
            index.scan(db, self.project, document_ids=[ident])
            require(
                file_hashes(expected_sources) == expected_sources,
                "sources changed during final indexing",
            )
            self.accept(db, CLOSEOUT, [("delivery", CLOSEOUT)])
            for task in CHILDREN:
                child = service.get_task(db, task)
                require(
                    child["status"] == "done" and not child["evidence_needs_review"],
                    f"child acceptance unavailable: {task}",
                )
            self.accept(db, PARENT, [(task, task) for task in CHILDREN])
            category_context.save_recent_task(
                db,
                self.project,
                "workbench",
                CLOSEOUT,
                0,
                0,
                1,
                "验收通过，近期安排归档。",
                **self.auth("recent:archive"),
            )
            category_context.set_category_focus(
                db,
                self.project,
                "workbench",
                None,
                1,
                "验收通过，清除已完成焦点。",
                **self.auth("focus:clear"),
            )
            verify_preserved(self.initial, observation(conn), None)

    def verify(self, db, closed):
        result = queries.query(db, self.project)
        selected = {r["id"]: r for r in result["tasks"] if r["category"] == "workbench"}
        require(set(selected) == set(headings()), "workbench task scope differs")
        desk = result["contexts"]["workbench"]
        research = result["contexts"]["research"]
        require(not research["context"], "research context changed")
        require(
            desk["context"]["focus_task_id"] == (None if closed else CLOSEOUT),
            "workbench focus differs",
        )
        require(
            len(desk["recent"]) == 1 and desk["recent"][0]["active"] == int(not closed),
            "recent arrangement differs",
        )
        require(
            len(result["historical_deliveries"]) == 12
            and all(r["source_status"] == "valid" for r in result["historical_deliveries"]),
            "historical source invalid",
        )
        nodes = result["research_nodes"]
        require(
            len(nodes["nodes"]) == 14
            and len(nodes["links"]) == 8
            and all(r["source_status"] == "valid" for r in nodes["nodes"]),
            "research source invalid",
        )
        records = {}
        for task in selected:
            reference = result["primary_plans"][task]
            require(
                reference["status"] == "valid" and reference["current_sha256"] == self.plan_hash,
                f"plan reference not verified: {task}",
            )
            record = service.get_task(db, task)
            status = "in_progress" if not closed and task in (PARENT, CLOSEOUT) else "done"
            require(
                record["status"] == status and not record["evidence_needs_review"],
                f"task acceptance differs: {task}",
            )
            records[task] = {
                k: record[k] for k in ("status", "revision", "criteria_version", "reviews")
            }
        return {"parent": records.pop(PARENT), "children": records, "plan_sha256": self.plan_hash}


def file_hashes(paths):
    return {name: sha(safe_path(ROOT, name).read_bytes()) for name in sorted(paths)}


def files_under(*directories):
    return {
        relative(p)
        for directory in directories
        for p in (ROOT / directory).rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }


def run_command(out, name, args):
    result = subprocess.run(
        args,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )
    (out / name).write_bytes(result.stdout)
    require(result.returncode == 0, f"{name} returned {result.returncode}")
    return result.stdout


def runtime_smoke(out, settings, config_path, suffix, closed):
    cli = [sys.executable, "-m", "catalyst_ai.cli", "workbench"]
    config = ["--config", str(config_path)]
    selected = json.loads(
        run_command(out, f"cli-{suffix}.json", [*cli, "query", *config, "--category", "workbench"])
    )
    base = f"http://127.0.0.1:{settings.port}"
    with (out / f"serve-{suffix}.log").open("wb") as log:
        proc = subprocess.Popen(
            [*cli, "serve", *config],
            cwd=ROOT,
            stdout=log,
            stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            endpoint = "/api/workbench/v1/query?category=workbench"
            for _ in range(60):
                require(proc.poll() is None, "configured workbench server did not start")
                try:
                    with urlopen(base + endpoint, timeout=2) as response:
                        api = json.load(response)
                        break
                except URLError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("configured workbench did not respond")
            status = "done" if closed else "in_progress"
            require(
                {t["id"]: t["status"] for t in api["tasks"]}[PARENT] == status,
                "runtime parent status differs",
            )
            for key in (
                "scope",
                "tasks",
                "counts",
                "primary_plans",
                "contexts",
                "historical_deliveries",
            ):
                require(selected[key] == api[key], f"CLI and HTTP differ: {key}")
            pages = [
                "/",
                "/tasks",
                *(f"/tasks/{task}" for task in headings()),
                "/tasks/S1A-01",
                "/artifacts",
                "/documents",
                "/decisions",
                "/api/workbench/v1/prediction-jobs",
                "/api/workbench/v1/exports/progress",
            ]
            statuses = {endpoint: 200}
            for route in pages:
                with urlopen(base + route, timeout=5) as response:
                    statuses[route] = response.status
                    require(response.status == 200, f"route failed: {route}")
                    if route.startswith("/tasks/WB-13"):
                        require(
                            route.split("/")[-1].encode() in response.read(),
                            f"task missing: {route}",
                        )
            require(proc.poll() is None, "workbench runtime exited during smoke test")
            return statuses
        finally:
            if proc.poll() is None:
                proc.terminate()
            proc.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="apply after verified rehearsal")
    args = parser.parse_args()
    stamp = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d-%H%M%S-%f")
    out = ROOT / "artifacts" / f"wb13-closeout-{stamp}"
    out.mkdir()
    print(relative(out), flush=True)
    settings, root, live = load(ROOT / CONFIG)
    require(root == ROOT and live == ROOT / "data/workbench.sqlite", "unexpected deployment target")
    before = out / "before.sqlite"
    backup.backup_database(live, before)
    initial = snapshot(before)
    require({r["id"] for r in initial["task"]}.isdisjoint(headings()), "WB-13 task ID already used")
    require(all(r["category"] == "research" for r in initial["task"]), "unexpected task categories")
    require(
        not initial["category_context"]
        and all(r["focus_task_id"] is None for r in initial["project"]),
        "existing category or legacy focus requires review",
    )
    history, nodes = review_sources(before, settings.project_id, (root / PLAN).read_bytes(), out)
    deployment = Deployment(settings.project_id, out, initial, history, nodes)
    write_json(
        out / "preview.json",
        {
            "schema": SCHEMA_VERSION,
            "tasks": initial["task"],
            "parent": PARENT,
            "children": CHILDREN,
            "plan_sections": headings(),
            "historical_reverification": history,
            "node_reverification": nodes,
            "preexisting_evidence_flags": [
                r for r in initial["evidence"] if r["status"] != "available"
            ],
        },
    )
    tests = sorted(
        p
        for p in files_under("tests")
        if re.search(r"test_(workbench|wb13)", p) and p.endswith(".py")
    )
    scoped = [
        *tests,
        relative(Path(__file__).resolve()),
        "src/catalyst_ai/storage/workbench.py",
        "src/catalyst_ai/workbench",
    ]
    ruff = str(Path(sys.executable).with_name("ruff.exe" if os.name == "nt" else "ruff"))
    frozen = file_hashes(
        files_under("src")
        | set(tests)
        | {
            CONFIG.as_posix(),
            "pyproject.toml",
            "uv.lock",
            relative(Path(__file__).resolve()),
        }
    )
    with ZipFile(out / "release-source.zip", "x", ZIP_DEFLATED) as archive:
        for name, digest in frozen.items():
            raw = (root / name).read_bytes()
            require(sha(raw) == digest, f"release file changed: {name}")
            archive.writestr(name, raw)
    result = run_command(out, "pytest.txt", [sys.executable, "-m", "pytest", "-q", *tests])
    run_command(out, "ruff.txt", [ruff, "check", *scoped])
    run_command(out, "ruff-format.txt", [ruff, "format", "--check", *scoped])
    write_json(
        out / "release.json",
        {
            "head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip(),
            "schema": SCHEMA_VERSION,
            "python": sys.version,
            "source_sha256": frozen,
            "archive_sha256": sha((out / "release-source.zip").read_bytes()),
            "installed": dict(sorted((d.metadata["Name"], d.version) for d in distributions())),
            "pytest": result.decode("utf-8").splitlines()[-1],
        },
    )
    v7 = (root / "artifacts/wb13-08-evidence/v7-bundle.zip").read_bytes()
    v7_report = backup.restore_bundle(v7, out / "v7-restored", sha(v7))
    v7_rows = snapshot(out / "v7-restored/workbench.sqlite")
    with ZipFile(io.BytesIO(v7)) as archive:
        (out / "v7-source.sqlite").write_bytes(archive.read("workbench.sqlite"))
    with closing(sqlite3.connect(out / "v7-source.sqlite")) as old:
        require(
            old.execute("PRAGMA user_version").fetchone()[0] == 7, "legacy package is not schema 7"
        )
        legacy_tables = [
            t
            for (t,) in old.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in legacy_tables:
            cursor = old.execute(f'SELECT * FROM "{table}"')
            keys = [
                col[0]
                for col in cursor.description
                if not (table == "index_workspace" and col[0] == "root")
            ]
            prior = Counter(
                tuple(r) for r in old.execute(f'SELECT {",".join(keys)} FROM "{table}"')
            )
            require(
                prior == Counter(tuple(r[k] for k in keys) for r in v7_rows[table]),
                f"legacy restore changed {table}",
            )
    pre_restore, _ = make_bundle(before, root, out, "before")
    protected_paths = files_under(
        "data/raw",
        "data/staged",
        "data/curated",
        "data/snapshots",
        "artifacts/models",
        "artifacts/runs",
    ) | {
        "data/catalog.sqlite",
        *(
            r["path"]
            for r in initial["artifact_location"]
            if any(
                a["id"] == r["artifact_id"] and a["kind"] == "features" for a in initial["artifact"]
            )
        ),
    }
    protected = file_hashes(protected_paths)
    expected = file_hashes(
        source_refs(initial)
        | {PLAN}
        | {path for task, (_, path) in deployment.proofs.items() if task != CLOSEOUT}
    )
    rehearsal = out / "rehearsal.sqlite"
    backup.backup_database(before, rehearsal)
    deployment.register(rehearsal, expected)
    rehearsal_open = deployment.verify(rehearsal, closed=False)
    rehearsal_config = out / "rehearsal-config.json"
    with socket.socket() as port_probe:
        port_probe.bind(("127.0.0.1", 0))
        rehearsal_port = port_probe.getsockname()[1]
    write_json(
        rehearsal_config,
        {
            **settings.model_dump(),
            "workspace": str(root),
            "database": relative(rehearsal),
            "port": rehearsal_port,
        },
    )
    rehearsal_settings, _, _ = load(rehearsal_config)
    rehearsal_http = runtime_smoke(out, rehearsal_settings, rehearsal_config, "rehearsal", False)
    write_json(
        out / "deployment-checks.json",
        {
            "rehearsal": rehearsal_open,
            "formal_mode": False,
            "before_restore": pre_restore,
            "http": rehearsal_http,
        },
    )
    deployment.finish(
        rehearsal,
        snapshot(rehearsal),
        {**expected, **file_hashes({deployment.proofs[CLOSEOUT][1]})},
    )
    rehearsal_final = deployment.verify(rehearsal, closed=True)
    rehearsal_restore, rehearsal_db = make_bundle(rehearsal, root, out, "rehearsal")
    require(
        deployment.verify(rehearsal_db, closed=True) == rehearsal_final, "rehearsal restore differs"
    )
    checks = {
        "predeployment_backup_and_restore": pre_restore,
        "rehearsal_restore": rehearsal_restore,
        "rehearsal_acceptance": rehearsal_final,
        "legacy_restore": {
            "schema_before": 7,
            "schema_after": SCHEMA_VERSION,
            "tables_equal": len(legacy_tables),
            "package_sha256": v7_report["sha256"],
        },
        "protected_file_sha256": protected,
        "release_sha256": sha((out / "release.json").read_bytes()),
    }
    write_json(out / "rehearsal-checks.json", checks)
    if not args.apply:
        require(snapshot(live) == initial, "live database changed during rehearsal")
        return
    require(file_hashes(frozen) == frozen, "frozen release changed")
    require(file_hashes(protected) == protected, "protected files changed during rehearsal")
    with socket.socket() as port_probe:
        port_probe.bind(("127.0.0.1", settings.port))
    deployment.register(live, expected)
    formal_open = deployment.verify(live, closed=False)
    http_open = runtime_smoke(out, settings, CONFIG, "deployed", False)
    deployed = out / "deployed.sqlite"
    backup.backup_database(live, deployed)
    deployed_rows = snapshot(deployed)
    verify_preserved(initial, deployed_rows, CLOSEOUT)
    require(file_hashes(protected) == protected, "protected files changed before acceptance")
    evidence_path = out / "deployment-checks.json"
    evidence_path.rename(out / "rehearsal-deployment-checks.json")
    write_json(
        evidence_path,
        {
            **checks,
            "formal_mode": True,
            "formal_deployment": formal_open,
            "http": http_open,
            "deployed_db_sha256": sha(deployed.read_bytes()),
            "protected_unchanged": True,
        },
    )
    deployment.finish(
        live, deployed_rows, {**expected, **file_hashes({deployment.proofs[CLOSEOUT][1]})}
    )
    formal_final = deployment.verify(live, closed=True)
    http_final = runtime_smoke(out, settings, CONFIG, "after", True)
    final = out / "after.sqlite"
    backup.backup_database(live, final)
    final_rows = snapshot(final)
    verify_preserved(initial, final_rows, None)
    actual_restore, restored = make_bundle(final, root, out, "after")
    require(deployment.verify(restored, closed=True) == formal_final, "formal restore differs")
    require(file_hashes(protected) == protected, "protected research files changed")
    require(file_hashes(frozen) == frozen, "deployment code or configuration changed")
    write_json(
        out / "verification.json",
        {
            "schema": SCHEMA_VERSION,
            "formal_acceptance": formal_final,
            "http": http_final,
            "formal_restore": actual_restore,
            "protected_unchanged": True,
            "prior_research_rows_preserved": True,
            "release_and_config_unchanged": True,
            "evidence_sha256": sha(evidence_path.read_bytes()),
            "before_db_sha256": sha(before.read_bytes()),
            "after_db_sha256": sha(final.read_bytes()),
        },
    )


if __name__ == "__main__":
    main()
