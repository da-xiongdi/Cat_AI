import re
from html import unescape
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from catalyst_ai.storage.workbench import transaction
from catalyst_ai.web.app import create_app
from catalyst_ai.workbench import index, plans, research, service


def auth(key):
    return {"actor": "tester", "request_id": key}


@pytest.fixture
def workbench(tmp_path):
    db = tmp_path / "workbench.sqlite"
    with TestClient(create_app(db, tmp_path), base_url="http://localhost") as client:
        yield db, client


def task(db, task_id, category, *, stages=()):
    service.create_task(
        db,
        {
            "id": task_id,
            "project_id": "cat-ai",
            "title": f"Filtered {task_id}",
            "goal": "Test",
            "category": category,
            "stages": stages,
            "primary_stage": stages[0] if stages else None,
            "deliverables": [f"Scope {task_id}"],
            "criteria": [{"id": "check", "description": "Test"}],
        },
        **auth(task_id),
    )


def document(db, root, artifact_id, path=None):
    path = root / (path or artifact_id + ".md")
    path.write_text("# Section\nOriginal\n", encoding="utf-8")
    index.register(db, "cat-ai", artifact_id, "document", path.name, **auth(artifact_id))
    return path


def purpose(db, artifact_id, category, purpose="execution_plan", *, active=1):
    key = f"{artifact_id}-{category}-{purpose}-{active}"
    plans.save_document_purpose(
        db,
        "cat-ai",
        key,
        {"document_id": artifact_id, "category": category, "purpose": purpose, "active": active},
        0,
        "Test",
        **auth("purpose-" + key),
    )


def reference(db, task_id, artifact_id, path, *, verify):
    key = "reference-" + task_id + "-" + artifact_id
    plans.save_task_plan_reference(
        db,
        "cat-ai",
        key,
        {
            "document_id": artifact_id,
            "task_id": task_id,
            "path": path.name,
            "section_locator": "Section",
            "purpose": "execution_plan",
        },
        0,
        "Test",
        **auth(key),
    )
    if verify:
        sha = plans.inspect_task_plan_reference(db, "cat-ai", key)["current_sha256"]
        plans.verify_task_plan_reference(db, "cat-ai", key, 1, sha, **auth("verify-" + key))
    return key


def review(db, task_id, artifact_id, version):
    revision = service.get_task(db, task_id)["revision"]
    service.transition(db, task_id, revision, "ready", **auth(task_id + "-ready"))
    service.transition(db, task_id, revision + 1, "in_progress", **auth(task_id + "-start"))
    service.submit_review(
        db,
        task_id,
        revision + 2,
        [
            {
                "criterion_id": "check",
                "passed": True,
                "evidence_id": artifact_id,
                "evidence_version": version,
            }
        ],
        "Test",
        **auth(task_id + "-submission"),
    )
    service.accept_review(db, task_id, revision + 3, "Test", **auth(task_id + "-acceptance"))


def test_task_filters_paginate_and_restore_context(workbench, tmp_path):
    db, client = workbench
    for task_id, category, stage in (
        ("A-OTHER", "workbench", "A"),
        ("B-FIRST", "research", "A"),
        ("C-LAST", "research", "A"),
        ("D-STAGE", "research", "B"),
        ("U", None, "A"),
    ):
        task(db, task_id, category, stages=[stage])
    service.add_dependency(db, "C-LAST", "A-OTHER", 1, **auth("dependency"))
    path = document(db, tmp_path, "PLAN")
    ref = reference(db, "C-LAST", "PLAN", path, verify=True)
    params = dict(category="research", status="planned", stage="A", q="filtered", limit=1)
    first = client.get("/tasks", params=params).text
    assert "当前结果 2 项" in first and "Filtered B-FIRST" in first
    assert "Filtered A-OTHER" not in first and "Filtered C-LAST" not in first
    query = urlencode({**params, "offset": 1}).replace("&", "&amp;")
    assert f'href="/tasks?{query}"' in first
    second = client.get("/tasks", params={**params, "offset": 1}).text
    assert "Filtered C-LAST" in second and "Filtered B-FIRST" not in second
    context = (
        "from_list=1&category=research&status=planned&stage=A&q=filtered&list_offset=1&list_limit=1"
    )
    detail = client.get("/tasks/C-LAST?" + context).text
    back = urlencode({**params, "offset": 1})
    # Back links retain the same parameters, independent of query parameter ordering.
    href = unescape(re.search(r'href="(/tasks\?[^"]+)">← 返回任务', detail)[1])
    assert parse_qs(urlsplit(href).query) == parse_qs(back)
    assert "/tasks/A-OTHER?category=workbench" in detail
    preview = client.get(f"/artifacts/PLAN?task=C-LAST&reference={ref}&{context}").text
    assert 'id="plan-section"' in preview
    assert "/tasks/C-LAST?" + context.replace("&", "&amp;") in preview
    assert "Filtered U" in client.get("/tasks?category=unclassified").text
    for name in ("tasks", "documents", "artifacts"):
        for invalid in ("wrong", ""):
            assert client.get("/" + name, params={"category": invalid}).status_code == 422


def test_documents_use_same_project_active_and_verified_bases(workbench, tmp_path):
    db, client = workbench
    task(db, "R", "research")
    task(db, "W", "workbench")
    shared = document(db, tmp_path, "SHARED", "system-plan.md")
    purpose(db, "SHARED", "research")
    ref = reference(db, "W", "SHARED", shared, verify=True)
    document(db, tmp_path, "SYSTEM")
    purpose(db, "SYSTEM", None, "research_plan")
    document(db, tmp_path, "INACTIVE")
    purpose(db, "INACTIVE", "research", active=0)
    pending = document(db, tmp_path, "PENDING")
    reference(db, "R", "PENDING", pending, verify=False)
    document(db, tmp_path, "MISMATCH")
    purpose(db, "MISMATCH", "research", "construction_plan")
    with transaction(db) as conn:
        # The relevant record sorts after the old project-level cap.
        conn.executemany(
            "INSERT INTO artifact(id,project_id,kind,created_at) VALUES(?,'cat-ai','document','0')",
            [(f"000-{number:03}",) for number in range(501)],
        )
    for category in ("research", "workbench", "all"):
        result = client.get("/documents", params={"category": category, "q": "SYSTEM-PLAN"})
        assert result.text.count(">SHARED</a>") == 1
        assert "当前结果 1 项" in result.text and f"reference={ref}" in result.text
    assert ">SYSTEM</a>" in client.get("/documents?category=research").text
    assert ">SHARED</a>" in client.get("/documents?category=workbench&limit=1").text
    pending_list = client.get("/documents?category=unclassified&offset=501").text
    assert "用途待核对" in pending_list and "尚未核对" in pending_list
    assert ">INACTIVE</a>" in pending_list
    shared.write_text("# Section\nChanged\n", encoding="utf-8")
    assert ">SHARED</a>" not in client.get("/documents?category=workbench").text
    result = client.get("/documents?category=unclassified&q=system-plan").text
    assert ">SHARED</a>" in result and "文件或引用已变化" in result
    preview = client.get(
        f"/artifacts/SHARED?task=W&reference={ref}&list_source=documents"
        "&category=unclassified&q=system-plan"
    ).text
    assert 'href="/documents?category=unclassified&amp;q=system-plan"' in preview
    assert 'id="plan-section"' in preview
    assert client.get(f"/artifacts/SYSTEM?task=W&reference={ref}").status_code == 404


def test_artifacts_match_fixed_versions_and_keep_research_issue_links(workbench, tmp_path):
    db, client = workbench
    for task_id, category in (("R", "research"), ("W", "workbench"), ("U", None)):
        task(db, task_id, category)
    shared = document(db, tmp_path, "SHARED")
    document(db, tmp_path, "UNPAIRED")
    index.scan(db, "cat-ai")
    old = index.get_artifact(db, "SHARED")["revisions"][0]["file_sha256"]
    review(db, "R", "SHARED", old)
    shared.write_text("# Section\nNew version\n", encoding="utf-8")
    stale = client.get("/artifacts?category=research").text
    assert old in stale and "证据待复核" in stale
    index.scan(db, "cat-ai")
    current = index.get_artifact(db, "SHARED")["revisions"][0]["file_sha256"]
    assert old != current
    review(db, "W", "SHARED", current)
    service.set_evidence(
        db, "cat-ai", "UNPAIRED", "custom", "Manual", "available", **auth("manual")
    )
    review(db, "U", "UNPAIRED", "custom")
    research.save(
        db,
        "cat-ai",
        "issues",
        "ISSUE-1",
        {
            "task_id": "W",
            "title": "Linked issue",
            "status": "researching",
            "scope": "Test",
            "conclusion": "Test",
            "evidence": [{"id": "SHARED", "version": current, "role": "result"}],
        },
        0,
        **auth("issue"),
    )
    for scope in ("research", "workbench", "all"):
        response = client.get(f"/artifacts?category={scope}&q=SHARED&limit=1")
        assert response.text.count(">SHARED</a>") == 1
        assert "当前结果 1 项" in response.text
        assert old in response.text and current in response.text
        assert "Scope R" in response.text and "Scope W" in response.text
        assert "ISSUE-1" in response.text
    unmatched = client.get("/artifacts?category=unclassified&q=UNPAIRED").text
    assert "成果与证据版本未配对" in unmatched
    assert "version=custom" not in unmatched
    assert "已完成" in client.get("/tasks?category=research&status=done").text
    assert "证据待复核 1 项" in client.get("/tasks?category=research&status=done").text
    assert "工作台建设有效完成 1 项" in client.get("/tasks?category=workbench&status=done").text
    old_preview = client.get(f"/artifacts/SHARED?version={old}")
    assert (
        old_preview.status_code == 200
        and "published file version is unavailable" in old_preview.text
    )
    current_preview = client.get(
        f"/artifacts/SHARED?version={current}&list_source=artifacts&category=workbench&q=SHARED"
    ).text
    assert "New version" in current_preview
    assert 'href="/artifacts?category=workbench&amp;q=SHARED"' in current_preview
    task_detail = client.get("/tasks/W?from_list=1&category=workbench").text
    assert "Linked issue" in task_detail and "#issue-ISSUE-1" in task_detail
    issue = client.get("/research?kind=issues&task=W&from_list=1&category=workbench").text
    assert 'id="issue-ISSUE-1"' in issue
    assert 'href="/tasks/W?from_list=1&amp;category=workbench"' in issue
    service.create_project(db, "other", "Other", **auth("other-project"))
    with transaction(db) as conn:
        conn.execute(
            "UPDATE evidence SET project_id='other' WHERE id='SHARED' AND version=?", (current,)
        )
    assert ">SHARED</a>" not in client.get("/artifacts?category=workbench&q=SHARED").text
    unclassified = client.get("/artifacts?category=unclassified&q=SHARED").text
    assert "成果与证据版本未配对" in unclassified
    assert f"version={current}" not in unclassified
    assert "证据待复核 1 项" in client.get("/tasks?category=workbench&status=done").text


def test_maintenance_page_empty_and_navigation(workbench):
    _, client = workbench
    response = client.get("/workbench-maintenance")
    assert response.status_code == 200
    assert "历史交付与剩余范围" in response.text
    assert "暂无历史交付登记" in response.text
    assert "/foundation" in response.text
    assert "/workbench-maintenance" in client.get("/").text
