"""Loopback-only workbench web application."""

import hmac
import json
import re
import secrets
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import select_autoescape

from catalyst_ai.storage.workbench import migrate, transaction
from catalyst_ai.workbench import (
    adapters,
    backup,
    decisions,
    foundation,
    index,
    model_runs,
    predictions,
    queries,
    research,
    research_nodes,
    roadmap,
    samples,
    service,
)

HERE = Path(__file__).parent
LABELS = {
    "queued": "排队中",
    "running": "执行中",
    "succeeded": "执行完成",
    "failed": "执行失败",
    "interrupted": "执行中断",
    "ok": "预测完成",
    "invalid_input": "输入无效",
    "unsupported_species_role": "物种或角色不支持",
    "output_out_of_range": "预测值超出范围",
    "nonfinite_prediction": "预测值无效",
    "planned": "待规划",
    "ready": "可开始",
    "in_progress": "进行中",
    "in_review": "待验收",
    "done": "已完成",
    "blocked": "阻塞",
    "cancelled": "已取消",
    "available": "可用",
    "pending": "待检查",
    "changed": "已变化",
    "missing": "缺失",
    "invalid": "无效",
    "read_error": "读取失败",
}


def create_app(db: Path, root: Path, project_id="cat-ai", project_name="Cat AI"):
    db, root = Path(db).resolve(), Path(root).resolve(strict=True)
    if db == (root / "data/catalog.sqlite").resolve():
        raise ValueError("management database cannot be the domain database")
    migrate(db)
    with transaction(db) as conn:
        exists = conn.execute("SELECT 1 FROM project WHERE id=?", (project_id,)).fetchone()
    if not exists:
        service.create_project(
            db,
            project_id,
            project_name,
            request_id="init-project-" + uuid.uuid4().hex,
            actor="系统",
        )
    index.configure_workspace(
        db, project_id, root, request_id="init-workspace-" + uuid.uuid4().hex, actor="系统"
    )
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=str(HERE / "templates"))
    templates.env.autoescape = select_autoescape(default=True, default_for_string=True)
    token = secrets.token_urlsafe(32)
    restore_previews = {}

    def localtime(value):
        if not value:
            return "未设置"
        try:
            return (
                datetime.fromisoformat(value)
                .astimezone(ZoneInfo("Asia/Shanghai"))
                .strftime("%Y-%m-%d %H:%M")
            )
        except (ValueError, TypeError):
            return value

    templates.env.filters["localtime"] = localtime
    templates.env.filters["label"] = lambda value: LABELS.get(value, value)
    templates.env.filters["pretty"] = lambda value: json.dumps(value, ensure_ascii=False, indent=2)

    @app.middleware("http")
    async def security(request, call_next):
        host = request.headers.get("host", "").lower()
        hostname = host.split(":", 1)[0]
        if hostname not in {"127.0.0.1", "localhost"}:
            return PlainTextResponse("仅允许本机访问", status_code=403)
        if request.method not in ("GET", "HEAD"):
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/").lower() != f"{request.url.scheme}://{host}":
                return PlainTextResponse("来源不允许", status_code=403)
            if request.url.path.startswith("/api/"):
                provided_token = request.headers.get("x-csrf-token", "")
            else:
                await request.body()
                form = await request.form()
                provided_token = str(form.get("csrf", ""))
            if not hmac.compare_digest(provided_token, token):
                return PlainTextResponse("请求令牌无效", status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        return response

    def render(request, page, status_code=200, **kwargs):
        with transaction(db) as conn:
            project = dict(
                conn.execute("SELECT * FROM project WHERE id=?", (project_id,)).fetchone()
            )
            scan = conn.execute(
                "SELECT s.finished_at FROM published_index p JOIN index_scan s ON s.id=p.scan_id "
                "WHERE p.project_id=?",
                (project_id,),
            ).fetchone()
        return templates.TemplateResponse(
            request=request,
            name="page.html",
            context={
                "page": page,
                "project": project,
                "scan_time": scan[0] if scan else None,
                "csrf": token,
                "request_id": uuid.uuid4().hex,
                **kwargs,
            },
            status_code=status_code,
        )

    def tasks():
        return [service.get_task(db, row["id"]) for row in service.list_tasks(db, project_id)]

    def task_for(task_id):
        task = service.get_task(db, task_id)
        if task["project_id"] != project_id:
            raise service.Missing("任务不存在")
        return task

    def artifact_for(artifact_id):
        artifact = index.get_artifact(db, artifact_id)
        if artifact["project_id"] != project_id:
            raise service.Missing("成果不存在")
        return artifact

    @app.exception_handler(service.Missing)
    async def missing(request, exc):
        return render(request, "message", status_code=404, message=str(exc))

    @app.get("/api/workbench/v1/query")
    async def management_query(category: str = "all"):
        if category not in queries.SCOPES:
            return JSONResponse({"detail": "invalid category scope"}, status_code=422)
        return queries.query(db, project_id, category)

    @app.get("/api/workbench/v1/roadmap/nodes/{node_id}/children")
    async def roadmap_children(node_id: str):
        data = roadmap.snapshot(db, project_id)
        parent = data["nodes"].get(node_id)
        if parent is None:
            raise service.Missing("路线节点不存在")
        return {"parent_id": node_id, "items": [data["nodes"][i] for i in parent["child_ids"]]}

    @app.get("/roadmap", response_class=HTMLResponse)
    async def roadmap_page(request: Request, node: str = "", task: str = "", view: str = ""):
        data = roadmap.snapshot(db, project_id)
        with transaction(db) as conn:
            node_history = (
                [
                    dict(r)
                    for r in conn.execute(
                        "SELECT * FROM research_node_revision WHERE project_id=? "
                        "AND entity_id=? ORDER BY revision DESC",
                        (project_id, node),
                    )
                ]
                if node
                else []
            )
            link_history = (
                [
                    dict(r)
                    for r in conn.execute(
                        "SELECT r.* FROM task_node_link_revision r WHERE r.project_id=? AND "
                        "(json_extract(r.old_value, '$.node_id')=? OR "
                        "json_extract(r.new_value, '$.node_id')=?) ORDER BY r.created_at DESC",
                        (project_id, node, node),
                    )
                ]
                if node
                else []
            )
        selected = data["nodes"].get(node) if node else None
        task_links = [link for link in data["links"] if link["task_id"] == task]
        if task and not node and task_links:
            node = next((link["node_id"] for link in task_links if link["role"] == "primary"), "")
            selected = data["nodes"].get(node)
        path = []
        cursor = selected
        while cursor:
            path.insert(0, cursor)
            cursor = data["nodes"].get(cursor["parent_id"])
        initial_ids = {i for stage in data["stages"] for i in stage["root_ids"]}
        initial_ids |= {child for i in initial_ids for child in data["nodes"][i]["child_ids"]}
        return render(
            request,
            "roadmap",
            roadmap=data,
            initial_nodes={i: data["nodes"][i] for i in initial_ids},
            selected=selected,
            missing_node=bool(node and not selected),
            missing_task=bool(
                task
                and (
                    task not in data["tasks"]
                    or (node and not any(link["node_id"] == node for link in task_links))
                )
            ),
            selected_task=task,
            node_path=path,
            roadmap_view=view,
            node_history=node_history,
            link_history=link_history,
        )

    @app.get("/", response_class=HTMLResponse)
    async def overview(request: Request):
        rows = tasks()
        milestones = []
        for milestone in ("S1-A", "S1-B", "S2", "S3"):
            subset = [t for t in rows if t["milestone"] == milestone]
            milestones.append(
                {
                    "name": milestone,
                    "total": len(subset),
                    "done": sum(t["status"] == "done" for t in subset),
                }
            )
        with transaction(db) as conn:
            activity = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM activity WHERE project_id=? ORDER BY id DESC LIMIT 8",
                    (project_id,),
                )
            ]
            sources = conn.execute(
                "SELECT count(DISTINCT legacy_id) FROM foundation_record "
                "WHERE project_id=? AND kind='sources'",
                (project_id,),
            ).fetchone()[0]
        claims = research.list_records(db, project_id, "claims")
        latest_claims = {r["id"]: r for r in reversed(claims)}
        snapshots = [
            a
            for a in index.list_artifacts(db, project_id, limit=500)["items"]
            if a["kind"] == "snapshot"
        ]
        return render(
            request,
            "overview",
            tasks=rows,
            milestones=milestones,
            activity=activity,
            artifacts=index.list_artifacts(db, project_id, limit=10)["items"],
            decisions=decisions.list_decisions(db, project_id)[:5],
            source_count=sources,
            research_counts={
                key: sum(
                    r["content"]["classification"] == key and not r["needs_review"]
                    for r in latest_claims.values()
                )
                for key in ("planned", "implemented", "validated")
            },
            snapshot_stats=snapshots,
            research_records=claims,
        )

    @app.get("/pending/{module}", response_class=HTMLResponse)
    async def pending_module(request: Request, module: str):
        titles = {
            "screening": "虚拟筛选",
            "candidates": "候选配方对比",
            "experiments": "实验验证与回灌",
        }
        if module not in titles:
            return render(request, "message", status_code=404, message="模块不存在")
        return render(request, "pending", title=titles[module])

    @app.get("/research", response_class=HTMLResponse)
    async def research_page(request: Request, kind: str = "claims"):
        if kind not in {"claims", "issues"}:
            raise service.Missing("研究台账不存在")
        return render(
            request, "research", kind=kind, records=research.list_records(db, project_id, kind)
        )

    @app.get("/api/workbench/v1/exports/progress")
    async def export_progress():
        return Response(
            json.dumps(
                {
                    "generated_at": datetime.now(ZoneInfo("UTC")).isoformat(),
                    "project_id": project_id,
                    "tasks": tasks(),
                    "claims": research.list_records(db, project_id, "claims"),
                    "issues": research.list_records(db, project_id, "issues"),
                },
                ensure_ascii=False,
            ),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="workbench-progress.json"'},
        )

    @app.get("/api/workbench/v1/claims")
    @app.get("/api/workbench/v1/issues")
    async def research_api(request: Request):
        kind = request.url.path.rsplit("/", 1)[-1]
        if kind not in {"claims", "issues"}:
            raise service.Missing("研究台账不存在")
        return {"items": research.list_records(db, project_id, kind)}

    @app.post("/api/workbench/v1/claims")
    @app.post("/api/workbench/v1/issues")
    async def research_api_save(request: Request):
        kind = request.url.path.rsplit("/", 1)[-1]
        if kind not in {"claims", "issues"}:
            raise service.Missing("研究台账不存在")
        try:
            body = await request.json()
            if not isinstance(body, dict) or set(body) != {
                "id",
                "content",
                "expected_revision",
                "request_id",
                "actor",
            }:
                raise ValueError("invalid research request fields")
            return research.save(
                db,
                project_id,
                kind,
                body["id"],
                body["content"],
                body["expected_revision"],
                request_id=body["request_id"],
                actor=body["actor"],
            )
        except service.Conflict as exc:
            return JSONResponse({"detail": str(exc)}, status_code=409)
        except (ValueError, TypeError) as exc:
            return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.get("/predictions", response_class=HTMLResponse)
    async def prediction_page(request: Request):
        models = [
            index.get_artifact(db, a["id"])
            for a in index.list_artifacts(db, project_id, limit=500)["items"]
            if a["kind"] == "model"
        ]
        return render(
            request, "predictions", models=models, jobs=predictions.list_jobs(db, project_id)
        )

    @app.get("/api/workbench/v1/prediction-jobs")
    async def prediction_jobs():
        return {"items": predictions.list_jobs(db, project_id)}

    @app.get("/api/workbench/v1/prediction-jobs/{job_id}")
    async def prediction_job(job_id: str):
        return predictions.get(db, project_id, job_id)

    @app.post("/api/workbench/v1/prediction-jobs")
    async def enqueue_prediction_api(request: Request):
        try:
            data = await request.json()
            if not isinstance(data, dict) or set(data) != {
                "model_id",
                "version",
                "items",
                "task_id",
                "request_id",
                "actor",
            }:
                raise ValueError("invalid prediction request fields")
            return predictions.enqueue(
                db,
                project_id,
                data["model_id"],
                data["version"],
                data["items"],
                data["task_id"],
                request_id=data["request_id"],
                actor=data["actor"],
            )
        except service.Conflict as exc:
            return JSONResponse({"detail": str(exc)}, status_code=409)
        except (ValueError, TypeError) as exc:
            return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.post("/api/workbench/v1/prediction-jobs/{job_id}/{operation}")
    async def prediction_control(request: Request, job_id: str, operation: str):
        try:
            body = await request.json()
            keys = (
                {"request_id", "actor", "expected_revision"}
                if operation == "cancel"
                else {"request_id", "actor"}
            )
            if (
                operation not in {"cancel", "retry"}
                or not isinstance(body, dict)
                or set(body) != keys
            ):
                raise ValueError("invalid prediction control request")
            if operation == "cancel":
                return predictions.cancel(
                    db,
                    project_id,
                    job_id,
                    body["expected_revision"],
                    request_id=body["request_id"],
                    actor=body["actor"],
                )
            return predictions.retry(
                db, project_id, job_id, request_id=body["request_id"], actor=body["actor"]
            )
        except service.Conflict as exc:
            return JSONResponse({"detail": str(exc)}, status_code=409)
        except (ValueError, TypeError) as exc:
            return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.get("/model-evidence", response_class=HTMLResponse)
    async def model_evidence(request: Request):
        with transaction(db) as conn:
            ids = [
                row[0]
                for row in conn.execute(
                    "SELECT id FROM artifact WHERE project_id=? "
                    "AND (kind IN ('model','report') "
                    "OR id IN ('I5-model-card','I5-diagnostics')) ORDER BY id",
                    (project_id,),
                )
            ]
        records = [index.get_artifact(db, artifact_id) for artifact_id in ids]
        return render(
            request, "model_evidence", records=records, runs=model_runs.list_runs(db, project_id)
        )

    @app.get("/api/workbench/v1/model-runs")
    async def api_model_runs():
        return {"items": model_runs.list_runs(db, project_id)}

    @app.get("/api/workbench/v1/model-runs/{run_id}")
    async def api_model_run(run_id: str):
        try:
            return model_runs.get(db, project_id, run_id)
        except service.Missing as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.post("/api/workbench/v1/model-runs")
    async def api_save_model_run(request: Request):
        try:
            body = await request.json()
            if not isinstance(body, dict) or set(body) != {
                "id",
                "content",
                "expected_revision",
                "request_id",
                "actor",
            }:
                raise ValueError(
                    "request requires id, content, expected_revision, request_id and actor"
                )
            if type(body["expected_revision"]) is not int or body["expected_revision"] < 0:
                raise ValueError("invalid expected revision")
            return model_runs.save(
                db,
                project_id,
                body["id"],
                body["content"],
                body["expected_revision"],
                request_id=body["request_id"],
                actor=body["actor"],
            )
        except service.Missing as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404)
        except service.Conflict as exc:
            return JSONResponse({"detail": str(exc)}, status_code=409)
        except (ValueError, TypeError, KeyError) as exc:
            return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.get("/foundation", response_class=HTMLResponse)
    async def foundation_page(request: Request, kind: str = "sources"):
        try:
            rows = foundation.list_records(db, project_id, kind)
        except ValueError:
            return render(request, "message", status_code=404, message="未知数据类型")
        dictionary = foundation.field_dictionary(db, project_id) if kind == "fields" else []
        return render(request, "foundation", kind=kind, rows=rows, dictionary=dictionary)

    @app.post("/foundation/register", response_class=HTMLResponse)
    async def foundation_register(request: Request):
        form = await request.form()
        try:
            result = foundation.stage_record(
                db,
                project_id,
                str(form.get("kind", "")),
                str(form.get("content", "")),
                str(form.get("actor", "")),
            )
            return render(request, "foundation_preview", result=result)
        except ValueError as exc:
            return render(request, "message", status_code=422, message=str(exc))

    @app.get("/foundation/export")
    async def foundation_export():
        return Response(
            json.dumps(foundation.export_data(db, project_id), ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="foundation.json"'},
        )

    @app.get("/foundation/imports/{import_id}")
    async def foundation_report(import_id: str):
        try:
            result = foundation.import_report(db, project_id, import_id)
        except ValueError as exc:
            raise service.Missing(str(exc)) from exc
        return Response(
            json.dumps(result, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="import-report.json"'},
        )

    @app.post("/foundation/backup")
    async def foundation_backup(request: Request):
        return Response(
            backup.create_bundle(db, root),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="workbench-backup.zip"'},
        )

    @app.post("/foundation/restore/preview", response_class=HTMLResponse)
    async def foundation_restore_preview(request: Request):
        form = await request.form()
        try:
            upload = form.get("file")
            if not hasattr(upload, "read"):
                raise ValueError("请选择备份文件")
            content = await upload.read()
            result = backup.preview_bundle(content)
            restore_previews[result["sha256"]] = content
            return render(request, "foundation_restore", result=result)
        except (ValueError, KeyError, OSError, backup.zipfile.BadZipFile) as exc:
            return render(request, "message", status_code=422, message=str(exc))

    @app.post("/foundation/restore/apply", response_class=HTMLResponse)
    async def foundation_restore_apply(request: Request):
        form = await request.form()
        digest = str(form.get("sha256", ""))
        content = restore_previews.get(digest)
        if content is None:
            return render(request, "message", status_code=409, message="恢复预览已失效，请重新上传")
        result = backup.restore_bundle(
            content,
            root / "backups" / ("restored-" + uuid.uuid4().hex),
            digest,
        )
        return render(request, "message", message=f"恢复完成，副本目录：{result['path']}")

    @app.get("/foundation/samples", response_class=HTMLResponse)
    async def foundation_samples(request: Request, offset: int = 0):
        try:
            result = samples.list_samples(root / "data/catalog.sqlite", offset=offset)
        except (ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
            return render(request, "message", status_code=422, message=f"领域库读取失败：{exc}")
        return render(request, "foundation_samples", result=result)

    @app.post("/foundation/preview", response_class=HTMLResponse)
    async def foundation_preview(request: Request):
        form = await request.form()
        try:
            upload = form.get("file")
            if not hasattr(upload, "read"):
                raise ValueError("请选择导入文件")
            result = foundation.stage(
                db,
                project_id,
                str(form.get("format", "")),
                await upload.read(10 * 1024 * 1024 + 1),
                str(form.get("actor", "")),
            )
            return render(request, "foundation_preview", result=result)
        except ValueError as exc:
            return render(request, "message", status_code=422, message=str(exc))

    @app.post("/foundation/apply", response_class=HTMLResponse)
    async def foundation_apply(request: Request):
        form = await request.form()
        try:
            foundation.apply(
                db,
                project_id,
                str(form.get("id", "")),
                str(form.get("sha256", "")),
                conflict=str(form.get("conflict", "reject")),
            )
            return RedirectResponse("/foundation", status_code=303)
        except (ValueError, service.Conflict) as exc:
            return render(request, "message", status_code=409, message=str(exc))

    @app.get("/tasks", response_class=HTMLResponse)
    async def task_list(request: Request, status: str = "", stage: str = "", q: str = ""):
        rows = [
            t
            for t in tasks()
            if (not status or t["status"] == status)
            and (not stage or stage in t["stages"])
            and (not q or q.casefold() in (t["title"] + " " + t["id"]).casefold())
        ]
        return render(request, "tasks", tasks=rows, status=status, stage=stage, q=q, labels=LABELS)

    @app.get("/tasks/new", response_class=HTMLResponse)
    async def task_new(request: Request):
        return render(request, "task_form", task=None)

    @app.get("/tasks/{task_id}", response_class=HTMLResponse)
    async def task_detail(request: Request, task_id: str, node: str = ""):
        task = task_for(task_id)
        road = roadmap.snapshot(db, project_id)
        task_links = [link for link in road["links"] if link["task_id"] == task_id]
        return_node = next(
            (link["node_id"] for link in task_links if link["node_id"] == node), None
        )
        if not return_node:
            return_node = next(
                (link["node_id"] for link in task_links if link["role"] == "primary"), None
            )
        artifacts = []
        for row in index.list_artifacts(db, project_id, limit=500)["items"]:
            item = index.get_artifact(db, row["id"])
            for revision in item["revisions"]:
                if revision["status"] == "available":
                    artifacts.append({"id": row["id"], "version": revision["file_sha256"]})
        with transaction(db) as conn:
            related_decisions = [
                dict(r)
                for r in conn.execute(
                    "SELECT d.id,r.title FROM task_decision td "
                    "JOIN decision d ON d.id=td.decision_id JOIN decision_revision r "
                    "ON r.decision_id=d.id AND r.revision=d.revision WHERE td.task_id=?",
                    (task_id,),
                )
            ]
        return render(
            request,
            "task",
            task=task,
            all_tasks=tasks(),
            artifacts=artifacts,
            related_decisions=related_decisions,
            roadmap_return_node=return_node,
            related_runs=[
                run
                for run in model_runs.list_runs(db, project_id)
                if run["history"][0]["content"]["task_id"] == task_id
            ],
        )

    @app.get("/tasks/{task_id}/edit", response_class=HTMLResponse)
    async def task_edit(request: Request, task_id: str):
        return render(request, "task_form", task=task_for(task_id))

    @app.get("/artifacts", response_class=HTMLResponse)
    async def artifacts(request: Request):
        rows = index.list_artifacts(db, project_id, limit=500)
        return render(
            request,
            "artifacts",
            artifacts=[index.get_artifact(db, row["id"]) for row in rows["items"]],
        )

    @app.get("/artifacts/{artifact_id}", response_class=HTMLResponse)
    async def artifact_detail(
        request: Request, artifact_id: str, version: str = "", offset: int = 0
    ):
        artifact = artifact_for(artifact_id)
        preview, error = None, None
        if version:
            try:
                preview = index.preview(db, artifact_id, version, offset=offset, limit=30)
            except (ValueError, OSError) as exc:
                error = str(exc)
        return render(
            request,
            "artifact",
            artifact=artifact,
            preview=preview,
            error=error,
            version=version,
            offset=offset,
        )

    @app.get("/artifacts/{artifact_id}/download/{version}")
    async def artifact_download(artifact_id: str, version: str):
        artifact = artifact_for(artifact_id)
        for observation in artifact["observations"]:
            if observation["status"] != "available" or observation["file_sha256"] != version:
                continue
            try:
                info = adapters.inspect(
                    root, observation["path"], artifact["kind"], 64 * 1024 * 1024
                )
                raw = adapters.read_limited(
                    adapters.safe_path(root, observation["path"]), 64 * 1024 * 1024
                )
                import hashlib

                if info["file_sha256"] == version == hashlib.sha256(raw).hexdigest():
                    return Response(
                        raw,
                        media_type="application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{version}.bin"'},
                    )
            except (OSError, ValueError):
                continue
        return PlainTextResponse("文件已变化或不可用，请刷新索引", status_code=409)

    @app.get("/decisions", response_class=HTMLResponse)
    async def decision_list(request: Request):
        return render(request, "decisions", decisions=decisions.list_decisions(db, project_id))

    @app.get("/decisions/new", response_class=HTMLResponse)
    async def decision_new(request: Request):
        return render(request, "decision_form", decision=None)

    @app.get("/decisions/{decision_id}", response_class=HTMLResponse)
    async def decision_detail(request: Request, decision_id: str):
        return render(
            request,
            "decision",
            decision=decisions.get_decision(db, project_id, decision_id),
            all_tasks=tasks(),
        )

    @app.get("/decisions/{decision_id}/edit", response_class=HTMLResponse)
    async def decision_edit(request: Request, decision_id: str):
        return render(
            request, "decision_form", decision=decisions.get_decision(db, project_id, decision_id)
        )

    @app.get("/decisions/{decision_id}/export")
    async def decision_export(decision_id: str):
        decision = decisions.get_decision(db, project_id, decision_id)
        item = decision["history"][0]
        return PlainTextResponse(
            f"# {item['title']}\n\n## 背景\n{item['background']}\n\n"
            f"## 决定\n{item['conclusion']}\n\n## 理由\n{item['rationale']}\n\n"
            f"## 影响\n{item['impact']}\n\n## 来源\n{item['source']}\n",
            media_type="text/markdown",
        )

    @app.get("/documents", response_class=HTMLResponse)
    async def documents(request: Request):
        items = [
            index.get_artifact(db, r["id"])
            for r in index.list_artifacts(db, project_id, limit=500)["items"]
            if r["kind"] == "document"
        ]
        return render(request, "documents", artifacts=items)

    @app.get("/search", response_class=HTMLResponse)
    async def search(request: Request, q: str = ""):
        word = q.casefold().strip()
        return render(
            request,
            "search",
            q=q,
            runs=[
                run
                for run in model_runs.list_runs(db, project_id)
                if word
                and word in (run["id"] + " " + run["history"][0]["content"]["title"]).casefold()
            ],
            tasks=[t for t in tasks() if word and word in (t["id"] + " " + t["title"]).casefold()],
            artifacts=[
                a
                for a in index.list_artifacts(db, project_id, limit=500)["items"]
                if word and word in a["id"].casefold()
            ],
            decisions=[
                d
                for d in decisions.list_decisions(db, project_id)
                if word and word in (d["id"] + " " + d["title"]).casefold()
            ],
        )

    @app.post("/actions/{action}", response_class=HTMLResponse)
    async def action(request: Request, action: str):
        form = await request.form()
        data = {key: str(value) for key, value in form.items()}
        actor = data.get("actor", "").strip()
        rid = data.get("request_id", "")
        try:
            if not actor:
                raise ValueError("请填写操作人")
            if action == "roadmap-node":
                node_id = data.get("node_id", "").strip()
                if not data.get("parent_id") and int(data.get("revision", "0")) == 0:
                    raise ValueError("新分支必须指定父节点")
                research_nodes.save_research_node(
                    db,
                    project_id,
                    node_id,
                    {
                        "stage": data.get("stage"),
                        "parent_id": data.get("parent_id") or None,
                        "sort_order": int(data.get("sort_order", "0")),
                        "source_path": data.get("source_path"),
                        "source_section": data.get("source_section"),
                        "source_sha256": data.get("source_sha256"),
                        "active": int(data.get("active", "1")),
                    },
                    int(data.get("revision", "0")),
                    data.get("reason", ""),
                    request_id=rid,
                    actor=actor,
                )
                return RedirectResponse("/roadmap?view=tree", status_code=303)
            if action == "roadmap-link":
                research_nodes.save_task_node_link(
                    db,
                    project_id,
                    data.get("link_id", ""),
                    {
                        "task_id": data.get("task_id"),
                        "node_id": data.get("node_id"),
                        "role": data.get("role"),
                        "active": int(data.get("active", "1")),
                    },
                    int(data.get("revision", "0")),
                    data.get("reason", ""),
                    request_id=rid,
                    actor=actor,
                )
                return RedirectResponse("/roadmap?view=tree", status_code=303)
            if action == "roadmap-move-primary":
                research_nodes.move_primary_to_reference(
                    db,
                    project_id,
                    data.get("primary_id", ""),
                    int(data.get("primary_revision", "0")),
                    data.get("reference_id", ""),
                    int(data.get("reference_revision", "0")),
                    data.get("reason", ""),
                    request_id=rid,
                    actor=actor,
                )
                return RedirectResponse("/roadmap?view=tree", status_code=303)
            if action == "enqueue-prediction":
                model_id, version = data.get("model", "").split("|", 1)
                predictions.enqueue(
                    db,
                    project_id,
                    model_id,
                    version,
                    json.loads(data.get("items", "")),
                    data.get("task_id") or None,
                    request_id=rid,
                    actor=actor,
                )
                return RedirectResponse("/predictions", status_code=303)
            if action in {"cancel-prediction", "retry-prediction"}:
                if action == "cancel-prediction":
                    predictions.cancel(
                        db,
                        project_id,
                        data["job_id"],
                        int(data["revision"]),
                        request_id=rid,
                        actor=actor,
                    )
                else:
                    predictions.retry(db, project_id, data["job_id"], request_id=rid, actor=actor)
                return RedirectResponse("/predictions", status_code=303)
            if action == "save-research":
                research.save(
                    db,
                    project_id,
                    data.get("kind", "claims"),
                    data.get("id", ""),
                    json.loads(data.get("content", "")),
                    int(data.get("revision", "0")),
                    request_id=rid,
                    actor=actor,
                )
                return RedirectResponse(
                    "/research?kind=" + data.get("kind", "claims"), status_code=303
                )
            if action == "save-model-run":
                model_runs.save(
                    db,
                    project_id,
                    data.get("run_id", ""),
                    json.loads(data.get("content", "")),
                    int(data.get("revision", "0")),
                    request_id=rid,
                    actor=actor,
                )
                return RedirectResponse("/model-evidence", status_code=303)
            if action == "register-r1-run":
                model_runs.register_r1(
                    db, project_id, data.get("task_id", ""), request_id=rid, actor=actor
                )
                return RedirectResponse("/model-evidence", status_code=303)
            if action == "register-historical-r1":
                index.register_historical_r1(db, project_id, request_id=rid, actor=actor)
                return RedirectResponse("/model-evidence", status_code=303)
            if action in {"create-task", "edit-task"}:
                criterion_lines = [
                    line.strip() for line in data.get("criteria", "").splitlines() if line.strip()
                ]
                criteria = []
                for line in criterion_lines:
                    parts = line.split("|", 1)
                    if len(parts) != 2 or not all(p.strip() for p in parts):
                        raise ValueError("每条检查项请按‘编号 | 内容’填写")
                    description = parts[1].strip()
                    optional = description.endswith(" | optional")
                    if optional:
                        description = description.removesuffix(" | optional").strip()
                    criteria.append(
                        {
                            "id": parts[0].strip(),
                            "description": description,
                            "required": not optional,
                        }
                    )
                stages = [s.strip() for s in data.get("stages", "").split(",") if s.strip()]
                fields = {
                    "title": data.get("title", ""),
                    "goal": data.get("goal", ""),
                    "deliverables": [
                        x.strip() for x in data.get("deliverables", "").splitlines() if x.strip()
                    ],
                    "criteria": criteria,
                    "milestone": data.get("milestone") or None,
                    "stages": stages,
                    "primary_stage": data.get("primary_stage") or None,
                    "priority": data.get("priority", "normal"),
                    "owner": data.get("owner") or None,
                    "planned_date": data.get("planned_date") or None,
                }
                task_id = data.get("task_id", "").strip()
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", task_id):
                    raise ValueError("任务编号仅支持字母、数字、点、下划线和连字符")
                if fields["planned_date"]:
                    datetime.strptime(fields["planned_date"], "%Y-%m-%d")
                if action == "create-task":
                    service.create_task(
                        db,
                        {**fields, "id": task_id, "project_id": project_id},
                        request_id=rid,
                        actor=actor,
                    )
                else:
                    current = task_for(task_id)
                    old_criteria = [
                        {
                            "id": c["criterion_id"],
                            "description": c["description"],
                            "required": bool(c["required"]),
                        }
                        for c in current["criteria"]
                    ]
                    if criteria == old_criteria:
                        fields.pop("criteria")
                    if (
                        fields.get("goal") == current["goal"]
                        and fields.get("deliverables") == current["deliverables"]
                    ):
                        fields.pop("goal")
                        fields.pop("deliverables")
                    service.update_task(
                        db, task_id, int(data["revision"]), fields, request_id=rid, actor=actor
                    )
                destination = "/tasks/" + task_id
            elif action == "transition":
                task_id = data["task_id"]
                task_for(task_id)
                service.transition(
                    db,
                    task_id,
                    int(data["revision"]),
                    data["target"],
                    request_id=rid,
                    actor=actor,
                    reason=data.get("reason") or None,
                    recovery_condition=data.get("recovery_condition") or None,
                    recovery_date=data.get("recovery_date") or None,
                    resolution=data.get("resolution") or None,
                )
                destination = "/tasks/" + task_id
            elif action in {"add-dependency", "remove-dependency"}:
                task_id, dep = data["task_id"], data["dependency"]
                task_for(task_id)
                task_for(dep)
                fn = (
                    service.add_dependency
                    if action == "add-dependency"
                    else service.remove_dependency
                )
                fn(db, task_id, dep, int(data["revision"]), request_id=rid, actor=actor)
                destination = "/tasks/" + task_id
            elif action == "submit-review":
                task = task_for(data["task_id"])
                results = []
                for criterion in task["criteria"]:
                    criterion_id = criterion["criterion_id"]
                    answer = data.get("result-" + criterion_id, "")
                    if not answer:
                        continue
                    result = {
                        "criterion_id": criterion_id,
                        "passed": answer == "pass",
                        "explanation": data.get("explanation-" + criterion_id) or None,
                    }
                    evidence = data.get("evidence-" + criterion_id, "")
                    if evidence:
                        result["evidence_id"], result["evidence_version"] = evidence.split("|", 1)
                    results.append(result)
                service.submit_review(
                    db,
                    task["id"],
                    int(data["revision"]),
                    results,
                    data.get("conclusion", ""),
                    request_id=rid,
                    actor=actor,
                )
                destination = "/tasks/" + task["id"]
            elif action == "accept-review":
                task_for(data["task_id"])
                service.accept_review(
                    db,
                    data["task_id"],
                    int(data["revision"]),
                    data.get("conclusion", ""),
                    request_id=rid,
                    actor=actor,
                )
                destination = "/tasks/" + data["task_id"]
            elif action == "focus":
                decisions.set_focus(
                    db, project_id, data.get("task_id"), request_id=rid, actor=actor
                )
                destination = "/"
            elif action == "register":
                if not re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", data.get("artifact_id", "")
                ):
                    raise ValueError("成果编号仅支持字母、数字、点、下划线和连字符")
                index.register(
                    db,
                    project_id,
                    data.get("artifact_id", ""),
                    data.get("kind", ""),
                    data.get("path", ""),
                    request_id=rid,
                    actor=actor,
                )
                destination = "/artifacts"
            elif action == "scan":
                index.scan(db, project_id)
                destination = "/artifacts"
            elif action == "save-decision":
                fields = {
                    key: data.get(key, "")
                    for key in (
                        "title",
                        "background",
                        "conclusion",
                        "rationale",
                        "impact",
                        "source",
                        "supersedes",
                    )
                }
                decision_id = data.get("decision_id", "").strip()
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", decision_id):
                    raise ValueError("决策编号仅支持字母、数字、点、下划线和连字符")
                decisions.save_decision(
                    db,
                    project_id,
                    decision_id,
                    fields,
                    int(data.get("revision", "0")),
                    request_id=rid,
                    actor=actor,
                )
                destination = "/decisions/" + decision_id
            elif action == "link-decision":
                decisions.link_task(
                    db,
                    project_id,
                    data["decision_id"],
                    data["task_id"],
                    data.get("impact", ""),
                    request_id=rid,
                    actor=actor,
                )
                destination = "/decisions/" + data["decision_id"]
            else:
                raise service.Missing("操作不存在")
            return RedirectResponse(destination, status_code=303)
        except (ValueError, OSError, sqlite3.Error, KeyError) as exc:
            status = (
                404
                if isinstance(exc, service.Missing)
                else 409
                if isinstance(exc, (service.Conflict, sqlite3.OperationalError))
                else 422
            )
            return render(
                request, "error", status_code=status, error=str(exc), fields=data, action=action
            )

    return app
