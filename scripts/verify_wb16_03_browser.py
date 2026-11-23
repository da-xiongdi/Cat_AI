"""Verify classified lists in Edge and smoke-test a read-only management DB copy."""

import hashlib
import re
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import wb16_01_edge_samples
import yaml
from fastapi.testclient import TestClient
from playwright.sync_api import expect, sync_playwright
from verify_wb15_browser import serve

from catalyst_ai.web.app import create_app
from catalyst_ai.workbench.backup import backup_database

ROOT = Path(__file__).resolve().parents[1]


def snapshot(db):
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        digest = hashlib.sha256()
        for statement in conn.iterdump():
            digest.update(statement.encode("utf-8") + b"\n")
        return digest.hexdigest()


def smoke_copy(directory):
    config = ROOT / "configs/workbench.yaml"
    settings = yaml.safe_load(config.read_text(encoding="utf-8"))
    workspace = (config.parent / settings["workspace"]).resolve()
    copy = directory / "management-copy.sqlite"
    backup_database(workspace / settings["database"], copy)
    app = create_app(copy, workspace, settings["project_id"], settings["project_name"])
    before = snapshot(copy)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        for page in ("tasks", "documents", "artifacts"):
            counts = {}
            for scope in (None, "all", "research", "workbench", "unclassified"):
                params = {"category": scope} if scope else {}
                response = client.get("/" + page, params=params)
                response.raise_for_status()
                counts[scope or "default"] = int(re.search(r"当前结果 (\d+) 项", response.text)[1])
            assert counts["default"] == counts["all"]
            print(f"{page}: {counts}")
    assert snapshot(copy) == before
    print("Management copy unchanged after browsing")


def browser(directory):
    sample = directory / "sample"
    wb16_01_edge_samples.OUT = sample
    wb16_01_edge_samples.main()
    db = sample / "management.sqlite"
    app = create_app(db, sample, "sample")
    before = snapshot(db)
    with serve(app) as origin, sync_playwright() as playwright:
        edge = playwright.chromium.launch(channel="msedge", headless=True)
        print(f"Edge {edge.version}")
        for width, height in ((1366, 768), (1920, 1080), (390, 844)):
            page = edge.new_page(viewport={"width": width, "height": height})
            errors = []
            page.on("pageerror", lambda error, captured=errors: captured.append(str(error)))
            page.goto(origin + "/documents?category=research")
            filters = page.locator("form.list-filters")
            filters.get_by_role("combobox", name="类别").select_option("workbench")
            filters.get_by_role("searchbox", name="编号或路径").fill("shared.md")
            filters.get_by_role("button", name="筛选").press("Enter")
            expect(page.get_by_text("工作台建设 · 当前结果 1 项")).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.reload()
            expect(filters.get_by_role("searchbox")).to_have_value("shared.md")
            page.get_by_role("link", name="Shared", exact=True).first.press("Enter")
            expect(page.locator("#plan-section")).to_have_text("# Shared")
            expect(page.locator("#plan-section")).to_be_in_viewport()
            page.get_by_role("link", name="返回文档", exact=True).click()
            assert parse_qs(urlsplit(page.url).query)["q"] == ["shared.md"]
            page.go_back()
            expect(page.locator("#plan-section")).to_be_visible()
            page.go_back()
            page.get_by_role("link", name="清除筛选").click()
            expect(filters.get_by_role("searchbox")).to_have_value("")
            page.get_by_role("navigation", name="相关台账").get_by_role("link", name="成果").click()
            assert parse_qs(urlsplit(page.url).query)["category"] == ["workbench"]
            expect(page.get_by_text("证据待复核", exact=False).first).to_be_visible()
            version_link = page.locator('a[href^="/artifacts/shared?version="]').first
            version_link.click()
            expect(
                page.get_by_text("published file version is unavailable", exact=False)
            ).to_be_visible()
            page.get_by_role("link", name="返回成果", exact=False).click()
            expect(version_link).to_be_visible()
            assert not errors, errors
            print(f"{width}x{height}: passed")
            page.close()
        edge.close()
    assert snapshot(db) == before


def main():
    with tempfile.TemporaryDirectory(prefix="wb16-03-") as directory:
        directory = Path(directory)
        smoke_copy(directory)
        browser(directory)


if __name__ == "__main__":
    main()
