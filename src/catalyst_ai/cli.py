import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from catalyst_ai import __version__
from catalyst_ai.config import load_settings
from catalyst_ai.datasets.eligibility import build_target_eligibility, freeze_qualified_snapshot
from catalyst_ai.datasets.split import build_paper_split, load_json
from catalyst_ai.features.design import build_feature_table
from catalyst_ai.ingest import ingest
from catalyst_ai.reporting.evidence import summary, write_json, write_new
from catalyst_ai.review import review_record
from catalyst_ai.revision import revise
from catalyst_ai.schemas.domain import ExperimentBatch
from catalyst_ai.storage.db import transaction
from catalyst_ai.storage.models import CuratedRow, ImportRunRow, StagedRow
from catalyst_ai.storage.snapshots import build_verified_snapshot


def make_parser():
    parser = argparse.ArgumentParser(prog="catalyst-ai", description="CO₂催化剂数据契约与治理CLI")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", type=Path, help="YAML配置；相对路径以工作目录为准")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="幂等初始化目录/SQLite，不生成业务数据")
    commands.add_parser("status", help="报告数据库数量及未实现范围")
    ingest_cmd = commands.add_parser("ingest", help="CSV/JSON导入、治理、来源追踪")
    ingest_cmd.add_argument("--input", type=Path, required=True)
    ingest_cmd.add_argument("--source", choices=["literature", "internal"])
    ingest_cmd.add_argument(
        "--adapter", choices=["themecat-v1", "themecat-v2"], help="TheMeCat CSV adapter version"
    )
    ingest_cmd.add_argument(
        "--dry-run", action="store_true", help="只读：stdout输出报告，无文件写入"
    )
    ingest_cmd.add_argument("--report", type=Path, help="真实导入时另选报告JSON路径，禁止覆盖")
    validate = commands.add_parser("validate", help="检查数据库完整性并输出某次导入质量报告")
    validate.add_argument("--run-id", help="默认最近一次导入")
    validate.add_argument("--report", type=Path)
    review = commands.add_parser("review", help="记录人工已完成的核验；不会替代人工检查")
    review.add_argument("--record-id", required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--decision", choices=["verified", "rejected"], required=True)
    review.add_argument("--evidence", required=True)
    review.add_argument("--acknowledge-warnings", action="store_true")
    revision = commands.add_parser("revise", help="基于父记录及证据创建修订并重新治理")
    revision.add_argument("--parent-record-id", required=True)
    revision.add_argument("--expected-parent-sha256", required=True)
    revision.add_argument(
        "--patch", type=Path, required=True, help="UTF-8 JSON对象，顶层字段完整替换"
    )
    revision.add_argument(
        "--base-adapter", choices=["themecat-v2"], help="从原始TheMeCat v1行重建v2语义基线"
    )
    revision.add_argument("--reason", required=True)
    revision.add_argument("--operator", required=True)
    revision.add_argument("--evidence", required=True)
    revision.add_argument("--report", type=Path, help="可选的新JSON报告路径")
    dataset = commands.add_parser("dataset", help="目标资格检查与人工核验数据快照")
    dataset_commands = dataset.add_subparsers(dest="dataset_command", required=True)
    build = dataset_commands.add_parser("build")
    build.add_argument("--target", required=True, help="已录入的指标名，不派生目标")
    build.add_argument("--record-id", action="append", dest="record_ids")
    build.add_argument("--output", type=Path)
    build.add_argument(
        "--demo",
        action="store_true",
        help="仅验证synthetic_demo软件流程，产物禁止科研训练，单独保存",
    )
    qualify = dataset_commands.add_parser("qualify", help="显式筛选目标样本，报告排除原因")
    qualify.add_argument("--target", required=True)
    qualify.add_argument("--target-definition", required=True, help="精确匹配指标定义，不猜测口径")
    qualify.add_argument("--target-unit", required=True, help="精确匹配标准单位")
    qualify.add_argument("--record-id", action="append", dest="record_ids", required=True)
    qualify.add_argument("--demo", action="store_true", help="仅synthetic_demo软件验证")
    qualify.add_argument(
        "--accept-themecat",
        action="store_true",
        help="接受指定TheMeCat原件作为来源证据，非逐行核验",
    )
    qualify.add_argument("--report", type=Path, help="可选JSON资格清单路径，拒绝覆盖")
    qualify.add_argument("--freeze", action="store_true", help="复核后冻结合格记录并返回关联")
    split = dataset_commands.add_parser("split", help="按规范DOI进行论文分组划分")
    split.add_argument("--snapshot", type=Path, required=True)
    split.add_argument("--qualification", type=Path, required=True)
    split.add_argument("--seed", type=int, default=42)
    split.add_argument("--report", type=Path, required=True)
    features = dataset_commands.add_parser("features", help="??????????????")
    features.add_argument("--snapshot", type=Path, required=True)
    features.add_argument("--qualification", type=Path, required=True)
    features.add_argument("--split", type=Path, required=True)
    features.add_argument("--report", type=Path, required=True)
    batch = commands.add_parser("batch", help="仅批次容量契约校验，无推荐算法")
    check = batch.add_subparsers(dest="batch_command", required=True).add_parser("check")
    check.add_argument("--capacity", type=int)
    check.add_argument("--candidate-id", action="append", default=[])
    return parser


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def execute(args, settings):
    if args.command == "init":
        with transaction(settings.database, initialize=True):
            pass
        for directory in ["raw", "staged", "curated", "snapshots", "examples"]:
            (settings.data_dir / directory).mkdir(parents=True, exist_ok=True)
        settings.report_dir.mkdir(parents=True, exist_ok=True)
        emit({"database": str(settings.database), "business_records_created": 0})
    elif args.command == "status":
        status = {
            "version": __version__,
            "scope": "Task A/B + I1 target eligibility",
            "database_exists": settings.database.exists(),
            "models": "未实现",
            "optimization": "未实现",
            "scientific_results": "无",
            "batch_capacity": settings.batch_capacity,
        }
        if settings.database.exists():
            with transaction(settings.database) as session:
                status["counts"] = {
                    cls.__tablename__: session.scalar(select(func.count()).select_from(cls))
                    for cls in [ImportRunRow, StagedRow, CuratedRow]
                }
                status["verified_research"] = session.scalar(
                    select(func.count())
                    .select_from(CuratedRow)
                    .where(
                        CuratedRow.dataset_kind == "research",
                        CuratedRow.review_status == "verified",
                    )
                )
        emit(status)
    elif args.command == "ingest":
        report = ingest(
            args.input,
            settings,
            dry_run=args.dry_run,
            source_kind=args.source,
            report_path=args.report,
            adapter=args.adapter,
        )
        print(summary(report), file=sys.stderr, end="")
        emit(report)
        return 2 if report["counts"]["staged"] or report["counts"]["duplicate"] else 0
    elif args.command == "validate":
        if args.report and args.report.suffix.lower() != ".json":
            raise ValueError("--report必须使用.json后缀")
        if args.report and (args.report.exists() or args.report.with_suffix(".txt").exists()):
            raise ValueError("报告路径已存在，拒绝覆盖")
        if not settings.database.exists():
            raise ValueError("数据库不存在")
        with sqlite3.connect(
            f"file:{settings.database.resolve().as_posix()}?mode=ro", uri=True
        ) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("SQLite完整性检查失败")
            if db.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("SQLite外键检查失败")
        with transaction(settings.database) as session:
            run = (
                session.get(ImportRunRow, args.run_id)
                if args.run_id
                else session.scalar(
                    select(ImportRunRow).order_by(ImportRunRow.created_at.desc()).limit(1)
                )
            )
            if run is None:
                raise ValueError("未找到导入运行")
            report = run.report
            raw_path = Path(report["raw_path"])
            if (
                not raw_path.exists()
                or hashlib.sha256(raw_path.read_bytes()).hexdigest() != run.input_sha256
            ):
                raise ValueError("原始文件丢失或哈希不一致")
        if args.report:
            write_json(args.report, report)
            write_new(args.report.with_suffix(".txt"), summary(report).encode("utf-8"))
        print(summary(report), file=sys.stderr, end="")
        emit(report)
        return 2 if report["counts"]["staged"] or report["counts"]["duplicate"] else 0
    elif args.command == "revise":
        if args.report and (args.report.suffix.lower() != ".json" or args.report.exists()):
            raise ValueError("报告须使用新的.json路径，拒绝覆盖")
        report = revise(
            settings,
            args.parent_record_id,
            patch=json.loads(args.patch.read_text(encoding="utf-8-sig")),
            expected_parent_sha256=args.expected_parent_sha256,
            reason=args.reason,
            operator=args.operator,
            evidence=args.evidence,
            base_adapter=args.base_adapter,
        )
        if args.report:
            write_json(args.report, report)
        emit(report)
        return 2 if report["counts"]["staged"] else 0
    elif args.command == "review":
        emit(
            review_record(
                settings,
                args.record_id,
                reviewer=args.reviewer,
                decision=args.decision,
                evidence=args.evidence,
                acknowledge_warnings=args.acknowledge_warnings,
            )
        )
    elif args.command == "dataset" and args.dataset_command == "features":
        if args.report.suffix.lower() != ".json" or args.report.exists():
            raise ValueError("????????.json???????")
        result = build_feature_table(
            load_json(args.snapshot), load_json(args.qualification), load_json(args.split)
        )
        write_json(args.report, result)
        emit(
            {
                "feature_table_id": result["feature_table_id"],
                "path": str(args.report),
                "record_count": len(result["content"]["rows"]),
            }
        )
    elif args.command == "dataset" and args.dataset_command == "split":
        if args.report.suffix.lower() != ".json" or args.report.exists():
            raise ValueError("分组清单须使用新的.json路径，拒绝覆盖")
        result = build_paper_split(
            load_json(args.snapshot), load_json(args.qualification), seed=args.seed
        )
        write_json(args.report, result)
        emit(result)
    elif args.command == "dataset" and args.dataset_command == "qualify":
        if args.report and (args.report.suffix.lower() != ".json" or args.report.exists()):
            raise ValueError("资格报告须使用新的.json路径，拒绝覆盖")
        result = build_target_eligibility(
            settings,
            record_ids=args.record_ids,
            target=args.target,
            target_definition=args.target_definition,
            target_unit=args.target_unit,
            demo=args.demo,
            source_acceptance="themecat-v1-published-dataset" if args.accept_themecat else None,
        )
        content = result["content"]
        if args.freeze and content["status"] == "ready":
            result = freeze_qualified_snapshot(settings, result)
        if args.report:
            write_json(args.report, result)
        emit(result)
        if content["status"] == "blocked" or (args.freeze and content["status"] == "empty"):
            return 1
        return 2 if content["counts"]["excluded_records"] else 0
    elif args.command == "dataset":
        emit(
            build_verified_snapshot(
                settings,
                target=args.target,
                record_ids=args.record_ids,
                output=args.output,
                demo=args.demo,
            )
        )
    elif args.command == "batch":
        emit(
            ExperimentBatch(
                capacity=args.capacity if args.capacity is not None else settings.batch_capacity,
                candidate_ids=args.candidate_id,
            ).model_dump()
        )
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = make_parser().parse_args(argv)
    try:
        return execute(args, load_settings(args.config))
    except (ValueError, OSError, ValidationError, SQLAlchemyError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
