"""Exercise continuous handoffs and compare every table on a production copy."""

import hashlib
import json
import re
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

import wb16_01_edge_samples
from playwright.sync_api import expect, sync_playwright
from verify_wb15_browser import serve

from catalyst_ai.web.app import create_app
from catalyst_ai.web.config import load
from catalyst_ai.workbench.backup import backup_database

ROOT = Path(__file__).resolve().parents[1]


def tables(db):
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        assert conn.execute("pragma quick_check").fetchone()[0] == "ok"
        assert not conn.execute("pragma foreign_key_check").fetchall()
        names = conn.execute("select name from sqlite_master where type='table' order by name")
        result = {}
        for (name,) in names.fetchall():
            quoted = '"' + name.replace('"', '""') + '"'
            rows = sorted(repr(row) for row in conn.execute(f"select * from {quoted}"))
            result[name] = {
                "rows": len(rows),
                "sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest(),
            }
        return result


def main():
    output = ROOT / "artifacts" / "wb16-05-verification.json"
    with tempfile.TemporaryDirectory(prefix="wb16-05-") as directory:
        folder = Path(directory)
        wb16_01_edge_samples.OUT = folder / "sample"
        wb16_01_edge_samples.main()
        sample = wb16_01_edge_samples.OUT
        db = sample / "management.sqlite"
        app = create_app(db, sample, "sample")
        before = tables(db)
        with serve(app) as origin, sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            version = browser.version
            for width, height in ((1366, 768), (1920, 1080), (390, 844)):
                page = browser.new_page(viewport={"width": width, "height": height})
                errors = []
                page.on("pageerror", lambda e, captured=errors: captured.append(str(e)))
                page.goto(origin + "/")
                page.locator('nav a[href="/tasks?category=research"]').click()
                page.locator('a[href^="/tasks/r?from_list="]').click()
                page.get_by_role("link", name="主计划 · shared.md · Shared").click()
                expect(page.locator("#plan-section")).to_have_text("# Shared")
                page.go_back()
                page.get_by_role("link", name="返回科研路线").click()
                expect(page).to_have_url(re.compile(r"/roadmap\?task=r"))
                page.go_back()
                page.get_by_role("link", name="返回任务", exact=False).last.click()
                assert "category=research" in page.url
                page.reload()
                page.get_by_role("link", name="清除筛选").click()
                assert "category=research" in page.url

                page.goto(origin + "/")
                page.get_by_role("link", name="进入工作台维护").click()
                page.get_by_role("link", name="关联正式任务 w").click()
                page.get_by_role("link", name="主计划 · shared.md · Shared").click()
                expect(page.locator("#plan-section")).to_have_text("# Shared")
                page.go_back()
                page.get_by_role("link", name="WB-01 · 历史交付").click()
                page.locator('a[href^="/artifacts/shared?version="]').first.click()
                assert "version=" in page.url
                page.go_back()
                expect(page.get_by_role("heading", name="历史交付与剩余范围")).to_be_visible()
                assert not errors, errors
                page.close()
            browser.close()
        assert tables(db) == before

        settings, workspace, original = load(ROOT / "configs/workbench.yaml")
        copy = folder / "production.sqlite"
        backup_database(original, copy)
        app = create_app(copy, workspace, settings.project_id, settings.project_name)
        before = tables(copy)
        with serve(app) as origin, sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page()
            routes = [
                "/",
                "/tasks",
                "/tasks?category=research",
                "/tasks?category=workbench",
                "/tasks?category=unclassified",
                "/documents",
                "/artifacts",
                "/decisions",
                "/research",
                "/roadmap",
                "/next-work?category=research",
                "/next-work?category=workbench",
                "/workbench-maintenance",
                "/foundation",
                "/predictions",
                "/model-evidence",
            ]
            statuses = {}
            for route in routes:
                response = page.goto(origin + route)
                statuses[route] = response.status
                assert response.status == 200, (route, response.status)
            page.goto(origin + "/tasks?category=unclassified")
            expect(page.get_by_text("当前结果 0 项", exact=False)).to_be_visible()
            page.goto(origin + "/workbench-maintenance")
            assert page.get_by_text("来源状态：changed", exact=False).count() == 12
            expect(page.get_by_text("正式任务待补登记", exact=False).first).to_be_visible()
            page.goto(origin + "/tasks?category=research")
            expect(page.get_by_text("当前结果 14 项", exact=False)).to_be_visible()
            page.goto(origin + "/tasks?category=workbench")
            expect(page.get_by_text("当前结果 29 项", exact=False)).to_be_visible()
            expect(page.locator("body")).not_to_be_empty()
            browser.close()
        after = tables(copy)
        assert before == after
        output.write_text(
            json.dumps(
                {"edge": version, "routes": statuses, "before": before, "after": after},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"continuous paths passed; {len(before)} tables unchanged; evidence: {output}")


if __name__ == "__main__":
    main()
