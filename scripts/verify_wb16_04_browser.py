"""Verify maintenance browsing against isolated samples and a consistent database copy."""

import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import wb16_01_edge_samples
import yaml
from fastapi.testclient import TestClient
from playwright.sync_api import expect, sync_playwright
from verify_wb15_browser import serve
from verify_wb16_03_browser import snapshot

from catalyst_ai.web.app import create_app
from catalyst_ai.workbench.backup import backup_database

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="wb16-04-") as directory:
        folder = Path(directory)
        wb16_01_edge_samples.OUT = folder / "sample"
        wb16_01_edge_samples.main()
        sample = folder / "sample"
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
                page.goto(origin + "/workbench-maintenance")
                expect(page.get_by_role("heading", name="工作台维护")).to_be_visible()
                expect(page.get_by_text("来源状态：changed", exact=False)).to_be_visible()
                expect(page.get_by_text("验收证据待复核")).to_be_visible()
                link = page.locator('a[href^="/artifacts/shared?version="]').first
                assert parse_qs(urlsplit(link.get_attribute("href")).query)["version"]
                link.click()
                assert "version=" in page.url
                page.go_back()
                page.get_by_role("link", name="关联正式任务 w").click()
                expect(page.get_by_role("heading", name="关联历史交付")).to_be_visible()
                page.get_by_role("link", name="WB-01 · 历史交付").click()
                expect(page.get_by_role("heading", name="历史交付与剩余范围")).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.get_by_role("link", name="备份与恢复").click()
                expect(page.get_by_role("heading", name="备份与恢复")).to_be_visible()
                assert not errors, errors
                page.close()
            edge.close()
        assert snapshot(db) == before
        settings = yaml.safe_load((ROOT / "configs/workbench.yaml").read_text(encoding="utf-8"))
        workspace = (ROOT / "configs" / settings["workspace"]).resolve()
        copy = folder / "production-copy.sqlite"
        backup_database(workspace / settings["database"], copy)
        app = create_app(copy, workspace, settings["project_id"], settings["project_name"])
        before = snapshot(copy)
        with TestClient(app, base_url="http://127.0.0.1") as client:
            response = client.get("/workbench-maintenance")
            response.raise_for_status()
            assert response.text.count("来源状态：changed") == 12
            assert "正式任务待补登记" in response.text
            assert "最近验收与固定证据" in response.text
        assert snapshot(copy) == before
        print("Three viewports passed; sample and production-copy databases unchanged")


if __name__ == "__main__":
    main()
