"""Verify WB-15 handoffs and document changes in isolated Edge sessions."""

import argparse
import hashlib
import json
import re
import socket
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import uvicorn
from playwright.sync_api import expect, sync_playwright

from catalyst_ai.web.app import create_app
from catalyst_ai.workbench import category_context, index, plans, research_nodes, service

PROJECT = "cat-ai"
PADDING = "Paragraph before the target.\n" * 70


def auth(request_id):
    return {"actor": "browser-check", "request_id": request_id}


def verify(db, reference, revision, request_id):
    check = plans.inspect_task_plan_reference(db, PROJECT, reference)
    plans.verify_task_plan_reference(
        db, PROJECT, reference, revision, check["current_sha256"], **auth(request_id)
    )


def reference_data(task, document, path, section, *, main=1):
    return {
        "task_id": task,
        "document_id": document,
        "path": path,
        "section_locator": section,
        "purpose": "execution_plan",
        "is_primary": main,
    }


def fixture(db, root):
    (root / "plan.md").write_text(
        PADDING + "# Research\ninitial\n# Workbench\nwork\n", encoding="utf-8"
    )
    (root / "reference.md").write_text("# Reference\nreference body\n", encoding="utf-8")
    for ident, path in (("DOC", "plan.md"), ("EXTRA", "reference.md")):
        index.register(db, PROJECT, ident, "document", path, **auth(ident))
    for category, task in (("research", "R"), ("workbench", "W"), ("research", "N")):
        service.create_task(
            db,
            {
                "id": task,
                "project_id": PROJECT,
                "title": task,
                "goal": "test",
                "category": category,
                "deliverables": ["result"],
                "criteria": [{"id": "c", "description": "check"}],
                "stages": ["A"] if task == "R" else [],
                "primary_stage": "A" if task == "R" else None,
            },
            **auth("task-" + task),
        )
    roadmap_source = b"# Stage\n"
    (root / "route.md").write_bytes(roadmap_source)
    research_nodes.save_research_node(
        db,
        PROJECT,
        "stage-a",
        {
            "stage": "A",
            "sort_order": 0,
            "source_path": "route.md",
            "source_section": "Stage",
            "source_sha256": hashlib.sha256(roadmap_source).hexdigest(),
        },
        0,
        "test",
        **auth("roadmap"),
    )
    research_nodes.save_task_node_link(
        db,
        PROJECT,
        "route-r",
        {"task_id": "R", "node_id": "stage-a", "role": "primary"},
        0,
        "test",
        **auth("route-task"),
    )
    service.add_dependency(db, "W", "R", 1, **auth("dependency"))
    category_context.set_category_focus(db, PROJECT, "workbench", "W", 0, "test", **auth("focus"))
    category_context.save_recent_task(
        db, PROJECT, "workbench", "W", 0, 1, 0, "test", **auth("recent")
    )
    for task, heading in (("R", "Research"), ("W", "Workbench")):
        ref = "REF-" + task
        plans.save_task_plan_reference(
            db,
            PROJECT,
            ref,
            reference_data(task, "DOC", "plan.md", heading),
            0,
            "test",
            **auth(ref),
        )
        verify(db, ref, 1, "verify-" + task)
    plans.save_task_plan_reference(
        db,
        PROJECT,
        "REF-EXTRA",
        reference_data("R", "EXTRA", "reference.md", "Reference", main=0),
        0,
        "test",
        **auth("reference"),
    )


@contextmanager
def serve(app):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def assert_section(page, heading, status="valid", *, long_document=True):
    expect(page.locator(f'[data-plan-status="{status}"]')).to_be_visible()
    anchor = page.locator("#plan-section")
    expect(anchor).to_have_text("# " + heading)
    expect(anchor).to_be_in_viewport()
    if long_document:
        assert anchor.evaluate("el => el.closest('pre').scrollTop") > 0


def exercise(page, origin, db, root, screenshot):
    page.goto(origin + "/next-work")
    expect(page.get_by_text("待关联主计划", exact=True)).to_have_count(1)
    for category, task, heading, label in (
        ("research", "R", "Research", "科研"),
        ("workbench", "W", "Workbench", "工作台建设"),
    ):
        page.get_by_role("link", name=label, exact=True).click()
        expect(page.get_by_role("link", name=label, exact=True)).to_have_attribute(
            "aria-current", "page"
        )
        if task == "W":
            expect(page.get_by_text("前置未完成或证据待复核：R", exact=True)).to_be_visible()
        page.get_by_role("link", name="打开主计划章节").click()
        expect(page).to_have_url(re.compile(rf"/artifacts/DOC\?task={task}.*#plan-section$"))
        assert_section(page, heading)
        page.get_by_role("link", name="返回任务 " + task).click()
        expect(page).to_have_url(re.compile(rf"/tasks/{task}\?category={category}$"))
        if task == "R":
            page.get_by_role("link", name="返回科研路线").click()
            expect(page).to_have_url(re.compile(r"/roadmap\?node=stage-a&task=R"))
            page.locator("#selected-task a").click()
            expect(page).to_have_url(re.compile(r"/tasks/R\?node=stage-a$"))
            page.go_back()
            page.go_back()
            page.get_by_role("link", name=re.compile("参考计划")).click()
            assert_section(page, "Reference", "unverified", long_document=False)
            expect(page.get_by_text("暂无核对记录", exact=True)).to_be_visible()
            page.get_by_role("link", name="返回任务 R").click()
        page.get_by_role("link", name="返回近期任务").click()
        expect(page).to_have_url(re.compile(rf"/next-work\?category={category}$"))

    page.get_by_role("link", name="科研", exact=True).click()
    doc = root / "plan.md"
    doc.write_text(PADDING + "# Research\nchanged\n# Workbench\nwork\n", encoding="utf-8")
    page.get_by_role("link", name="打开主计划章节").click()
    assert_section(page, "Research", "changed")
    expect(page.locator("[data-plan-verification]")).to_have_count(1)
    if screenshot:
        page.screenshot(path=screenshot)
    verify(db, "REF-R", 1, "reverify-changed")
    page.reload()
    assert_section(page, "Research")
    expect(page.locator("[data-plan-verification]")).to_have_count(2)

    for markdown, status in (
        ("# Renamed\nnew body\n", "section_missing"),
        ("# Research\none\n# Research\ntwo\n", "section_ambiguous"),
        (None, "missing_or_invalid"),
    ):
        if markdown is None:
            doc.unlink()
        else:
            doc.write_text(markdown, encoding="utf-8")
        page.reload()
        expect(page.locator(f'[data-plan-status="{status}"]')).to_be_visible()
        expect(page.locator("#plan-section")).to_have_count(0)
        expect(page.locator("[data-plan-verification]")).to_have_count(2)

    doc.write_text(PADDING + "# Renamed\nnew body\n# Workbench\nwork\n", encoding="utf-8")
    plans.save_task_plan_reference(
        db,
        PROJECT,
        "REF-R",
        reference_data("R", "DOC", "plan.md", "Renamed"),
        1,
        "correct heading",
        **auth("correct"),
    )
    verify(db, "REF-R", 2, "verify-corrected")
    page.reload()
    assert_section(page, "Renamed")
    expect(page.locator("[data-plan-verification]")).to_have_count(3)

    revision = service.get_task(db, "W")["revision"]
    service.set_task_category(db, PROJECT, "W", "research", revision, "test", **auth("reclassify"))
    page.get_by_role("link", name="返回近期任务").click()
    page.get_by_role("link", name="工作台建设", exact=True).click()
    expect(page.get_by_text("待复核", exact=True)).to_have_count(1)
    expect(page.get_by_text("待关联主计划", exact=True)).to_have_count(0)
    page.get_by_role("link", name="打开主计划章节").click()
    assert_section(page, "Workbench", "changed")
    page.get_by_role("link", name="返回近期任务").click()
    expect(page).to_have_url(re.compile(r"/next-work\?category=workbench$"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path)
    evidence = parser.parse_args().evidence_dir
    if evidence:
        evidence.mkdir(parents=True, exist_ok=True)
    results = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        print("Edge", browser.version)
        for width, height in ((1366, 768), (1920, 1080), (390, 844)):
            dimension = f"{width}x{height}"
            with tempfile.TemporaryDirectory(prefix="wb15-browser-") as directory:
                root = Path(directory)
                db = root / "management.sqlite"
                app = create_app(db, root)
                fixture(db, root)
                with serve(app) as origin:
                    page = browser.new_page(viewport={"width": width, "height": height})
                    errors = []
                    page.on("pageerror", lambda error, captured=errors: captured.append(str(error)))
                    exercise(
                        page,
                        origin,
                        db,
                        root,
                        evidence / f"edge-{dimension}.png" if evidence else None,
                    )
                    assert not errors, errors
                    page.close()
            results[dimension] = "passed"
            print(f"{dimension}: handoffs, changes, history and reclassification passed")
        if evidence:
            (evidence / "edge.json").write_text(
                json.dumps(
                    {"edge": browser.version, "headless": True, "viewports": results}, indent=2
                )
                + "\n",
                encoding="utf-8",
            )
        browser.close()


if __name__ == "__main__":
    main()
