"""Preview or reconcile the reviewed S2 task plan using workbench services."""

import argparse
import hashlib
import json
import sqlite3
import uuid
from pathlib import Path

from catalyst_ai.workbench import backup, index, service


def load_manifest(root):
    path = root / "docs/workbench/s2_tasks.json"
    raw = path.read_bytes()
    manifest = json.loads(raw)
    if manifest["schema_version"] != 1 or manifest["project_id"] != "cat-ai":
        raise ValueError("unsupported deployment manifest")
    tasks = {}
    for entry in manifest["tasks"]:
        data = {k: v for k, v in entry.items() if k not in {"target_status", "dependencies"}}
        data["project_id"] = manifest["project_id"]
        parsed = service.TaskCreate.model_validate(data).model_dump()
        ident = parsed["id"]
        if ident in tasks or entry["target_status"] not in {"planned", "ready"}:
            raise ValueError("duplicate task or invalid target state")
        if len({c["id"] for c in parsed["criteria"]}) != len(parsed["criteria"]):
            raise ValueError("duplicate criterion")
        tasks[ident] = {
            "data": parsed,
            "dependencies": sorted(entry["dependencies"]),
            "target_status": entry["target_status"],
        }
    return tasks, {
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "sources": {
            p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in manifest["sources"]
        },
    }


def current_criteria(task):
    return [
        {"id": c["criterion_id"], "description": c["description"], "required": bool(c["required"])}
        for c in task["criteria"]
    ]


def preview(db, tasks):
    changes = []
    all_tasks = {t["id"] for t in service.list_tasks(db, "cat-ai")}
    graph = {}
    for ident in sorted(all_tasks | tasks.keys()):
        old = service.get_task(db, ident) if ident in all_tasks else None
        if ident not in tasks:
            graph[ident] = old["dependencies"]
            continue
        entry, data = tasks[ident], tasks[ident]["data"]
        graph[ident] = entry["dependencies"]
        if old and old["project_id"] != data["project_id"]:
            raise service.Conflict("task belongs to another project")
        delta = {}
        if old:
            for key, value in data.items():
                if key not in {"id", "project_id", "criteria"} and old[key] != value:
                    delta[key] = value
            if current_criteria(old) != data["criteria"]:
                delta["criteria"] = data["criteria"]
        dependencies_changed = old is None or sorted(old["dependencies"]) != graph[ident]
        state_changed = old is None or old["status"] != entry["target_status"]
        if not old or delta or dependencies_changed or state_changed:
            if old and (old["status"] != "planned" or old["reviews"]):
                raise service.Conflict(
                    f"task has started or has reviews; reconcile manually: {ident}"
                )
            changes.append(
                {
                    "id": ident,
                    "revision": old["revision"] if old else None,
                    "create": old is None,
                    "changes": delta,
                    "dependencies": graph[ident],
                    "target_status": entry["target_status"],
                }
            )

    def visit(ident, chain):
        if ident not in graph or ident in chain:
            raise ValueError("unknown or cyclic dependency: " + ident)
        for dep in graph[ident]:
            visit(dep, chain | {ident})

    for ident in tasks:
        visit(ident, set())
    return changes


def reconcile(db, tasks, expected, tag):
    if preview(db, tasks) != expected:
        raise service.Conflict("task state changed since preview")

    def request(action, ident):
        return {"request_id": f"s2-{tag}-{action}-{ident}", "actor": "Codex"}

    for change in expected:
        ident = change["id"]
        if change["create"]:
            service.create_task(db, tasks[ident]["data"], **request("create", ident))
        elif change["changes"]:
            service.update_task(
                db, ident, change["revision"], change["changes"], **request("update", ident)
            )
    for change in expected:
        ident = change["id"]
        old = service.get_task(db, ident)
        for dep in sorted(set(old["dependencies"]) - set(change["dependencies"])):
            service.remove_dependency(
                db,
                ident,
                dep,
                service.get_task(db, ident)["revision"],
                **request("remove-" + dep, ident),
            )
        for dep in sorted(set(change["dependencies"]) - set(old["dependencies"])):
            service.add_dependency(
                db,
                ident,
                dep,
                service.get_task(db, ident)["revision"],
                **request("add-" + dep, ident),
            )
    for change in expected:
        ident = change["id"]
        if change["target_status"] == "ready":
            service.transition(
                db,
                ident,
                service.get_task(db, ident)["revision"],
                "ready",
                **request("ready", ident),
            )
    assert preview(db, tasks) == [], "deployment did not converge"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="back up, rehearse, then apply the task plan"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    db = root / "data/workbench.sqlite"
    tasks, identity = load_manifest(root)
    changes = preview(db, tasks)
    if not args.apply or not changes:
        print(json.dumps({**identity, "apply": args.apply, "changes": changes}, ensure_ascii=False))
        return
    out = root / "artifacts/reports" / ("s2-task-deployment-20261117-" + uuid.uuid4().hex[:12])
    out.mkdir(parents=True)
    protected = [root / "data/catalog.sqlite"]
    protected += [
        p
        for folder in ("data/snapshots", "artifacts/models", "artifacts/reports/s1-b-20261113-v4")
        for p in (root / folder).rglob("*")
        if p.is_file()
    ]

    def hashes():
        return {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in protected
        }

    before = hashes()
    original = backup.backup_database(db, out / "before.sqlite")
    backup.backup_database(db, out / "rehearsal.sqlite")
    with sqlite3.connect(db) as conn:
        reviews_before = conn.execute("SELECT * FROM review ORDER BY id").fetchall()
    reconcile(out / "rehearsal.sqlite", tasks, changes, "rehearsal-" + out.name)
    reconcile(db, tasks, changes, out.name)
    assert hashes() == before, "research inputs changed"
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT * FROM review ORDER BY id").fetchall() == reviews_before
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    for artifact_id, kind, path in (
        ("S2-implementation-plan", "document", "docs/s2_implementation_plan.md"),
        ("S2-task-manifest", "attachment", "docs/workbench/s2_tasks.json"),
        ("feature-engineering-plan", "document", "docs/feature_engineering_plan_v0.1.md"),
    ):
        index.register(
            db, "cat-ai", artifact_id, kind, path, request_id=out.name + artifact_id, actor="Codex"
        )
    index.scan(db, "cat-ai")
    states = {}
    for ident, entry in tasks.items():
        t = service.get_task(db, ident)
        assert t["status"] == entry["target_status"] and not t["reviews"]
        states[ident] = {
            k: t[k] for k in ("title", "status", "revision", "criteria_version", "dependencies")
        }
    report = {
        **identity,
        "changes": changes,
        "tasks": states,
        "backup": original,
        "research_files_unchanged": before,
        "reviews_unchanged": True,
        "rehearsal_passed": True,
        "repeat_changes": preview(db, tasks),
    }
    (out / "verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    backup.backup_database(db, out / "after.sqlite")
    print(
        json.dumps(
            {"report": (out / "verification.json").relative_to(root).as_posix(), "tasks": states},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
