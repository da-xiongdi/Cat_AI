"""Auditable staging of offline workbench backups and prototype CSV files."""

import hashlib
import json
import math
import uuid
from pathlib import Path

from catalyst_ai.storage.workbench import now, transaction
from catalyst_ai.workbench.csv_preview import preview_csv
from catalyst_ai.workbench.fields import describe_fields, migrate_fields, validate_fields
from catalyst_ai.workbench.service import Conflict

KINDS = (
    "sources",
    "records",
    "fields",
    "governance",
    "models",
    "screenings",
    "candidates",
    "batches",
    "experiments",
    "roadmap",
    "issues",
)


def _json(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _finite(value):
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(_finite(item) for item in value.values())
    if isinstance(value, list):
        return all(_finite(item) for item in value)
    return True


def inspect_json(raw: bytes) -> dict:
    """Validate the full prototype envelope and preserve all original objects."""
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"无效 JSON：{exc}") from exc
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("不支持的原型版本")
    if not _finite(data):
        raise ValueError("JSON 包含非有限数值")
    if not isinstance(data.get("settings"), dict) or str(data["settings"].get("capacity")) not in (
        "4",
        "5",
        "6",
    ):
        raise ValueError("容量必须为 4、5 或 6")
    errors = []
    ids = {}
    for kind in KINDS:
        items = data.get(kind)
        if not isinstance(items, list):
            raise ValueError(f"{kind} 必须是数组")
        ids[kind] = set()
        for i, item in enumerate(items):
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("id"), str)
                or not item["id"].strip()
            ):
                errors.append(f"{kind}[{i}] 缺少有效 ID")
                continue
            if item["id"] in ids[kind]:
                errors.append(f"{kind} 重复 ID：{item['id']}")
            ids[kind].add(item["id"])
    for kind in KINDS:
        for item in data[kind]:
            if not isinstance(item, dict):
                continue
            for key, target in {
                "sourceId": "sources",
                "evidence": "sources",
                "modelId": "models",
                "screeningId": "screenings",
                "candidateId": "candidates",
                "batchId": "batches",
            }.items():
                ref = item.get(key)
                if ref and (not isinstance(ref, str) or ref not in ids[target]):
                    errors.append(f"{kind}/{item.get('id')} 的 {key} 未找到：{ref}")
            if kind == "batches":
                refs = item.get("candidateIds", [])
                if not isinstance(refs, list) or any(
                    not isinstance(x, str) or x not in ids["candidates"] for x in refs
                ):
                    errors.append(f"batches/{item.get('id')} 候选关联无效")
                elif len(refs) > int(data["settings"]["capacity"]):
                    errors.append(f"batches/{item.get('id')} 超出容量")
            if kind in ("records", "candidates", "experiments"):
                for field in (
                    "calcination",
                    "temp",
                    "pressure",
                    "ghsv",
                    "conv",
                    "sel",
                    "sty",
                    "predConv",
                    "predSel",
                    "predSty",
                    "replicates",
                ):
                    value = item.get(field)
                    if value is None or value == "":
                        continue
                    try:
                        number = float(value)
                        if isinstance(value, bool) or not math.isfinite(number):
                            raise ValueError
                        if (
                            field in ("conv", "sel", "predConv", "predSel")
                            and not 0 <= number <= 100
                        ):
                            raise ValueError
                        if field == "replicates" and (number < 1 or not number.is_integer()):
                            raise ValueError
                    except (TypeError, ValueError):
                        errors.append(f"{kind}/{item.get('id')} 的 {field} 数值无效")
    warnings = migrate_fields(data["fields"], data["records"])
    errors.extend(validate_fields(data["fields"], data["records"]))
    return {"data": data, "errors": errors, "warnings": warnings}


def stage(db: Path, project_id: str, fmt: str, raw: bytes, actor: str) -> dict:
    if fmt not in ("json", "csv") or not actor.strip():
        raise ValueError("需要有效格式和操作人")
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError("导入文件超过 10 MiB")
    digest = hashlib.sha256(raw).hexdigest()
    if fmt == "json":
        result = inspect_json(raw)
        report = {
            "errors": result["errors"],
            "warnings": result["warnings"],
            "counts": {k: len(result["data"][k]) for k in KINDS},
        }
    else:
        result = preview_csv(raw)
        report = {
            "errors": [
                f"第 {r['line']} 行：{e['field']} {e['message']}"
                for r in result["rows"]
                for e in r["errors"]
            ],
            "rows": result["rows"],
            "field_mapping": result["field_mapping"],
        }
    with transaction(db) as conn:
        report["base_versions"] = {
            f"{row['kind']}/{row['legacy_id']}": row["revision"]
            for row in conn.execute(
                "SELECT kind,legacy_id,MAX(revision) revision FROM foundation_record "
                "WHERE project_id=? GROUP BY kind,legacy_id",
                (project_id,),
            )
        }
        if fmt == "json":
            changes = []
            for kind in KINDS:
                for item in result["data"][kind]:
                    if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                        continue
                    previous = conn.execute(
                        "SELECT revision,content FROM foundation_record WHERE project_id=? "
                        "AND kind=? AND legacy_id=? ORDER BY revision DESC LIMIT 1",
                        (project_id, kind, item["id"]),
                    ).fetchone()
                    if previous and previous["content"] != _json(item):
                        changes.append(
                            {
                                "kind": kind,
                                "id": item["id"],
                                "revision": previous["revision"],
                                "previous": json.loads(previous["content"]),
                                "incoming": item,
                            }
                        )
            report["changes"] = changes
        if fmt == "csv":
            source_ids = {
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT legacy_id FROM foundation_record "
                    "WHERE project_id=? AND kind='sources'",
                    (project_id,),
                )
            }
            for row in result["rows"]:
                source_id = row["raw"]["sourceId"].strip()
                if source_id and source_id not in source_ids:
                    report["errors"].append(f"第 {row['line']} 行：来源 {source_id} 不存在")
        existing = conn.execute(
            "SELECT id,status,report FROM foundation_import "
            "WHERE project_id=? AND format=? AND sha256=?",
            (project_id, fmt, digest),
        ).fetchone()
        if existing:
            if existing["status"] == "staged":
                conn.execute(
                    "UPDATE foundation_import SET report=? WHERE id=?",
                    (_json(report), existing["id"]),
                )
                return {
                    "id": existing["id"],
                    "sha256": digest,
                    "status": "staged",
                    "report": report,
                }
            return {
                "id": existing["id"],
                "sha256": digest,
                "status": existing["status"],
                "report": json.loads(existing["report"]),
            }
        import_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO foundation_import VALUES(?,?,?,?,?,?,?,?,?)",
            (
                import_id,
                project_id,
                fmt,
                digest,
                now(),
                actor.strip(),
                raw,
                _json(report),
                "staged",
            ),
        )
    return {"id": import_id, "sha256": digest, "status": "staged", "report": report}


def apply(
    db: Path, project_id: str, import_id: str, expected_sha256: str, *, conflict: str = "reject"
) -> dict:
    """Publish staged objects atomically, requiring explicit conflict disposition."""
    if conflict not in ("reject", "keep", "revise"):
        raise ValueError("无效冲突处置")
    with transaction(db) as conn:
        batch = conn.execute(
            "SELECT * FROM foundation_import WHERE id=? AND project_id=?", (import_id, project_id)
        ).fetchone()
        if batch is None:
            raise ValueError("导入批次不存在")
        if batch["sha256"] != expected_sha256:
            raise Conflict("预览哈希不匹配")
        if hashlib.sha256(batch["original"]).hexdigest() != expected_sha256:
            raise Conflict("原始文件哈希已变化")
        if batch["status"] == "applied":
            return {"id": import_id, "status": "applied"}
        if json.loads(batch["report"])["errors"]:
            raise Conflict("预览存在错误，不能发布")
        if batch["format"] == "json":
            data = inspect_json(batch["original"])["data"]
            items = [(kind, item["id"], item) for kind in KINDS for item in data[kind]]
            items.append(("settings", "settings", data["settings"]))
        else:
            preview = preview_csv(batch["original"])
            source_ids = {
                row[0]
                for row in conn.execute(
                    "SELECT legacy_id FROM foundation_record WHERE project_id=? AND kind='sources'",
                    (project_id,),
                )
            }
            if any(row["raw"]["sourceId"].strip() not in source_ids for row in preview["rows"]):
                raise Conflict("来源已变化，请重新预览")
            items = [
                (
                    "records",
                    row["raw"]["id"].strip() or f"csv-{import_id}-{n}",
                    {"raw": row["raw"], "status": "待治理", "line": row["line"]},
                )
                for n, row in enumerate(preview["rows"], 1)
            ]
        for kind, legacy_id, obj in items:
            content = _json(obj)
            old = conn.execute(
                "SELECT revision,content FROM foundation_record WHERE project_id=? "
                "AND kind=? AND legacy_id=? ORDER BY revision DESC LIMIT 1",
                (project_id, kind, legacy_id),
            ).fetchone()
            if old and old["content"] == content:
                continue
            baseline = json.loads(batch["report"]).get("base_versions", {})
            if (old["revision"] if old else 0) != baseline.get(f"{kind}/{legacy_id}", 0):
                raise Conflict(f"{kind}/{legacy_id} 预览已过期，请重新上传预览")
            if old and conflict == "reject":
                raise Conflict(f"{kind}/{legacy_id} 内容发生变化，请选择处置方式")
            if old and conflict == "keep":
                continue
            conn.execute(
                "INSERT INTO foundation_record VALUES(?,?,?,?,?,?,?)",
                (
                    project_id,
                    kind,
                    legacy_id,
                    old["revision"] + 1 if old else 1,
                    content,
                    import_id,
                    now(),
                ),
            )
        conn.execute("UPDATE foundation_import SET status='applied' WHERE id=?", (import_id,))
    return {"id": import_id, "status": "applied"}


def list_records(db: Path, project_id: str, kind: str) -> list[dict]:
    if kind not in (*KINDS, "settings"):
        raise ValueError("未知数据类型")
    with transaction(db) as conn:
        rows = conn.execute(
            "SELECT r.* FROM foundation_record r WHERE project_id=? AND kind=? "
            "AND revision=(SELECT MAX(x.revision) FROM foundation_record x "
            "WHERE x.project_id=r.project_id AND x.kind=r.kind "
            "AND x.legacy_id=r.legacy_id) ORDER BY legacy_id",
            (project_id, kind),
        ).fetchall()
    return [{**dict(row), "content": json.loads(row["content"])} for row in rows]


def field_dictionary(db: Path, project_id: str) -> list[dict]:
    return describe_fields([row["content"] for row in list_records(db, project_id, "fields")])


def export_data(db: Path, project_id: str) -> dict:
    """Build a complete current envelope in one SQLite snapshot."""
    with transaction(db) as conn:
        rows = conn.execute(
            "SELECT r.kind,r.content FROM foundation_record r WHERE project_id=? "
            "AND revision=(SELECT MAX(x.revision) FROM foundation_record x "
            "WHERE x.project_id=r.project_id AND x.kind=r.kind AND x.legacy_id=r.legacy_id) "
            "ORDER BY kind,legacy_id",
            (project_id,),
        ).fetchall()
    data = {kind: [] for kind in KINDS}
    data.update(version=1, settings={"capacity": 4})
    for row in rows:
        if row["kind"] == "settings":
            data["settings"] = json.loads(row["content"])
        elif row["kind"] in KINDS:
            data[row["kind"]].append(json.loads(row["content"]))
    return data


def stage_record(db: Path, project_id: str, kind: str, content: str, actor: str) -> dict:
    if kind not in ("sources", "fields", "governance"):
        raise ValueError("此类型暂不支持登记")
    obj = json.loads(content)
    if not isinstance(obj, dict) or not isinstance(obj.get("id"), str):
        raise ValueError("登记内容需要稳定 ID")
    if kind == "sources" and not obj.get("title"):
        raise ValueError("来源需要 title")
    if kind == "governance" and not all(
        obj.get(key) for key in ("name", "inputs", "rule_version", "owner")
    ):
        raise ValueError("治理工作包需要 name、inputs、rule_version 和 owner")
    if kind == "fields" and not all(obj.get(key) for key in ("data_type", "version")):
        raise ValueError("新增或修订字段需要 data_type 和 version")
    reviews = obj.get("reviews", [])
    if not isinstance(reviews, list) or any(
        not isinstance(review, dict)
        or not all(review.get(key) for key in ("scope", "actor", "conclusion", "evidence_version"))
        for review in reviews
    ):
        raise ValueError("核验记录需要 scope、actor、conclusion 和 evidence_version")
    data = export_data(db, project_id)
    data[kind] = [item for item in data[kind] if item["id"] != obj["id"]] + [obj]
    return stage(db, project_id, "json", _json(data).encode("utf-8"), actor)


def import_report(db: Path, project_id: str, import_id: str) -> dict:
    with transaction(db) as conn:
        row = conn.execute(
            "SELECT id,sha256,status,report FROM foundation_import WHERE id=? AND project_id=?",
            (import_id, project_id),
        ).fetchone()
    if row is None:
        raise ValueError("导入批次不存在")
    return {**dict(row), "report": json.loads(row["report"])}
