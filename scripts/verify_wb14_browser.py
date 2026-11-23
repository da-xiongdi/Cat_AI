"""Verify WB-14 interactions in Edge on a disposable management database."""

import socket
import threading
import time
from urllib.parse import quote, urlencode

import uvicorn
from close_wb13 import snapshot, write_json
from playwright.sync_api import expect, sync_playwright

from catalyst_ai.web.app import create_app
from catalyst_ai.workbench import research_nodes


def seed(db, project):
    rows = snapshot(db)
    primary = next(
        row for row in rows["task_node_link"] if row["role"] == "primary" and row["active"]
    )
    branch = next(row for row in rows["research_node"] if row["id"] == primary["node_id"])
    task = primary["task_id"]
    parent = branch["id"]
    for node in ("wb14-test-subbranch", "wb14-test-leaf"):
        research_nodes.save_research_node(
            db,
            project,
            node,
            {**branch, "parent_id": parent, "sort_order": 90},
            0,
            "专项验收隔离数据",
            request_id=node,
            actor="Codex",
        )
        parent = node
    research_nodes.save_task_node_link(
        db,
        project,
        "wb14-test-reference",
        {"node_id": node, "task_id": task, "role": "reference"},
        0,
        "专项验收隔离引用",
        request_id="wb14-test-reference",
        actor="Codex",
    )
    return branch["id"], node, task


def select(node, task="", view=""):
    return "/roadmap?" + urlencode({"node": node, "task": task, "view": view})


def desktop(page, base, branch, leaf, task):
    requests = []
    page.on("request", lambda req: requests.append(req.url) if "/children" in req.url else None)
    page.goto(base + "/roadmap")
    canvas = page.locator("#roadmap-canvas")
    cards = canvas.locator(".roadmap-card")
    expect(cards.first).to_be_visible()
    expect(page.get_by_text("尚未设置科研焦点。")).to_be_visible()
    assert not requests

    def control(action):
        canvas.locator(f'[data-action="{action}"]').click()

    def zoom():
        return canvas.locator(".roadmap-content").evaluate("(e) => Number(e.style.zoom)")

    toggle = canvas.locator(f'[data-node-id="{branch}"] button')
    toggle.scroll_into_view_if_needed()
    toggle.focus()
    toggle.press("Enter")
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expect(toggle).to_be_focused()
    assert len(requests) == 1
    expect(canvas.locator(f'[data-node-id="{leaf}"]')).to_have_count(0)
    toggle.press("Space")
    expect(toggle).to_have_attribute("aria-expanded", "false")
    assert len(requests) == 1

    control("collapse")
    expect(cards).to_have_count(6)
    control("expand")
    expect(canvas.get_by_role("status")).to_contain_text("加载完成")
    expect(canvas.locator(f'[data-node-id="{leaf}"]')).to_have_count(1)
    control("in")
    assert zoom() > 1
    control("out")
    assert zoom() == 1
    control("fit")
    assert 0 < zoom() <= 1
    control("in")
    control("in")
    control("in")
    viewport = canvas.locator(".roadmap-viewport")
    viewport.evaluate("(e) => e.scrollTo(0,0)")
    box = viewport.bounding_box()
    x, y = box["x"] + box["width"] - 50, box["y"] + 25
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x - 180, y, steps=8)
    page.mouse.up()
    assert viewport.evaluate("(e) => e.scrollLeft") > 0
    control("reset")
    assert zoom() == 1 and viewport.evaluate("(e) => e.scrollLeft") == 0
    control("fullscreen")
    page.wait_for_function("!!document.fullscreenElement")
    control("fullscreen")
    page.wait_for_function("!document.fullscreenElement")

    page.goto(base + select(leaf, task))
    expect(canvas.locator(f'[data-node-id="{leaf}"].selected')).to_have_count(1)
    expect(page.locator("#selected-task")).to_contain_text(task)
    node_url = page.url
    page.reload()
    expect(canvas.locator(f'[data-node-id="{leaf}"].selected')).to_have_count(1)
    page.locator("#selected-task a").press("Enter")
    page.wait_for_url("**/tasks/*?node=*")
    page.go_back()
    assert page.url == node_url


def tree_paths(page, base, branch, leaf, task, pending):
    page.goto(base + "/roadmap?view=tree")
    expect(page.locator("#roadmap-canvas")).to_have_count(0)
    page.locator("#roadmap-tree").locator(f'a[href*="{quote(branch, safe="")}"]').press("Enter")
    page.wait_for_url("**/roadmap?node=*&view=tree")
    page.locator('a[href*="node=wb14-test-subbranch"][href*="view=tree"]').last.press("Enter")
    page.wait_for_url("**/roadmap?node=wb14-test-subbranch&view=tree")
    page.locator(f'a[href*="node={leaf}"][href*="view=tree"]').last.press("Enter")
    page.wait_for_url(f"**/roadmap?node={leaf}&view=tree")
    page.locator(f'a[href^="/tasks/{task}?node="]').press("Enter")
    page.wait_for_url("**/tasks/*?node=*")
    page.get_by_role("link", name="返回科研路线").press("Enter")
    expect(page.locator("#selected-task")).to_contain_text(task)
    assert f"node={leaf}" in page.url
    page.goto(base + f"/tasks/{task}")
    page.get_by_role("link", name="返回科研路线").press("Enter")
    expect(page.locator("#selected-task")).to_contain_text(task)
    assert branch in page.url or urlencode({"node": branch}) in page.url
    page.goto(base + f"/tasks/{pending}")
    page.get_by_role("link", name="返回科研路线").press("Enter")
    expect(page.locator("#selected-task")).to_contain_text(pending)
    page.goto(base + select("wb14-unknown", "wb14-unknown", "tree"))
    expect(page.get_by_text("定位失败", exact=False).first).to_be_visible()
    expect(page.locator("#roadmap-tree")).to_be_visible()


def concurrency(browser, base, branch):
    context = browser.new_context()
    response_statuses = []
    try:
        pages = [context.new_page(), context.new_page()]
        for i, page in enumerate(pages):
            page.goto(base + select(branch, view="tree"))
            form = page.locator('form[action="/actions/roadmap-node"]')
            form.locator('[name="sort_order"]').fill(str(900 + i))
            form.locator('[name="reason"]').fill("双标签页修订检查")
            form.locator('[name="actor"]').fill("Codex")
        for page in pages:
            with page.expect_response(
                lambda r: r.url.endswith("/actions/roadmap-node") and r.request.method == "POST"
            ) as response:
                page.locator('form[action="/actions/roadmap-node"] button').click()
            response_statuses.append(response.value.status)
        assert response_statuses == [303, 409], response_statuses
        expect(pages[-1].get_by_text("修订", exact=False).first).to_be_visible()
        return response_statuses
    finally:
        context.close()


def run(db, root, project, out, settings):
    before = snapshot(db)
    app = create_app(db, root, project, settings.project_name)
    branch, leaf, task = seed(db, project)
    pending = next(
        row["id"]
        for row in before["task"]
        if row["category"] == "research"
        and not any(link["task_id"] == row["id"] for link in before["task_node_link"])
    )
    seeded = snapshot(db)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(0.05)
            assert server.started
            results = {}
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge")
                for width, height in ((1366, 768), (1920, 1080), (390, 844)):
                    page = browser.new_page(viewport={"width": width, "height": height})
                    errors = []
                    page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
                    if width > 700:
                        desktop(page, base, branch, leaf, task)
                        page.goto(base + "/roadmap")
                        expect(page.locator(".roadmap-card").first).to_be_visible()
                        results[f"{width}x{height}"] = (
                            "lazy expansion, keyboard focus, collapse, expand, zoom, drag, "
                            "fit, reset, fullscreen, selection, reload, history"
                        )
                    else:
                        page.goto(base + "/roadmap")
                        expect(page.locator("#roadmap-canvas")).to_be_hidden()
                        page.get_by_role("link", name="树形列表").press("Enter")
                        page.wait_for_url("**/roadmap?view=tree#roadmap-tree")
                        tree_paths(page, base, branch, leaf, task, pending)
                        page.goto(base + select(leaf, view="tree"))
                        assert page.evaluate("document.documentElement.scrollWidth") <= width
                        results[f"{width}x{height}"] = (
                            "tree, keyboard navigation, main/reference/pending routes, invalid IDs"
                        )
                    page.screenshot(path=str(out / f"edge-{width}.png"))
                    assert not errors, errors
                    page.close()
                failure = browser.new_page()
                failure.route("**/children", lambda route: route.fulfill(status=503))
                failure.goto(base + select(leaf))
                expect(failure.get_by_role("status")).to_contain_text("读取失败")
                failure.locator('[data-action="expand"]').click()
                expect(failure.get_by_role("status")).to_contain_text("可再次展开重试")
                expect(failure.locator("#roadmap-tree")).to_be_visible()
                failure.unroute("**/children")
                failure.locator('[data-action="expand"]').click()
                expect(failure.get_by_role("status")).to_contain_text("加载完成")
                expect(failure.locator(f'[data-node-id="{leaf}"]')).to_have_count(1)
                failure.close()
                nojs = browser.new_page(java_script_enabled=False)
                tree_paths(nojs, base, branch, leaf, task, pending)
                nojs.close()
                assert snapshot(db) == seeded, "browsing changed database rows"
                results["read_only_browsing"] = "all tables unchanged"
                results["failure_retry_and_no_javascript"] = "passed"
                results["edge_version"] = browser.version
                results["two_tabs"] = concurrency(browser, base, branch)
                browser.close()
        finally:
            server.should_exit = True
            thread.join(timeout=10)
    write_json(out / "edge.json", results)
