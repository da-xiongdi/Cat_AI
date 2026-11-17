"""Record WB-05/08 closeout against the real management store and an isolated browser copy."""

import hashlib
import json
import threading
import time
import uuid
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright

from catalyst_ai.storage.workbench import SCHEMA_VERSION, migrate
from catalyst_ai.web.app import create_app
from catalyst_ai.workbench import backup, import_draft, index, research, service


def main():
    root = Path(__file__).resolve().parents[1]
    db = root / "data/workbench.sqlite"
    tag = uuid.uuid4().hex[:12]
    out = root / "backups" / ("wb-closeout-" + tag)
    out.mkdir(parents=True)
    protected = [root / "data/catalog.sqlite"]
    protected += [
        p
        for directory in ("data/snapshots", "artifacts/models")
        for p in (root / directory).rglob("*")
        if p.is_file()
    ]

    def hashes():
        return {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected
        }

    before = hashes()
    backup.backup_database(db, out / "before.sqlite")
    migrate(db)
    draft = root / "docs/workbench/first_import.json"
    preview = import_draft.preview(root, draft)
    repeat = import_draft.apply(
        db, root, draft, preview["manifest_sha256"], request_id="repeat-" + tag, actor="Codex"
    )
    index.scan(db, "cat-ai")
    doc = index.get_artifact(db, "S1A-acceptance")["revisions"][0]["file_sha256"]
    entries = [
        (
            "claims",
            "S1A-historical-548",
            dict(
                title="S1-A historical feedback: 548/593",
                object_type="governance",
                classification="planned",
                scope="2026-11-10 historical feedback",
                conclusion="Superseded by the 2026-11-13 553/593 engineering acceptance",
                limitations="Historical statement, not a new verification",
                evidence=[dict(id="S1A-acceptance", version=doc, role="historical_report")],
            ),
        ),
        (
            "claims",
            "S1A-current-553",
            dict(
                title="S1-A documented engineering acceptance: 553/593",
                object_type="governance",
                classification="planned",
                task_id="S1A-01",
                scope="Historical engineering acceptance; 40 excluded records",
                conclusion="Engineering task accepted; research source review remains limited",
                limitations="Dataset acceptance; no row-by-row verification; assumed pressure",
                evidence=[dict(id="S1A-acceptance", version=doc, role="report")],
            ),
        ),
        (
            "issues",
            "DIFF-S1B",
            dict(
                title="S1-B build exists; acceptance pending",
                status="researching",
                task_id="S1B-01",
                scope="v4 selection and features versus older progress headings",
                conclusion="Retain build evidence; verify all criteria before completing the task",
                evidence=[
                    dict(
                        id=ident,
                        version=index.get_artifact(db, ident)["revisions"][0]["file_sha256"],
                        role=role,
                    )
                    for ident, role in (
                        ("S1B-features", "features"),
                        ("S1B-selection", "selection"),
                    )
                ],
            ),
        ),
    ]
    for kind, ident, content in entries:
        old = [r for r in research.list_records(db, "cat-ai", kind) if r["id"] == ident]
        previous = json.loads(json.dumps(old[0]["content"])) if old else None
        if previous:
            for ref in previous["evidence"]:
                ref.pop("status", None)
        if not old:
            research.save(
                db,
                "cat-ai",
                kind,
                ident,
                content,
                old[0]["revision"] if old else 0,
                request_id=ident + tag,
                actor="Codex",
            )
    bundle = backup.create_bundle(db, root)
    (out / "bundle.zip").write_bytes(bundle)
    manifest = backup.preview_bundle(bundle)
    assert not manifest["manifest"]["missing"]
    backup.restore_bundle(bundle, out / "restored", manifest["sha256"])
    restored = out / "restored/workbench.sqlite"
    assert service.get_task(restored, "S1A-01")["status"] == "done"
    for kind in ("claims", "issues"):
        assert research.list_records(restored, "cat-ai", kind) == research.list_records(
            db, "cat-ai", kind
        )
    index.scan(restored, "cat-ai")
    assert index.get_artifact(restored, "R1-model")["revisions"][0]["status"] == "available"
    browser_db = out / "browser.sqlite"
    backup.backup_database(db, browser_db)
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(browser_db, root), host="127.0.0.1", port=18765, log_level="error"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    assert server.started
    errors = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge", headless=True)
            for width, height in ((1366, 768), (1920, 1080), (390, 844)):
                page = browser.new_page(viewport=dict(width=width, height=height))
                page.on("pageerror", lambda error: errors.append(str(error)))
                for url in (
                    "/",
                    "/tasks",
                    "/tasks/S1A-01",
                    "/artifacts",
                    "/decisions",
                    "/documents",
                    "/foundation",
                    "/foundation/samples",
                    "/foundation?kind=fields",
                    "/foundation?kind=governance",
                    "/model-evidence",
                    "/research",
                    "/research?kind=issues",
                    "/pending/screening",
                    "/pending/candidates",
                    "/pending/experiments",
                ):
                    response = page.goto("http://127.0.0.1:18765" + url)
                    assert response.status == 200, (url, response.status)
                page.goto("http://127.0.0.1:18765/tasks/new")
                for name, value in dict(
                    task_id="browser-" + str(width),
                    title="Browser acceptance",
                    goal="Verify browser workflow",
                    deliverables="Fixed review record",
                    criteria="c | Check browser",
                    actor="Codex browser",
                ).items():
                    page.locator('[name="' + name + '"]').fill(value)
                page.locator('button[type="submit"]').count()
                page.locator('form[action="/actions/create-task"] button').click()
                assert "browser-" + str(width) in page.url
                for target in ("ready", "in_progress"):
                    form = page.locator('form[action="/actions/transition"]')
                    form.locator('[name="target"]').select_option(target)
                    form.locator('[name="actor"]').fill("Codex browser")
                    form.locator("button").click()
                form = page.locator('form[action="/actions/submit-review"]')
                form.locator('[name="result-c"]').select_option("pass")
                form.locator('[name="evidence-c"]').select_option("S1A-acceptance|" + doc)
                form.locator('[name="explanation-c"]').fill("Verified fixed document version")
                form.locator('[name="conclusion"]').fill("Browser workflow passed")
                form.locator('[name="actor"]').fill("Codex browser")
                form.locator("button").click()
                form = page.locator('form[action="/actions/accept-review"]')
                form.locator('[name="conclusion"]').fill("Accepted in isolated browser database")
                form.locator('[name="actor"]').fill("Codex browser")
                form.locator("button").click()
                assert service.get_task(browser_db, "browser-" + str(width))["status"] == "done"
                page.screenshot(path=str(out / (str(width) + ".png")), full_page=True)
                page.goto("http://127.0.0.1:18765/research")
                form = page.locator('form[action="/actions/save-research"]')
                form.locator('[name="id"]').fill("browser-claim-" + str(width))
                content = dict(
                    title="Browser claim",
                    object_type="candidate",
                    classification="validated",
                    scope="Browser test",
                    conclusion="Reject missing experiment",
                    limitations="Test",
                    evidence=[],
                )
                form.locator('[name="content"]').fill(json.dumps(content))
                form.locator('[name="actor"]').fill("Codex browser")
                form.locator("button").click()
                assert "missing evidence roles" in page.content()
                page.goto("http://127.0.0.1:18765/research")
                form = page.locator('form[action="/actions/save-research"]')
                form.locator('[name="id"]').fill("browser-claim-" + str(width))
                content["classification"] = "planned"
                form.locator('[name="content"]').fill(json.dumps(content))
                form.locator('[name="actor"]').fill("Codex browser")
                form.locator("button").click()
                assert "browser-claim-" + str(width) in page.content()
                response = page.request.get(
                    "http://127.0.0.1:18765/api/workbench/v1/exports/progress"
                )
                assert response.status == 200 and "generated_at" in response.json()
                page.close()
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    assert not errors, errors
    assert before == hashes(), "protected data changed"
    report = dict(
        directory=str(out),
        repeat_import=repeat,
        bundle_sha256=manifest["sha256"],
        browser_viewports=[1366, 1920, 390],
        browser_errors=errors,
        protected_hashes=before,
        protected_unchanged=True,
        tasks=len(service.list_tasks(db, "cat-ai")),
        schema=SCHEMA_VERSION,
    )
    (out / "verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in report.items() if k != "protected_hashes"}))


if __name__ == "__main__":
    main()
