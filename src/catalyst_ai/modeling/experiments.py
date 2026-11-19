"""R1 fixed-parameter DOI-grouped OOF comparison.

The returned fitted objects are in-memory development artifacts, not prediction packages.
"""

import hashlib
import importlib.metadata
import platform
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from catalyst_ai.datasets.split import normalize_doi
from catalyst_ai.features.design import composition
from catalyst_ai.features.pipeline import R1Features, select_inputs
from catalyst_ai.modeling.baseline import metrics, target_value
from catalyst_ai.reporting.evidence import digest, write_json

MODEL_ORDER = ("dummy", "extra_trees", "ridge")
FEATURE_SETS = ("F_cond", "F_base")


def _model(name):
    if name == "dummy":
        return DummyRegressor(strategy="mean")
    if name == "ridge":
        return make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    if name == "extra_trees":
        return ExtraTreesRegressor(n_estimators=100, min_samples_leaf=2, random_state=42, n_jobs=1)
    raise ValueError("unknown model")


def _predict(features, model, records, indices):
    outputs = [features.transform_one(records[i]["payload"], diagnostic=True) for i in indices]
    values = np.asarray([item["values"] for item in outputs], dtype=float)
    predictions = model.predict(values)
    if not np.isfinite(predictions).all():
        failed = [
            records[i]["record_id"]
            for i, value in zip(indices, predictions, strict=True)
            if not np.isfinite(value)
        ]
        raise ValueError(f"non-finite model output; metrics cannot be computed; records: {failed}")
    for item, value in zip(outputs, predictions, strict=True):
        item.pop("values")
        item["raw_prediction"] = float(value)
        if not 0 <= value <= 100:
            item["status"] = (
                item["status"] + "+output_out_of_range"
                if item["status"] != "ok"
                else "output_out_of_range"
            )
    return outputs


def _score(rows):
    if not rows:
        raise ValueError("empty evaluation set")
    by_doi = defaultdict(list)
    for row in rows:
        by_doi[row["doi"]].append(abs(row["observed"] - row["raw_prediction"]))
    return {
        **metrics(
            np.asarray([row["observed"] for row in rows]),
            np.asarray([row["raw_prediction"] for row in rows]),
        ),
        "paper_equal_mae": float(np.mean([np.mean(errors) for errors in by_doi.values()])),
        "records": len(rows),
        "papers": len(by_doi),
    }


def _availability(rows):
    """Summarize independent-prediction availability without dropping diagnostic rows."""
    available = [r for r in rows if r["status"] in ("ok", "caution")]
    rejected = [r for r in rows if r["status"] not in ("ok", "caution")]
    reasons = Counter(
        reason for row in rejected for reason in row["status"].split("+") if reason != "caution"
    )
    return {
        "total_records": len(rows),
        "available_records": len(available),
        "available_fraction": len(available) / len(rows) if rows else None,
        "available_papers": len({r["doi"] for r in available}),
        "total_papers": len({r["doi"] for r in rows}),
        "rejected_records": len(rejected),
        "rejection_reasons": dict(sorted(reasons.items())),
        "available_metrics": _score(available) if available else None,
        "unavailable_metrics_reason": None if available else "no available predictions",
    }


def _common_support(candidates):
    """Score each candidate on the same records, requiring availability for every candidate."""
    available_ids = [
        {r["record_id"] for r in rows if r["status"] in ("ok", "caution")}
        for rows in candidates.values()
    ]
    common = set.intersection(*available_ids) if available_ids else set()
    return {
        "record_ids": sorted(common),
        "records": len(common),
        "metrics": {
            name: _score([r for r in rows if r["record_id"] in common]) if common else None
            for name, rows in candidates.items()
        },
        "unavailable_metrics_reason": None if common else "no common available records",
    }


def _coverage(snapshot, split, selection):
    """Count composition signatures without treating them as independent samples."""
    records = {r["record_id"]: r for r in snapshot["content"]["records"]}

    def counts(ids):
        signatures = set()
        unavailable = []
        for identifier in ids:
            comp, _ = composition(records[identifier]["payload"].get("recipe") or {})
            if comp is None:
                unavailable.append(identifier)
                continue
            amounts = defaultdict(float)
            for component in comp["components"]:
                amounts[(component["role"], component["species"])] += component["amount"]
            signatures.add(
                digest(
                    {
                        "basis": comp["basis"],
                        "scope": comp["scope"],
                        "amounts": [
                            [*key, value] for key, value in sorted(amounts.items()) if value > 0
                        ],
                    }
                )
            )
        return {
            "records": len(ids),
            "papers": len({normalize_doi(records[i]["payload"]["source"]["doi"]) for i in ids}),
            "composition_signatures": len(signatures),
            "signature_unavailable_record_ids": sorted(unavailable),
        }

    return {
        part: {
            "parent": counts(split["content"]["splits"][part]["record_ids"]),
            "retained": counts(selection["content"]["retained"][part]),
            "excluded": selection["content"]["excluded"][part],
        }
        for part in ("train", "validation", "test")
    }


def _verify_research_evidence(snapshot, qualification, raw_files):
    """Check frozen records against qualification and the supplied original files."""
    content = snapshot["content"]
    if content.get("dataset_kind") != qualification["content"].get("dataset_kind"):
        raise ValueError("snapshot and qualification dataset kind mismatch")
    if content.get("dataset_kind") != "research":
        return
    qc = qualification["content"]
    target = qc.get("target") or {}
    if (target.get("metric"), target.get("definition"), target.get("unit")) != (
        content.get("target"),
        content.get("target_definition"),
        content.get("target_unit"),
    ):
        raise ValueError("snapshot and qualification target mismatch")
    items = qc.get("records") or []
    qualified = {r["record_id"]: r for r in items}
    if len(items) != len(qualified):
        raise ValueError("duplicate qualification records")
    required_hashes = set()
    for record in content["records"]:
        evidence = qualified.get(record["record_id"])
        if not evidence or evidence.get("status") != "included" or evidence.get("integrity_errors"):
            raise ValueError("missing or invalid qualification evidence")
        if (
            digest(record["payload"]) != record.get("payload_sha256")
            or record.get("payload_sha256") != evidence.get("payload_sha256")
            or not record.get("input_sha256")
            or record.get("input_sha256") != evidence.get("input_sha256")
            or record.get("input_locator") != evidence.get("input_locator")
        ):
            raise ValueError("snapshot and qualification evidence mismatch")
        required_hashes.add(record["input_sha256"])
    for expected in required_hashes:
        try:
            actual = hashlib.sha256(Path((raw_files or {})[expected]).read_bytes()).hexdigest()
        except (KeyError, OSError) as error:
            raise ValueError(f"missing original source file: {expected}") from error
        if actual != expected:
            raise ValueError(f"original source hash mismatch: {expected}")


def compare_r1(snapshot, qualification, split, *, raw_files=None):
    """Compare defaults using original train OOF, then evaluate held-out partitions.

    Reconstructs selection from validated inputs. The historical test set is evaluated only
    after OOF selection. Invalid targets or insufficient groups stop evaluation.
    """
    selection = select_inputs(snapshot, qualification, split)
    _verify_research_evidence(snapshot, qualification, raw_files)
    content = snapshot["content"]
    if content.get("target") != "co2_conversion" or content.get("target_unit") != "%":
        raise ValueError("R1 requires CO2 conversion target in percent")
    records_by_id = {record["record_id"]: record for record in content["records"]}
    ids = selection["content"]["retained"]
    train = [records_by_id[i] for i in sorted(ids["train"])]
    heldout = {
        part: [records_by_id[i] for i in sorted(ids[part])] for part in ("validation", "test")
    }
    if not train or any(not records for records in heldout.values()):
        raise ValueError("train, validation and test must contain selected records")
    groups = np.asarray([normalize_doi(r["payload"]["source"]["doi"]) for r in train])
    if len(set(groups)) < 3:
        raise ValueError("train needs at least 3 DOI groups for 3-fold GroupKFold")
    targets = np.asarray([target_value(r, content) for r in train], dtype=float)
    folds = list(GroupKFold(n_splits=3).split(np.arange(len(train)), groups=groups))
    assignments = [None] * len(train)
    oof = {(feature, name): [] for feature in FEATURE_SETS for name in MODEL_ORDER}
    fold_details = []
    for fold, (fit_idx, hold_idx) in enumerate(folds):
        for i in hold_idx:
            assignments[i] = fold
        detail = {
            "fold": fold,
            "training_record_ids": [train[i]["record_id"] for i in fit_idx],
            "held_out_record_ids": [train[i]["record_id"] for i in hold_idx],
            "features": {},
        }
        for feature in FEATURE_SETS:
            transformer = R1Features.fit([train[i]["payload"] for i in fit_idx], feature)
            matrix = [transformer.transform_one(train[i]["payload"])["values"] for i in fit_idx]
            feature_detail = {"vocabulary": [list(k) for k in transformer.vocabulary], "models": {}}
            for name in MODEL_ORDER:
                model = _model(name).fit(matrix, targets[fit_idx])
                predictions = _predict(transformer, model, train, hold_idx)
                rows = [
                    {
                        "record_id": train[i]["record_id"],
                        "doi": str(groups[i]),
                        "fold": fold,
                        "observed": float(targets[i]),
                        **prediction,
                    }
                    for i, prediction in zip(hold_idx, predictions, strict=True)
                ]
                oof[(feature, name)].extend(rows)
                feature_detail["models"][name] = _score(rows)
            detail["features"][feature] = feature_detail
        fold_details.append(detail)
    scores = {
        feature: {name: _score(oof[(feature, name)]) for name in MODEL_ORDER}
        for feature in FEATURE_SETS
    }
    selected = min(MODEL_ORDER, key=lambda name: scores["F_base"][name]["paper_equal_mae"])
    fitted = {}
    for feature in FEATURE_SETS:
        transformer = R1Features.fit([r["payload"] for r in train], feature)
        matrix = [transformer.transform_one(r["payload"])["values"] for r in train]
        fitted[feature] = (transformer, _model(selected).fit(matrix, targets))
    heldout_reports = {}
    for part, records in heldout.items():
        y = [target_value(r, content) for r in records]
        rows_by_feature = {}
        for feature, (transformer, model) in fitted.items():
            predictions = _predict(transformer, model, records, range(len(records)))
            rows_by_feature[feature] = [
                {
                    "record_id": record["record_id"],
                    "doi": normalize_doi(record["payload"]["source"]["doi"]),
                    "observed": float(target),
                    **prediction,
                }
                for record, target, prediction in zip(records, y, predictions, strict=True)
            ]
        heldout_reports[part] = {
            "purpose": "development"
            if part == "validation"
            else "previously viewed historical comparison",
            "candidates": {
                feature: {
                    "metrics": _score(rows),
                    "availability": _availability(rows),
                    "predictions": rows,
                }
                for feature, rows in rows_by_feature.items()
            },
            "common_support": _common_support(rows_by_feature),
        }
    report = {
        "schema_version": "r1-oof-comparison-v1",
        "selection": selection,
        "input_coverage": _coverage(snapshot, split, selection),
        "feature_version": "r1-features-v1",
        "target_definition": content.get("target_definition"),
        "feature_implementation_sha256": hashlib.sha256(
            (Path(__file__).parents[1] / "features" / "pipeline.py").read_bytes()
        ).hexdigest(),
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "dependencies": {
            "python": platform.python_version(),
            **{name: importlib.metadata.version(name) for name in ("numpy", "scikit-learn")},
        },
        "configuration": {
            "folds": 3,
            "group": "normalized_doi",
            "ordering": "record_id",
            "cross_validation": {"class": "GroupKFold", "n_splits": 3, "shuffle": False},
            "model_order_tie_break": list(MODEL_ORDER),
            "selection_metric": "oof_paper_equal_mae",
            "feature_sets": list(FEATURE_SETS),
            "models": {
                "dummy": {"strategy": "mean"},
                "ridge": {"alpha": 1.0, "scaling": "training_standard_scaler"},
                "extra_trees": {
                    "n_estimators": 100,
                    "min_samples_leaf": 2,
                    "random_state": 42,
                    "n_jobs": 1,
                },
            },
        },
        "fold_assignments": [
            {"record_id": r["record_id"], "doi": str(groups[i]), "fold": assignments[i]}
            for i, r in enumerate(train)
        ],
        "fold_details": fold_details,
        "oof_scores": scores,
        "oof_availability": {
            feature: {name: _availability(oof[(feature, name)]) for name in MODEL_ORDER}
            for feature in FEATURE_SETS
        },
        "oof_common_support_by_model": {
            name: _common_support({feature: oof[(feature, name)] for feature in FEATURE_SETS})
            for name in MODEL_ORDER
        },
        "oof_common_support_all_candidates": _common_support(
            {
                f"{feature}/{name}": oof[(feature, name)]
                for feature in FEATURE_SETS
                for name in MODEL_ORDER
            }
        ),
        "oof_predictions": {
            f: {n: sorted(oof[(f, n)], key=lambda r: r["record_id"]) for n in MODEL_ORDER}
            for f in FEATURE_SETS
        },
        "selected": {"feature_set": "F_base", "model": selected},
        "validation": heldout_reports["validation"],
        "test": heldout_reports["test"],
        "limitations": [
            "Diagnostic scores include unsupported and out-of-range predictions.",
            "Test has previously been viewed and is a historical comparison, not confirmation.",
            "No packaged prediction interface or independent confirmation.",
        ],
    }
    report["content_sha256"] = digest(report)
    transformer, model = fitted["F_base"]
    return report, {"features": transformer, "model": model}


def write_r1_comparison(output, report):
    """Persist reviewable comparison evidence in a fresh directory (never overwrite)."""
    if report.get("content_sha256") != digest(
        {key: value for key, value in report.items() if key != "content_sha256"}
    ):
        raise ValueError("comparison report hash mismatch")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "report.json", report)
    write_json(output / "selection.json", report["selection"])
    write_json(output / "configuration.json", report["configuration"])
    write_json(
        output / "folds.json",
        {
            "report_content_sha256": report["content_sha256"],
            "assignments": report["fold_assignments"],
            "details": report["fold_details"],
        },
    )
    lines = [
        "# R1 默认模型比较（3.2）",
        "",
        f"报告内容 SHA-256：`{report['content_sha256']}`",
        "",
        "原 train 内固定三折 DOI GroupKFold；每折独立拟合词表及 Ridge 标准化。",
        "按全部 OOF 记录的论文等权 MAE 在 F_base 中选型；F_cond 为对照。",
        "",
        "| 特征集 | 模型 | OOF 论文等权 MAE | 逐行 MAE | RMSE | 入口可用条数 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for feature in FEATURE_SETS:
        for name in MODEL_ORDER:
            score = report["oof_scores"][feature][name]
            availability = report["oof_availability"][feature][name]
            lines.append(
                f"| {feature} | {name} | {score['paper_equal_mae']:.6f} | "
                f"{score['mae']:.6f} | {score['rmse']:.6f} | "
                f"{availability['available_records']}/{availability['total_records']} |"
            )
    lines.extend(["", f"选定：F_base / {report['selected']['model']}。", ""])
    for part, label in (("validation", "开发验证"), ("test", "已查看的历史 test 对照")):
        candidate = report[part]["candidates"]["F_base"]
        score, availability = candidate["metrics"], candidate["availability"]
        lines.append(
            f"{label}：全体诊断 MAE {score['mae']:.6f}、"
            f"论文等权 MAE {score['paper_equal_mae']:.6f} 个百分点；"
            f"入口可用 {availability['available_records']}/{availability['total_records']}。"
        )
    lines.extend(
        [
            "",
            "所有误差单位均为百分点。全体诊断包括未见物种和输出越界记录，不能当作入口可用预测。",
            "共同可用子集仅用于辅助比较，不替代全体 OOF 选模指标。",
            "来源接受不等于逐行原文核验；绝压沿用用户假设。组成签名不证明样品独立性。",
            "历史 test 不用于选模，也不构成前瞻确认或经验证的适用域。",
            "独立预测包和自定义训练配置分别属于 3.3、3.4。",
            "",
            "逐行预测、可用率、筛选覆盖和共同支持子集见 report.json；",
            "筛选、有效默认配置和逐记录折归属分别见 "
            "selection.json、configuration.json、folds.json。",
        ]
    )
    (output / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_configured(path):
    """Run a validated S2 experiment and persist its evidence in a fresh directory.

    The returned fitted estimators are development objects, not prediction packages.
    """
    import json

    from catalyst_ai.features.enhanced import EnhancedFeatures
    from catalyst_ai.modeling.config import load_config
    from catalyst_ai.storage.feature_catalog import get_catalog

    path = Path(path).resolve()
    validated = load_config(path)
    config = validated["effective_config"]
    base = path.parent
    dataset = config["dataset"]
    docs = {
        name: json.loads((base / dataset[name]).read_text(encoding="utf-8"))
        for name in ("snapshot", "qualification", "split", "selection", "features")
    }
    snapshot, selection = docs["snapshot"], docs["selection"]
    if config["features"]["preset"] == "R1":
        selection = select_inputs(snapshot, docs["qualification"], docs["split"])
    binding = docs["selection"]["content"]["binding"]
    database = (base / dataset["catalog_database"]).resolve()
    properties = get_catalog(database, "properties", binding["property_version"])
    species = get_catalog(database, "species", binding["mapping_version"])
    content = snapshot["content"]
    if content.get("target") != "co2_conversion" or content.get("target_unit") != "%":
        raise ValueError("training requires CO2 conversion target in percent")
    records = {r["record_id"]: r for r in content["records"]}
    partitions = {
        part: [records[i] for i in sorted(selection["content"]["retained"][part])]
        for part in ("train", "validation", "test")
    }
    if any(not rows for rows in partitions.values()):
        raise ValueError("train, validation and test must contain selected records")
    train = partitions["train"]
    groups = np.asarray([normalize_doi(r["payload"]["source"]["doi"]) for r in train])
    targets = np.asarray([target_value(r, content) for r in train], dtype=float)
    features = config["features"]["sets"]
    models = {m["name"]: m["params"] for m in config["models"]}
    order = [name for name in MODEL_ORDER if name in models]

    def transformer(rows, feature):
        payloads = [r["payload"] for r in rows]
        if feature in ("F1", "F2"):
            return EnhancedFeatures.fit(payloads, feature, properties=properties, species=species)
        return R1Features.fit(payloads, feature)

    def estimator(name):
        params = models[name]
        if name == "dummy":
            return DummyRegressor(strategy="mean")
        if name == "ridge":
            return make_pipeline(StandardScaler(), Ridge(**params))
        return ExtraTreesRegressor(random_state=config["seed"], **params)

    def rows_for(transform, model, rows, indices, fold=None):
        predictions = _predict(transform, model, rows, indices)
        return [
            {
                "record_id": rows[i]["record_id"],
                "doi": normalize_doi(rows[i]["payload"]["source"]["doi"]),
                "observed": float(target_value(rows[i], content)),
                **({"fold": fold} if fold is not None else {}),
                **prediction,
            }
            for i, prediction in zip(indices, predictions, strict=True)
        ]

    oof = {(f, n): [] for f in features for n in order}
    folds = []
    for fold, (fit_idx, hold_idx) in enumerate(
        GroupKFold(n_splits=config["validation"]["n_splits"]).split(
            np.arange(len(train)), groups=groups
        )
    ):
        detail = {
            "fold": fold,
            "training_record_ids": [train[i]["record_id"] for i in fit_idx],
            "held_out_record_ids": [train[i]["record_id"] for i in hold_idx],
            "features": {},
        }
        for feature in features:
            transform = transformer([train[i] for i in fit_idx], feature)
            vocabulary = (
                transform.base.vocabulary if feature in ("F1", "F2") else transform.vocabulary
            )
            matrix = [transform.transform_one(train[i]["payload"])["values"] for i in fit_idx]
            detail["features"][feature] = {"vocabulary": [list(k) for k in vocabulary]}
            for name in order:
                model = estimator(name).fit(matrix, targets[fit_idx])
                oof[feature, name].extend(rows_for(transform, model, train, hold_idx, fold))
        folds.append(detail)
    scores = {f: {n: _score(oof[f, n]) for n in order} for f in features}
    feature_order = [f for f in ("F_base", "F1", "F2", "F_cond") if f in features]
    if config["mode"] == "baseline_compare" and config["features"]["preset"] == "R1":
        feature_order = ["F_base"]
    selected_feature, selected_name = min(
        ((f, n) for f in feature_order for n in order),
        key=lambda pair: scores[pair[0]][pair[1]]["paper_equal_mae"],
    )
    fitted = {}
    heldout = {part: {} for part in ("validation", "test")}
    for feature in features:
        transform = transformer(train, feature)
        matrix = [transform.transform_one(r["payload"])["values"] for r in train]
        for name in order:
            model = estimator(name).fit(matrix, targets)
            fitted[feature, name] = (transform, model)
            for part in heldout:
                rows = rows_for(transform, model, partitions[part], range(len(partitions[part])))
                heldout[part][f"{feature}/{name}"] = rows
    report = {
        "schema_version": "s2-experiment-v1",
        "selection": selection,
        "input_coverage": _coverage(snapshot, docs["split"], selection),
        "configuration": validated,
        "binding": binding,
        "input_hashes": {k: v["content_sha256"] for k, v in docs.items()},
        "implementation_sha256": {
            str(p.relative_to(Path(__file__).parents[1])): hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
            for p in (
                Path(__file__),
                Path(__file__).parents[1] / "features" / "pipeline.py",
                Path(__file__).parents[1] / "features" / "enhanced.py",
                Path(__file__).parents[1] / "features" / "physchem.py",
                Path(__file__).parent / "config.py",
            )
        },
        "dependencies": {
            "python": platform.python_version(),
            **{
                n: importlib.metadata.version(n)
                for n in ("numpy", "scikit-learn", "pydantic", "PyYAML")
            },
        },
        "fold_details": folds,
        "fold_assignments": [
            {"record_id": train[i]["record_id"], "doi": str(groups[i]), "fold": fold["fold"]}
            for fold in folds
            for i in range(len(train))
            if train[i]["record_id"] in fold["held_out_record_ids"]
        ],
        "oof_scores": scores,
        "oof_predictions": {
            f: {n: sorted(oof[f, n], key=lambda r: r["record_id"]) for n in order} for f in features
        },
        "oof_availability": {f: {n: _availability(oof[f, n]) for n in order} for f in features},
        "oof_common_support_all_candidates": _common_support(
            {f"{f}/{n}": oof[f, n] for f in features for n in order}
        ),
        "selected": {"feature_set": selected_feature, "model": selected_name},
        "limitations": [
            "Diagnostic scores include unavailable predictions.",
            "Historical test has previously been viewed; it is not confirmation.",
            "R2 uses the S1 common subset; do not subtract R1 full-set results.",
        ],
    }
    for part, candidates in heldout.items():
        report[part] = {
            "purpose": "development"
            if part == "validation"
            else "previously viewed historical comparison",
            "candidates": {
                key: {
                    "metrics": _score(rows),
                    "availability": _availability(rows),
                    "predictions": rows,
                }
                for key, rows in candidates.items()
            },
            "common_support": _common_support(candidates),
        }
    import pickle

    report["fitted_sha256"] = {
        f"{feature}/{name}": hashlib.sha256(
            pickle.dumps({"features": transform, "model": model}, protocol=4)
        ).hexdigest()
        for (feature, name), (transform, model) in fitted.items()
    }
    report["target_definition"] = content.get("target_definition") or "CO2 conversion"
    report["content_sha256"] = digest(report)
    output = (base / config["output"]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "report.json", report)
    write_json(output / "configuration.json", validated)
    write_json(output / "folds.json", {"assignments": report["fold_assignments"], "details": folds})
    write_json(output / "selection.json", selection)
    return report, fitted
