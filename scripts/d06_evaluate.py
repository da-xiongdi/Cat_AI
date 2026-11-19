"""Check a frozen D-04 v2 bundle or explicitly run its D-06 point evaluation."""

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter

from catalyst_ai.features.pipeline import CONDITIONS, project
from catalyst_ai.modeling.predictor import _payload, load_package, predict_batch

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = "artifacts/models/s3-20261118-01/r2"
MODEL_ID = "s2-b985a35b63b802522f7931b87ab1cfb7518eedb672298179dad45a5c01c58113"
FEATURE_FILE = "artifacts/reports/s1-b-20261113-v4/features.json"
RULE_FILE = "artifacts/reports/d-03-20261118-01/rule.json"
PROTOCOL_SHA = "8333ce089e305b4ee44730cc82604fff83b60f4e7595dccdc31019b34e7c9fe7"
RULE_SHA = "049ca56ebe7afec86000e6d7c5bc1422ceea19be6b507d2a34b1e73a496cc86c"
REQUIRED_HASHES = {
    "protocol.md",
    "source-ledger.md",
    "candidates.json",
    "label-access.json",
    "labels.json",
    "model-manifest.json",
    "model.pkl",
    "rule.json",
    "features.json",
}
READY_MINIMUM = (30, 10)
DOMAIN_MINIMUM = (10, 5)
DOMAINS = ("inside", "warning", "outside")
AVAILABLE = {"ok", "caution"}
NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class InputRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Freeze(InputRecord):
    version: Literal["d04-evaluation-freeze-v1"]
    candidate_scope: NonEmpty
    coverage_scope: NonEmpty
    sha256: dict[str, Sha256]


class Candidate(InputRecord):
    record_id: NonEmpty
    source_group: NonEmpty | None = None
    source: NonEmpty
    locator: NonEmpty
    decision: Literal["eligible", "excluded"]
    reason: NonEmpty
    input: dict | None = None


class LabelAccess(InputRecord):
    custodian: NonEmpty
    eligible_labels_unseen_by_evaluators: Literal[True]
    history: list[NonEmpty] = Field(min_length=1)


class Label(InputRecord):
    record_id: NonEmpty
    co2_conversion_pct: float = Field(ge=0, le=100, allow_inf_nan=False)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def verified_bytes(path, expected):
    data = path.read_bytes()
    if sha256(data) != expected:
        raise ValueError(f"SHA-256 mismatch: {path}")
    return data


def write_json(path, value):
    staged = path.with_suffix(".json.tmp")
    staged.write_text(
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8"
    )
    staged.replace(path)


def counts(rows):
    groups = {row["source_group"] for row in rows} - {None}
    return {"records": len(rows), "groups": len(groups)}


def sufficient(count, minimum):
    return count["records"] >= minimum[0] and count["groups"] >= minimum[1]


def preflight(bundle, package_dir, rule_path, feature_path):
    freeze_bytes = (bundle / "freeze.json").read_bytes()
    freeze = Freeze.model_validate_json(freeze_bytes)
    hashes = freeze.sha256
    if hashes.keys() != REQUIRED_HASHES:
        raise ValueError("freeze.json must bind exactly the required D-06 files")
    if hashes["protocol.md"] != PROTOCOL_SHA or hashes["rule.json"] != RULE_SHA:
        raise ValueError("freeze does not bind D-04 protocol v2 and the fixed D-03 rule")
    for name in ("protocol.md", "source-ledger.md"):
        verified_bytes(bundle / name, hashes[name])
    candidates = [
        row.model_dump()
        for row in TypeAdapter(list[Candidate]).validate_json(
            verified_bytes(bundle / "candidates.json", hashes["candidates.json"])
        )
    ]
    if len({row["record_id"] for row in candidates}) != len(candidates):
        raise ValueError("duplicate candidate record_id")
    eligible = [row for row in candidates if row["decision"] == "eligible"]
    if len({(row["source"], row["locator"]) for row in eligible}) != len(eligible):
        raise ValueError("duplicate eligible source locator")
    for row in eligible:
        if row["source_group"] is None:
            raise ValueError(f"eligible record {row['record_id']} has no independent source group")
        try:
            project(_payload(row["input"]))
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            raise ValueError(f"invalid eligible input {row['record_id']}: {error}") from error
    access = LabelAccess.model_validate_json(
        verified_bytes(bundle / "label-access.json", hashes["label-access.json"])
    )
    manifest = json.loads(
        verified_bytes(package_dir / "manifest.json", hashes["model-manifest.json"])
    )
    verified_bytes(package_dir / "model.pkl", hashes["model.pkl"])
    rule = json.loads(verified_bytes(rule_path, hashes["rule.json"]))
    if (
        manifest["model_id"] != MODEL_ID
        or manifest["artifact_sha256"] != hashes["model.pkl"]
        or rule["model_id"] != MODEL_ID
        or rule["version"] != "d03-candidate-v1"
        or rule["input_sha256"][f"{MODEL_DIR}/manifest.json"] != hashes["model-manifest.json"]
        or rule["input_sha256"][FEATURE_FILE] != hashes["features.json"]
    ):
        raise ValueError("D-03 rule, feature reference and S3 R2 package do not match")
    features = json.loads(verified_bytes(feature_path, hashes["features.json"]))
    references = final_reference(manifest, rule, features)
    candidate_count, eligible_count = counts(candidates), counts(eligible)
    summary = {
        "status": "ready" if sufficient(eligible_count, READY_MINIMUM) else "insufficient_evidence",
        "evaluation_performed": False,
        "model_id": MODEL_ID,
        "rule_version": rule["version"],
        "freeze_sha256": sha256(freeze_bytes),
        "input_sha256": hashes,
        "candidate_scope": freeze.candidate_scope,
        "coverage_scope": freeze.coverage_scope,
        "candidate": candidate_count,
        "candidate_records_without_group": sum(row["source_group"] is None for row in candidates),
        "eligible": eligible_count,
        "minimum": {"records": READY_MINIMUM[0], "groups": READY_MINIMUM[1]},
        "input_eligibility_rate": len(eligible) / len(candidates) if candidates else None,
        "label_custodian": access.custodian,
        "run_record_exists": (bundle / "d06-run").exists(),
    }
    return summary, candidates, eligible, rule["reference"]["final"], references


def composition(components, amount_field):
    result = defaultdict(float)
    for component in components:
        result[component["role"], component["species"]] += component[amount_field] / 100
    return dict(result)


def final_reference(manifest, rule, features):
    training_ids = set(manifest["training_record_ids"])
    rows = [row for row in features["content"]["rows"] if row["record_id"] in training_ids]
    if (
        len(rows) != len(training_ids)
        or {r["record_id"] for r in rows} != training_ids
        or len(rows) != rule["reference"]["final"]["records"]
        or not all(row["partition"] == "train" for row in rows)
    ):
        raise ValueError("D-03 final training reference is incomplete or mismatched")
    return [
        (composition(row["composition"], "material_mol_pct"), row["conditions"]) for row in rows
    ]


def classify(item, result, rule, references):
    if result["status"] == "unsupported_species_role":
        return "outside", ["unsupported_species_role"], None, None
    amounts = composition(item["components"], "mol_pct")
    comp = min(
        math.fsum(abs(amounts.get(k, 0) - ref.get(k, 0)) for k in amounts.keys() | ref.keys())
        for ref, _ in references
    )
    scales = rule["condition_iqr"]
    cond = min(
        (
            max(abs(item[k] - ref[k]) / scales[k] for k in CONDITIONS)
            for _, ref in references
            if all(ref[k] is not None for k in CONDITIONS)
        ),
        default=None,
    )
    caution = result["status"] == "caution" or bool(result["out_of_range"])
    label, reasons = ("warning", ["existing_caution"]) if caution else ("inside", [])
    for name, distance in (("composition", comp), ("conditions", cond)):
        p90, p99 = rule["thresholds"][name]
        if distance is None or distance > p90:
            if distance is not None and distance > p99:
                label = "outside"
                reasons.append(f"{name}_above_p99")
            else:
                if label == "inside":
                    label = "warning"
                reasons.append(f"{name}_unassessable" if distance is None else f"{name}_above_p90")
    return label, reasons, comp, cond


def read_labels(path, expected_hash, eligible):
    labels = {}
    for label in TypeAdapter(list[Label]).validate_json(verified_bytes(path, expected_hash)):
        if label.record_id in labels:
            raise ValueError(f"duplicate label: {label.record_id}")
        labels[label.record_id] = label.co2_conversion_pct
    if labels.keys() != {row["record_id"] for row in eligible}:
        raise ValueError("label IDs must exactly match eligible record IDs")
    return labels


def score(rows, total, minimum):
    available = [row for row in rows if row["absolute_error_pct_points"] is not None]
    errors = [row["absolute_error_pct_points"] for row in available]
    by_group = defaultdict(list)
    for row in available:
        by_group[row["source_group"]].append(row["absolute_error_pct_points"])
    population, usable = counts(rows), counts(available)
    return {
        **population,
        "coverage": len(rows) / total if total else None,
        "available": usable,
        "availability": len(available) / len(rows) if rows else None,
        "mae_pct_points": fmean(errors) if errors else None,
        "rmse_pct_points": math.sqrt(fmean(error**2 for error in errors)) if errors else None,
        "group_equal_mae_pct_points": (
            fmean(fmean(group) for group in by_group.values()) if by_group else None
        ),
        "coverage_evidence": sufficient(population, minimum),
        "error_evidence": sufficient(usable, minimum),
    }


def predict_rows(package, eligible, rule, references):
    predictions = predict_batch(package, [row["input"] for row in eligible])
    rows = []
    for row, result in zip(eligible, predictions, strict=True):
        domain, reasons, comp, cond = classify(row["input"], result, rule, references)
        rows.append(
            {
                "record_id": row["record_id"],
                "source_group": row["source_group"],
                "source": row["source"],
                "locator": row["locator"],
                "prediction": result,
                "domain": domain,
                "domain_reasons": reasons,
                "composition_distance": comp,
                "condition_distance": cond,
            }
        )
    return rows


def evaluate(bundle, package_dir, labels_path, checked):
    summary, candidates, eligible, rule, references = checked
    if summary["status"] != "ready":
        raise ValueError("insufficient eligible records or groups; labels remain sealed")
    if (bundle / "d06-run").exists():
        raise FileExistsError("this frozen bundle already has a D-06 run record")
    package = load_package(package_dir)
    if package[0]["model_id"] != MODEL_ID:
        raise ValueError("loaded package is not the frozen S3 R2 model")

    out = bundle / "d06-run"
    out.mkdir(exist_ok=False)
    summary = {
        **summary,
        "status": "in_progress",
        "run_record_exists": True,
        "execution_sha256": sha256(Path(__file__).read_bytes()),
        "model_dependencies": package[0]["dependencies"],
    }
    write_json(out / "inputs.json", summary)
    try:
        rows = predict_rows(package, eligible, rule, references)
        summary["evaluation_label_access_started_at_utc"] = datetime.now(UTC).isoformat()
        write_json(out / "inputs.json", summary)
        labels = read_labels(labels_path, summary["input_sha256"]["labels.json"], eligible)
        for row in rows:
            result = row["prediction"]
            observed = labels[row["record_id"]]
            value = result["co2_conversion_pct"] if result["status"] in AVAILABLE else None
            row.update(
                observed_co2_conversion_pct=observed,
                absolute_error_pct_points=abs(value - observed) if value is not None else None,
            )
        statuses = {row["prediction"]["status"] for row in rows} | AVAILABLE
        reasons = Counter(
            reason
            for row in rows
            if row["prediction"]["status"] not in AVAILABLE
            for reason in set(row["prediction"]["validation"])
        )
        metrics = {
            "candidate": summary["candidate"],
            "candidate_records_without_group": summary["candidate_records_without_group"],
            "eligible": summary["eligible"],
            "input_eligibility_rate": summary["input_eligibility_rate"],
            "exclusion_reasons": dict(
                Counter(r["reason"] for r in candidates if r["decision"] == "excluded")
            ),
            "overall": score(rows, len(rows), READY_MINIMUM),
            "entry_status": {
                status: counts([r for r in rows if r["prediction"]["status"] == status])
                for status in sorted(statuses)
            },
            "entry_rejection_reasons": dict(sorted(reasons.items())),
            "domain_minimum": {"records": DOMAIN_MINIMUM[0], "groups": DOMAIN_MINIMUM[1]},
            "domain": {
                label: score([r for r in rows if r["domain"] == label], len(rows), DOMAIN_MINIMUM)
                for label in DOMAINS
            },
        }
        write_json(out / "row-results.json", rows)
        write_json(out / "group-metrics.json", metrics)
        summary.update(status="completed", evaluation_performed=True)
        write_json(out / "inputs.json", summary)
    except Exception as error:
        summary.update(
            status="failed", evaluation_performed=False, failure_type=type(error).__name__
        )
        write_json(out / "inputs.json", summary)
        raise
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--package", type=Path, default=ROOT / MODEL_DIR)
    parser.add_argument("--rule", type=Path, default=ROOT / RULE_FILE)
    parser.add_argument("--features", type=Path, default=ROOT / FEATURE_FILE)
    parser.add_argument("--execute", action="store_true", help="run one formal D-06 evaluation")
    parser.add_argument("--labels", type=Path, help="sealed label file, required with --execute")
    args = parser.parse_args()
    if args.execute != (args.labels is not None):
        parser.error("use --execute and --labels together")
    try:
        checked = preflight(args.bundle, args.package, args.rule, args.features)
        if args.execute:
            print(evaluate(args.bundle, args.package, args.labels, checked))
        else:
            print(json.dumps(checked[0], ensure_ascii=False, indent=2))
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(1, f"D-06: {error}\n")


if __name__ == "__main__":
    main()
