"""Rehearse and record the formal S5-05 M3 acceptance in the workbench."""

import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

from fastapi.testclient import TestClient
from s5_05_m3_audit import REPORT, ROOT, SEEDS, read, sha

from catalyst_ai.storage.workbench import atomic_operations, transaction
from catalyst_ai.web.app import create_app
from catalyst_ai.workbench import backup, index, model_runs, plans, service

DB = ROOT / "data/workbench.sqlite"
PROJECT = "cat-ai"
TASK = "S5-05"
SUMMARY = "S5-closeout-20261125-v1"
CALCULATIONS = "S5-05-M3-recalculation-v1"
AUDIT_SCRIPT = "S5-05-M3-audit-script-v1"
SUMMARY_REF = "S5-05-M3-closeout-reference-v1"
ADDITIONS = {
    SUMMARY: ROOT / "docs/s5_closeout_20261125.md",
    CALCULATIONS: REPORT / "m3-review-recalculation-v1.json",
    AUDIT_SCRIPT: ROOT / "scripts/s5_05_m3_audit.py",
}
REVIEW_FILES = {
    "S5-05-M3-evidence-v1": REPORT / "evidence-sha256.json",
    "S5-05-M3-report-v1": REPORT / "final_report.md",
    "S5-05-M3-model-card-v1": REPORT / "model_card.md",
}
BRANCH = "cat-ai:task-branch:S5"


def auth(action):
    return {"request_id": f"s5-05-m3-accept-20261125-v1:{action}", "actor": "Codex"}


def verify_replay():
    # Run the frozen verifiers without writing to their original result files.
    for script, output in (
        ("s5_05_diagnostics.py", "applicability-and-permutation.json"),
        ("s5_05_verify.py", "verification.json"),
        ("s5_05_fold_permutation.py", "fold-permutation.json"),
    ):
        path = ROOT / "scripts" / script
        original = path.read_text(encoding="utf-8-sig")
        write_call = f"(O/'{output}').write_text"
        assert original.count(write_call) == 1

        def compare_output(value, *, output=output, **kwargs):
            assert json.loads(value) == read(REPORT / output)

        source = compile(original.replace(write_call, "compare_output"), str(path), "exec")
        exec(source, {"__file__": str(path), "compare_output": compare_output})


def verify_registration(db):
    receipt = read(REPORT / "registration-receipt.json")
    preflight = read(REPORT / "preexperiment-verification.json")
    assert preflight["tests_exit"] == 0
    assert sha(REPORT / "preexperiment-tests.log") == preflight["tests_sha256"]
    for evidence in (
        read(REPORT / "preregistration-sha256.json"),
        preflight["prior_synthetic_and_partition_proofs"],
    ):
        for path, digest in evidence.items():
            assert sha(ROOT / path) == digest
    for seed in SEEDS:
        p = REPORT / f"run-{seed}"
        assert read(p / "lock.json")["input_hashes"] == preflight["preflight"][str(seed)]["hashes"]
    receipt_time = datetime.fromisoformat(receipt["utc"])
    assert datetime.fromisoformat(preflight["utc"]) < receipt_time
    latest_lock = max((REPORT / f"run-{s}/lock.json").stat().st_mtime for s in SEEDS)
    first_holdout = min((REPORT / f"run-{s}/holdout/all_arms.json").stat().st_mtime for s in SEEDS)
    assert receipt_time < datetime.fromtimestamp(latest_lock, UTC)
    assert latest_lock < first_holdout
    trace = read(REPORT / "training-trace.json")
    assert [(r["seed"], r["exit"]) for r in trace] == [(s, 0) for s in SEEDS]
    first_lock = (REPORT / "run-45/lock.json").stat().st_mtime
    assert receipt_time.timestamp() < first_lock - trace[0]["seconds"]
    assert all(0 < r["seconds"] < 1800 for r in trace)
    with transaction(db) as conn:
        for name, ref in receipt["files"].items():
            assert sha(ROOT / ref["path"]) == ref["sha256"]
            row = conn.execute(
                "SELECT status, observed_at FROM evidence WHERE id=? AND version=?",
                (name, ref["sha256"]),
            ).fetchone()
            assert row["status"] == "available"
            assert datetime.fromisoformat(row["observed_at"]) < receipt_time
        node = conn.execute(
            "SELECT source_path,source_sha256 FROM research_node WHERE id=?", (BRANCH,)
        ).fetchone()
        assert sha(ROOT / node["source_path"]) == node["source_sha256"]


def accept(db, versions):
    verify_registration(db)
    with atomic_operations(db):
        task = service.get_task(db, TASK)
        assert task["status"] == "in_review" and task["revision"] == 7
        submission = task["reviews"][-1]
        assert (submission["id"], submission["kind"]) == (94, "submission")
        assert {item["criterion_id"] for item in submission["results"] if item["passed"]} == {
            "evidence",
            "conclusions",
            "release",
        }
        assert {r["evidence_id"]: r["evidence_version"] for r in submission["results"]} == versions
        for name, path in ADDITIONS.items():
            index.register(
                db,
                PROJECT,
                name,
                "document" if path.suffix == ".md" else "attachment",
                path.relative_to(ROOT).as_posix(),
                **auth(f"register:{name}"),
            )
        index.scan(db, PROJECT, document_ids=list(ADDITIONS))
        ref = plans.save_task_plan_reference(
            db,
            PROJECT,
            SUMMARY_REF,
            {
                "task_id": TASK,
                "document_id": SUMMARY,
                "path": ADDITIONS[SUMMARY].relative_to(ROOT).as_posix(),
                "section_locator": "S5 科研收口与 M3 验收依据",
                "purpose": "acceptance",
            },
            0,
            "登记 M3 审核依据与 S5 阶段科研收口",
            **auth("reference"),
        )
        plans.verify_task_plan_reference(
            db,
            PROJECT,
            SUMMARY_REF,
            ref["revision"],
            sha(ADDITIONS[SUMMARY]),
            **auth("verify-reference"),
        )
        for seed in SEEDS:
            run_id = f"S5-05-E05-{seed}-v1"
            run = model_runs.get(db, PROJECT, run_id)
            content = run["history"][0]["content"]
            assert content["task_id"] == TASK and content["execution_status"] == "succeeded"
            assert content["research_status"] == "unreviewed"
            for ref in content["evidence"]:
                assert ref.pop("status") == "available"
            assert {
                "id": f"S5-05-M3-run-{seed}-lock-v1",
                "version": sha(REPORT / f"run-{seed}/lock.json"),
                "role": "model",
            } in content["evidence"]
            content["research_status"] = "limited"
            content["evidence"].extend(
                [
                    {"id": SUMMARY, "version": sha(ADDITIONS[SUMMARY]), "role": "report"},
                    {"id": CALCULATIONS, "version": sha(ADDITIONS[CALCULATIONS]), "role": "other"},
                ]
            )
            model_runs.save(db, PROJECT, run_id, content, run["revision"], **auth(f"run:{seed}"))
        result = service.accept_review(
            db,
            TASK,
            task["revision"],
            "S5-05 M3 正式通过。三项必需标准均满足。"
            "事前登记、等额预算、训练侧选模与留出顺序已核对。"
            "54 臂及 5,832 条预测重载一致，30 个历史运行 R² 复算一致，265 个固定文件散列匹配。"
            "三种子按训练侧平局规则保留 F_base/Extra Trees；留出属于已观察数据上的内部探索，"
            "特征贡献用于解释预测行为。S5 科研收口，暂不启动下一阶段。"
            "详见 S5-closeout-20261125-v1，"
            f"SHA-256 {sha(ADDITIONS[SUMMARY])}。",
            **auth("accept"),
        )
        assert result == {"id": TASK, "status": "done", "revision": 8}
    return result


def verify_workbench(db, workspace, versions):
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        run_count = conn.execute("SELECT count(*) FROM model_run WHERE id LIKE 'S5-05-E05-%'")
        assert run_count.fetchone()[0] == 3
    tasks = [service.get_task(db, f"S5-0{i}") for i in range(1, 6)]
    assert all(t["status"] == "done" and not t["evidence_needs_review"] for t in tasks)
    task = tasks[-1]
    assert [r["kind"] for r in task["reviews"]] == ["submission", "acceptance"]
    assert task["reviews"][-1]["results"] == task["reviews"][0]["results"]
    with TestClient(create_app(db, workspace, PROJECT), base_url="http://127.0.0.1") as client:
        page = client.get(f"/tasks/{TASK}")
        assert page.status_code == 200 and 'id="accept-review"' not in page.text
        references = ("S5-05-primary-plan", "S5-05-M3-report-reference-v1", SUMMARY_REF)
        assert all(ref in page.text for ref in references)
        for ref in references:
            page = client.get(f"/tasks/{TASK}/plans/{ref}")
            assert page.status_code == 200 and 'data-plan-status="valid"' in page.text
            assert 'id="plan-section"' in page.text and f'href="/tasks/{TASK}' in page.text
        for view in ("tree", "canvas"):
            page = client.get(f"/roadmap?node={quote(BRANCH)}&task={TASK}&view={view}")
            assert page.status_code == 200 and 'id="selected-task"' in page.text
        for ident, digest in versions.items():
            page = client.get(f"/artifacts/{ident}/download/{digest}")
            assert page.status_code == 200
            assert page.content == (REVIEW_FILES | ADDITIONS)[ident].read_bytes()
        for seed in SEEDS:
            page = client.get(f"/api/workbench/v1/model-runs/S5-05-E05-{seed}-v1")
            assert page.status_code == 200
            content = page.json()["history"][0]["content"]
            assert content["research_status"] == "limited"
            assert all(ref["status"] == "available" for ref in content["evidence"])
    return task["reviews"][-1]["id"]


def main():
    audit = subprocess.check_output([sys.executable, str(ADDITIONS[AUDIT_SCRIPT])], cwd=ROOT)
    assert json.loads(audit) == read(ADDITIONS[CALCULATIONS])
    verify_replay()
    versions = {ident: sha(path) for ident, path in REVIEW_FILES.items()}
    indexed_versions = versions | {ident: sha(path) for ident, path in ADDITIONS.items()}
    backups = ROOT / "backups/s5-05-m3-accept-20261125-v1"
    before = backups / "before.sqlite"
    rehearsal = backups / "rehearsal.sqlite"
    if not before.exists():
        backup.backup_database(DB, before)
    if not rehearsal.exists():
        backup.backup_database(before, rehearsal)
    if service.get_task(rehearsal, TASK)["status"] == "in_review":
        accept(rehearsal, versions)
    review = verify_workbench(rehearsal, ROOT, indexed_versions)
    with TemporaryDirectory() as folder:
        bundle = backup.create_bundle(rehearsal, ROOT)
        preview = backup.preview_bundle(bundle)
        destination = Path(folder) / "restore"
        backup.restore_bundle(bundle, destination, preview["sha256"])
        restored_review = verify_workbench(
            destination / "workbench.sqlite", destination / "workspace", indexed_versions
        )
        assert restored_review == review
    print(f"Rehearsal and restored bundle verified, acceptance #{review}", flush=True)
    result = accept(DB, versions)
    review = verify_workbench(DB, ROOT, indexed_versions)
    print(
        json.dumps({"formal": result, "review_id": review, "fixed_versions": indexed_versions}),
        flush=True,
    )


if __name__ == "__main__":
    main()
