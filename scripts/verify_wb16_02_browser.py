"""Exercise overview and category navigation on an isolated database in Edge."""

import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright
from verify_wb15_browser import serve

from catalyst_ai.web.app import create_app
from catalyst_ai.workbench import service


def main():
    with tempfile.TemporaryDirectory(prefix="wb16-02-browser-") as directory:
        root = Path(directory)
        db = root / "management.sqlite"
        app = create_app(db, root)
        for task_id, category in (("R1", "research"), ("W1", "workbench")):
            service.create_task(
                db,
                {
                    "id": task_id,
                    "project_id": "cat-ai",
                    "title": task_id,
                    "goal": "test",
                    "category": category,
                },
                actor="tester",
                request_id=task_id,
            )
        with serve(app) as origin, sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            for width, height in ((1366, 768), (1920, 1080), (390, 844)):
                page = browser.new_page(viewport={"width": width, "height": height})
                errors = []
                page.on("pageerror", lambda error, captured=errors: captured.append(str(error)))
                page.goto(origin + "/")
                assert page.locator('a[href="/next-work?category=workbench"]').count() > 0
                page.locator('nav[aria-label] a[href="/tasks?category=research"]').click()
                assert page.locator('a[href^="/tasks/R1?from_list="]').count() == 1
                assert page.locator('a[href^="/tasks/W1?from_list="]').count() == 0
                page.locator('input[name="q"]').last.fill("R1")
                page.locator("form.filters button").click()
                page.locator('a[href^="/tasks/R1?from_list="]').click()
                page.locator('a.back[href^="/tasks?"]').click()
                assert "category=research" in page.url and "q=R1" in page.url
                page.reload()
                assert page.locator('input[name="q"]').last.input_value() == "R1"
                page.go_back()
                page.go_back()
                assert "category=research" in page.url
                assert not errors, errors
                page.close()
                print(f"{width}x{height}: passed")
            browser.close()


if __name__ == "__main__":
    main()
