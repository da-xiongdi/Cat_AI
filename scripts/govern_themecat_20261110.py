"""Apply the user's absolute-pressure assumption to the original TheMeCat import.

All updates go through the append-only revision API. This is a resumable one-off
batch; it does not review records or infer missing numerical values.
"""

import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

from sqlalchemy import select

from catalyst_ai.config import Settings
from catalyst_ai.datasets.eligibility import (
    THEMECAT_ACCEPTED,
    THEMECAT_SHA256,
    build_target_eligibility,
    freeze_qualified_snapshot,
)
from catalyst_ai.reporting.evidence import digest, write_json
from catalyst_ai.revision import revise
from catalyst_ai.sources.themecat import adapt_v2
from catalyst_ai.storage.db import transaction
from catalyst_ai.storage.models import ImportRunRow, StagedRow

PAPER = "https://doi.org/10.1038/s41597-025-06482-8"
DEFINITIONS = {
    "co2_conversion": "100 * (CO2 inlet molar flow - CO2 outlet molar flow) / CO2 inlet molar flow",
    "methanol_selectivity": (
        "100 * methanol outlet molar flow / (CO2 inlet molar flow - CO2 outlet molar flow)"
    ),
    "methanol_yield": "100 * methanol outlet molar flow / CO2 inlet molar flow",
    "methanol_sty": "methanol outlet mass flow per catalyst mass",
}


def main():
    settings = Settings()
    output = Path("artifacts/reports/themecat-governance-20261110")
    output.mkdir(parents=True, exist_ok=True)
    backup = output / "catalog-before.sqlite"
    if not backup.exists():
        with sqlite3.connect(settings.database) as db, sqlite3.connect(backup) as saved:
            db.backup(saved)
    raw_path = settings.data_dir / "raw" / (THEMECAT_SHA256 + ".csv")
    data = raw_path.read_bytes()
    if hashlib.sha256(data).hexdigest() != THEMECAT_SHA256:
        raise ValueError("原件哈希不匹配")
    rows, _ = adapt_v2(data)
    by_locator = {row.locator: row for row in rows}
    with transaction(settings.database) as session:
        parents = [
            (r.id, r.input_locator, digest(r.payload), r.fingerprint)
            for r in session.scalars(
                select(StagedRow)
                .join(ImportRunRow, StagedRow.run_id == ImportRunRow.id)
                .where(
                    ImportRunRow.input_sha256 == THEMECAT_SHA256, StagedRow.status != "duplicate"
                )
                .where(ImportRunRow.report["adapter"].as_string() == "themecat-v1")
                .order_by(StagedRow.id)
            ).all()
        ]
    if len(parents) != 820:
        raise ValueError(f"预计820条非重复原始v1记录，实际{len(parents)}；拒绝批量操作")
    results, failures = [], []
    for index, (parent, locator, parent_hash, fingerprint) in enumerate(parents, 1):
        try:
            row = by_locator[locator]
            if digest(row.raw_payload) != fingerprint:
                raise ValueError("原始行指纹不匹配")
            test = row.payload["test"]
            test["pressure_type"] = "absolute"
            test["pressure"]["provenance"] = {
                "value_source": "TheMeCat v1 CSV",
                "definition_source": (
                    "user assumption 2026-11-10: unspecified pressure treated as absolute; "
                    "not verified from original paper"
                ),
            }
            observations = row.payload["observations"]
            for obs in observations:
                obs["value"]["definition"] = DEFINITIONS[obs["metric"]]
                obs["value"]["provenance"]["definition_source"] = PAPER
            report = revise(
                settings,
                parent,
                patch={"test": test, "observations": observations},
                expected_parent_sha256=parent_hash,
                base_adapter="themecat-v2",
                reason="用户指定未标明的压力默认为绝压；按数据集论文记录指标定义和v2语义",
                operator="user-directed batch",
                evidence="用户指令 2026-11-10；" + PAPER,
            )
            results.append(report["rows"][0])
        except (ValueError, KeyError, OSError) as exc:
            failures.append({"parent_record_id": parent, "error": str(exc)})
        if index % 50 == 0:
            curated_count = sum(r["status"] == "curated" for r in results)
            print(
                f"{index}/{len(parents)}: curated={curated_count}, failures={len(failures)}",
                flush=True,
            )
    selected = [r["record_id"] for r in results]
    if selected:
        qualification = build_target_eligibility(
            settings,
            record_ids=selected,
            target="co2_conversion",
            target_definition=DEFINITIONS["co2_conversion"],
            target_unit="%",
            source_acceptance=THEMECAT_ACCEPTED,
        )
        if qualification["content"]["status"] == "ready" and not failures:
            qualification = freeze_qualified_snapshot(settings, qualification)
        path = output / "qualification.json"
        if not path.exists():
            write_json(path, qualification)
    else:
        qualification = None
    summary = {
        "input_parents": len(parents),
        "revisions": len(results),
        "failures": failures,
        "status_counts": dict(Counter(r["status"] for r in results)),
        "blocks": dict(
            Counter(i["code"] for r in results for i in r["issues"] if i["severity"] == "block")
        ),
        "qualification_counts": qualification["content"]["counts"] if qualification else None,
        "qualification_status": qualification["content"]["status"] if qualification else None,
        "snapshot": qualification["snapshot"] if qualification else None,
        "backup": str(backup),
        "pressure_assumption": (
            "unspecified pressure treated as absolute, user-directed; not verified"
        ),
        "paper": PAPER,
    }
    path = output / "summary.json"
    if not path.exists():
        write_json(path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
