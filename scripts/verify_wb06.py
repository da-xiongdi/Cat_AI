"""Verify real R1 prediction, browser submission, killed-worker recovery and backup."""

import hashlib
import json
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright

from catalyst_ai.features.pipeline import project
from catalyst_ai.modeling.predictor import load_package, predict_batch
from catalyst_ai.storage.workbench import migrate
from catalyst_ai.web.app import create_app
from catalyst_ai.workbench import backup, index, predictions


def main():
    root = Path(__file__).resolve().parents[1]
    db = root / "data/workbench.sqlite"
    tag = uuid.uuid4().hex[:12]
    out = root / "artifacts/reports" / ("wb06-" + tag)
    out.mkdir(parents=True)
    files = [root / "data/catalog.sqlite"] + [
        p
        for directory in ("data/snapshots", "artifacts/models")
        for p in (root / directory).rglob("*")
        if p.is_file()
    ]

    def protected():
        return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}

    before = protected()
    backup.backup_database(db, out / "before.sqlite")
    migrate(db)
    index.scan(db, "cat-ai")
    artifact = index.get_artifact(db, "R1-model")
    location = artifact["locations"][0]
    package = load_package((root / location).parent)
    metadata = package[0]
    snapshot = json.loads(
        (root / "data/snapshots" / (metadata["snapshot_id"] + ".json")).read_text(encoding="utf-8")
    )
    record = next(
        r
        for r in snapshot["content"]["records"]
        if r["record_id"] == metadata["training_record_ids"][0]
    )
    row = project(record["payload"])
    item = {
        **row["conditions"],
        "components": [dict(role=r, species=s, mol_pct=a) for (r, s), a in row["amounts"].items()],
    }
    items = [item, {}]
    version = predictions.sha((root / location).read_bytes())
    job = predictions.enqueue(
        db, "cat-ai", "R1-model", version, items, request_id="wb06-" + tag, actor="Codex"
    )
    command = [sys.executable, "-m", "catalyst_ai.cli", "workbench", "worker", "--config"]
    subprocess.run(
        command + [str(root / "configs/workbench.yaml"), "--once"], check=True, timeout=90
    )
    actual = predictions.get(db, "cat-ai", job["id"])
    assert actual["status"] == "succeeded", actual["error"]
    expected = predict_batch(package, items)
    assert [
        {k: v for k, v in result.items() if k != "row"} for result in actual["result"]["rows"]
    ] == expected
    bundle = backup.create_bundle(db, root)
    preview = backup.preview_bundle(bundle)
    assert not preview["manifest"]["missing"]
    (out / "bundle.zip").write_bytes(bundle)
    backup.restore_bundle(bundle, out / "isolated", preview["sha256"])
    copy_db = out / "isolated/workbench.sqlite"
    copy_root = out / "isolated/workspace"
    assert predictions.get(copy_db, "cat-ai", job["id"])["result"] == actual["result"]
    config = out / "isolated/worker.yaml"
    # Config requires its management store inside workspace; use an isolated SQLite snapshot there.
    isolated_db = copy_root / "wb.sqlite"
    backup.backup_database(copy_db, isolated_db)
    config.write_text("workspace: workspace\ndatabase: wb.sqlite\nproject_id: cat-ai\n")
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(isolated_db, copy_root), host="127.0.0.1", port=18766, log_level="error"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    errors = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport=dict(width=1366, height=768))
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto("http://127.0.0.1:18766/predictions")
            form = page.locator('form[action="/actions/enqueue-prediction"]')
            form.locator('[name="model"]').select_option("R1-model|" + version)
            form.locator('[name="items"]').fill(json.dumps(items))
            form.locator('[name="actor"]').fill("Codex browser")
            form.locator("button").click()
            queued = next(
                j for j in predictions.list_jobs(isolated_db, "cat-ai") if j["status"] == "queued"
            )
            subprocess.run(command + [str(config), "--once"], check=True, timeout=90)
            assert predictions.get(isolated_db, "cat-ai", queued["id"])["status"] == "succeeded"
            page.reload()
            assert "invalid_input" in page.content()
            page.screenshot(path=str(out / "desktop.png"), full_page=True)
            page.set_viewport_size(dict(width=390, height=844))
            page.screenshot(path=str(out / "mobile.png"), full_page=True)
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    crash_job = predictions.enqueue(
        isolated_db,
        "cat-ai",
        "R1-model",
        version,
        [item] * 1000,
        request_id="crash-" + tag,
        actor="Codex",
    )
    process = subprocess.Popen(command + [str(config), "--once"])
    try:
        for _ in range(500):
            current = predictions.get(isolated_db, "cat-ai", crash_job["id"])
            if current["status"] == "running":
                break
            time.sleep(0.02)
        assert current["status"] == "running"
    finally:
        process.terminate()
        process.wait(timeout=10)
    # Shorten only the verification lease window after the real worker has been killed.
    assert crash_job["id"] in predictions.recover(isolated_db, "cat-ai", stale_seconds=0)
    retried = predictions.retry(
        isolated_db, "cat-ai", crash_job["id"], request_id="retry-" + tag, actor="Codex"
    )
    assert (
        predictions.get(isolated_db, "cat-ai", retried["id"])["payload"]["retry_of"]
        == crash_job["id"]
    )
    predictions.cancel(
        isolated_db, "cat-ai", retried["id"], 1, request_id="cancel-" + tag, actor="Codex"
    )
    assert not errors and before == protected()
    report = dict(
        job_id=job["id"],
        schema=7,
        python_equivalence=True,
        browser_errors=errors,
        row_statuses=[r["status"] for r in actual["result"]["rows"]],
        killed_worker_job=crash_job["id"],
        linked_retry=retried["id"],
        backup_sha256=preview["sha256"],
        protected_unchanged=True,
        protected=before,
    )
    target = out / "verification.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    index.register(
        db,
        "cat-ai",
        "WB06-verification-" + tag,
        "attachment",
        target.relative_to(root).as_posix(),
        request_id="wb06-report-" + tag,
        actor="Codex",
    )
    index.scan(db, "cat-ai")
    print(str(target))


if __name__ == "__main__":
    main()
