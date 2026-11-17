"""Reproduce S1-A closeout from pinned evidence; never modify catalyst facts."""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from catalyst_ai.features.qualification import qualify
from catalyst_ai.features.stoichiometry import formula_counts
from catalyst_ai.reporting.evidence import digest, write_json, write_new
from catalyst_ai.storage.feature_catalog import (
    coverage,
    get_catalog,
    get_evidence,
    import_catalog,
    import_evidence,
    migrate,
    query_entries,
)

SNAPSHOT = Path(
    "data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json"
)
QUALIFICATION = Path(
    "data/snapshots/qualifications/qualification-"
    "b450e999aca00cd7e035b5bb1006a48d3fbd171520391710eb05a2490aa85967."
    "json"
)
SPLIT = Path("artifacts/reports/themecat-i2-20261110/split-verified.json")
EVIDENCE = Path("artifacts/reports/s1-a-closeout-20261113")
PROPERTY_VERSION = "mendeleev-data-665935bc-pauling-cordero-v2"
MAPPING_VERSION = "themecat-centers-v2"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_immutable(path, obj):
    raw = (json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("refuse to change existing version: " + str(path))
    else:
        write_new(path, raw)


def existing_facts(database):
    with sqlite3.connect(database) as con:
        tables = [
            r[0]
            for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if not r[0].startswith(("feature_", "sqlite_"))
        ]
        return {
            name: digest(
                sorted(
                    [
                        repr(row)
                        for row in con.execute('SELECT * FROM "' + name.replace('"', '""') + '"')
                    ]
                )
            )
            for name in tables
        }


def prepare():
    """Freeze explicit descriptor conventions, not inferred experimental identities."""
    pinned = {
        "data_license.raw": "bcbc87d5f4ce66074a3a51d84a44df0de94d0f1a4cc794e4c17bc497b226e5eb",
        "data_readme.raw": "5ee139181aa96e16225c5d1426da1a433c93cec41d8015452c526a77d14f86ce",
        "data_elements.raw": "8ea60a0afe8ba3a0d23af9220968e3d08c988d3d6d773cf032fe6a34c125ee95",
    }
    for name, expected in pinned.items():
        if sha(EVIDENCE / name) != expected:
            raise ValueError("pinned property evidence changed")
    oldprops = read("configs/s1_element_properties.json")
    elements = {r["symbol"]: r for r in read(EVIDENCE / "data_elements.raw")}
    for row in oldprops["entries"]:
        field = {
            "pauling_electronegativity": "en_pauling",
            "covalent_radius": "covalent_radius_cordero",
        }[row["property"]]
        if row["value"] != elements[row["element"]][field]:
            raise ValueError("property value differs from licensed data asset")
    props = dict(
        oldprops,
        version=PROPERTY_VERSION,
        source={
            "name": "mendeleev-data pinned 665935bc115d1aaed8a8264ce4cb54c9be8b75f7",
            ("reference"): (
                "https://github.com/lmmentel/mendeleev-"
                "data/tree/665935bc115d1aaed8a8264ce4cb54c9be8b75f7"
            ),
            ("license"): (
                "MIT; Copyright (c) 2024 Lukasz Mentel; retain data_license.raw "
                "notice. Upstream distribution declaration, not a claim about "
                "original publisher rights."
            ),
            "evidence": (
                f"{EVIDENCE.as_posix()}/data_elements.raw "
                f"sha256:{pinned['data_elements.raw']}; data_license.raw "
                f"sha256:{pinned['data_license.raw']}; "
                "236 property states/values equal v1; Cordero pm, Pauling dimensionless"
            ),
        },
    )
    mapping = read("configs/s1_species_mapping.json")
    mapping["schema_version"] = 2
    mapping["version"] = MAPPING_VERSION
    mapping["source"]["evidence"] = (
        "Feature plan sections 2.5/4.2; explicit nominal formula units; "
        "source-accepted dataset, not row-verified. La family checked "
        "against Crossref title for 10.1016/S1002-0721(09)60193-9; "
        "unresolved InNi3O0.5 and CoGaAlO4 remain unsupported."
    )
    for row in mapping["entries"]:
        name = row["species"]
        row["elements"] = formula_counts(name)
        row["formula_unit_basis"] = (
            "one nominal formula unit exactly as the dataset species string; "
            "retain whole-catalyst material mol%; no scaling"
        )
        if name.startswith("LaMn"):
            row["state"] = "supported"
            row["centers"] = {e: n for e, n in row["elements"].items() if e != "O"}
            row["evidence"] = (
                "Reviewed nominal descriptor convention: La/Mn/Cu centers, oxygen "
                "excluded; dataset sample name equals explicit formula; paper "
                "title reports LaMn1-xCuxO3 family; material mol% basis accepted "
                "from dataset. No phase/active-site or row verification claim."
            )
        elif row["state"] == "unsupported":
            row["evidence"] = (
                "Evidence insufficient for source identity/formula correspondence;"
                " quarantine. Parsed elemental counts are syntax only, no "
                "effective correction or formal descriptor eligibility."
            )
    save_immutable(Path("configs/s1_element_properties_v2.json"), props)
    save_immutable(Path("configs/s1_species_mapping_v2.json"), mapping)
    snapshot = read(SNAPSHOT)
    evidence_paths = [
        (SNAPSHOT, "accepted_dataset_snapshot"),
        (Path("data/raw/s1-a-crossref-131111.json"), "bibliographic_metadata"),
        (EVIDENCE / "la_crossref.raw", "bibliographic_metadata"),
        (EVIDENCE / "coga_crossref.raw", "bibliographic_metadata"),
        (EVIDENCE / "fetch-log.json", "source_access_log"),
        (EVIDENCE / "data_elements.raw", "licensed_data_asset"),
        (EVIDENCE / "data_license.raw", "upstream_data_license"),
        (EVIDENCE / "data_readme.raw", "data_scope_documentation"),
    ]
    refs = [{"path": p.as_posix(), "sha256": sha(p), "type": kind} for p, kind in evidence_paths]
    rows = []
    for record in snapshot["content"]["records"]:
        payload = record["payload"]
        for i, c in enumerate(payload["recipe"]["components"]):
            name = c["species"]
            insufficient = name in {"InNi3O0.5", "CoGaAlO4"}
            row = {
                "record_id": record["record_id"],
                "component_index": i,
                "original_species": name,
                "role": c["role"],
                "source_doi": payload["source"]["doi"],
                "dataset_sample_name": payload["recipe"]["material_family"],
                "dataset_locator": payload["extraction"]["locator"],
                "status": "evidence_insufficient" if insufficient else "dataset_accepted",
                "candidate_species": "InNi3C0.5" if name == "InNi3O0.5" else None,
                "rationale": (
                    (
                        "Candidate C is supported by title and dataset sample names; "
                        "publisher fetch 403; no complete sample/composition/role/test "
                        "correspondence. No correction applied."
                    )
                    if name == "InNi3O0.5"
                    else (
                        "Source metadata describes Co-Co2C alcohol catalysts; available "
                        "evidence does not resolve CoGaAlO4 sample identity. No "
                        "contradiction asserted solely from title; retain unsupported."
                    )
                    if name == "CoGaAlO4"
                    else (
                        "Retain existing published-dataset acceptance and source role; "
                        "explicit nominal formula-unit descriptor convention reviewed. No "
                        "original-paper row verification."
                    )
                ),
                ("evidence_location"): (
                    "parent snapshot recipe.components[index], source DOI, extraction "
                    "locator; bibliographic title is contextual only"
                ),
                "evidence_sha256": [refs[0]["sha256"]],
            }
            if name == "InNi3O0.5":
                row["evidence_sha256"] += [refs[1]["sha256"], refs[4]["sha256"]]
            if name.startswith("LaMn"):
                row["evidence_sha256"].append(refs[2]["sha256"])
            if name == "CoGaAlO4":
                row["evidence_sha256"].append(refs[3]["sha256"])
            rows.append(row)
    review = {
        "schema_version": 1,
        "version": "s1-source-dispositions-v2",
        "rule_version": "s1-qualification-v2",
        "reviewer": "Codex automated evidence/convention review; not human row verification",
        "parent_snapshot_id": snapshot["snapshot_id"],
        "parent_content_sha256": snapshot["content_sha256"],
        "evidence": refs,
        "components": rows,
    }
    save_immutable(Path("configs/s1_source_review_v2.json"), review)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/catalog.sqlite"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output directory exists; choose a new run directory")
    args.output.mkdir(parents=True)
    before = existing_facts(args.database)
    protected = [
        SNAPSHOT,
        QUALIFICATION,
        SPLIT,
        Path("configs/s1_element_properties.json"),
        Path("configs/s1_species_mapping.json"),
        Path("artifacts/reports/s1-a-coverage-v1.json"),
        *Path("data/raw").glob("*"),
    ]
    hashes_before = {p.as_posix(): sha(p) for p in protected if p.is_file()}
    with (
        sqlite3.connect(args.database) as con,
        sqlite3.connect(args.output / "before.sqlite") as backup,
    ):
        con.backup(backup)
    prepare()
    migrations = [migrate(args.database), migrate(args.database)]
    imports = []
    for path in ("configs/s1_element_properties_v2.json", "configs/s1_species_mapping_v2.json"):
        imports.append(
            [
                import_catalog(args.database, path),
                import_catalog(args.database, path, dry_run=False),
                import_catalog(args.database, path, dry_run=False),
            ]
        )
    review_path = "configs/s1_source_review_v2.json"
    imports.append(
        [
            import_evidence(args.database, review_path),
            import_evidence(args.database, review_path, dry_run=False),
            import_evidence(args.database, review_path, dry_run=False),
        ]
    )
    props = get_catalog(args.database, "properties", PROPERTY_VERSION)
    mapping = get_catalog(args.database, "species", MAPPING_VERSION)
    review = get_evidence(args.database, "s1-source-dispositions-v2")
    snapshot, qualification, split = read(SNAPSHOT), read(QUALIFICATION), read(SPLIT)
    report = qualify(snapshot, qualification, split, props, mapping, review, root=Path.cwd())
    repeated = qualify(snapshot, qualification, split, props, mapping, review, root=Path.cwd())
    if report != repeated:
        raise ValueError("qualification not reproducible")
    write_json(args.output / "qualification.json", report)
    legacy = coverage(
        snapshot,
        get_catalog(args.database, "properties", "mendeleev-bd4716b-cordero-pauling-v1"),
        get_catalog(args.database, "species", "themecat-centers-v1"),
    )
    if legacy != read("artifacts/reports/s1-a-coverage-v1.json"):
        raise ValueError("legacy replay changed")
    previous = {r["record_id"] for r in legacy["records"] if not r["reasons"]}
    current = {r["record_id"] for r in report["content"]["records"] if r["joint_supported"]}
    write_json(
        args.output / "v1-diff.json",
        {
            "same_parent_snapshot": True,
            "v1_supported": len(previous),
            "v2_supported": len(current),
            "added": sorted(current - previous),
            "removed": sorted(previous - current),
            ("reason"): (
                "five nominal La/Mn/Cu mappings now supported; 39 InNi3O0.5 and "
                "one CoGaAlO4 remain quarantined"
            ),
        },
    )
    write_json(
        args.output / "query-examples.json",
        {
            "Cu_radius": query_entries(
                args.database, "properties", PROPERTY_VERSION, "Cu:covalent_radius"
            ),
            "decimal_multicenter": query_entries(
                args.database, "species", MAPPING_VERSION, "LaMn0.1Cu0.9O3"
            ),
            "carbonate": query_entries(args.database, "species", MAPPING_VERSION, "BaCO3"),
        },
    )
    after = existing_facts(args.database)
    hashes_after = {p: sha(p) for p in hashes_before}
    if before != after or hashes_before != hashes_after:
        raise ValueError("protected facts/evidence changed")
    with sqlite3.connect(args.database) as con:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = con.execute("PRAGMA foreign_key_check").fetchall()
    if integrity != "ok" or foreign_keys:
        raise ValueError("database integrity failure")
    write_json(
        args.output / "acceptance.json",
        {
            "scope": "S1-A only; no computed F1/F2 or model results",
            "migration_repeated": migrations,
            "imports_dry_commit_repeat": imports,
            "integrity_check": integrity,
            "foreign_key_errors": foreign_keys,
            "protected_table_hashes_before": before,
            "protected_table_hashes_after": after,
            "protected_file_sha256": hashes_before,
            "legacy_report_replayed_equal": True,
            "qualification_replayed_equal": True,
            "report_sha256": report["content_sha256"],
            "script_sha256": sha(__file__),
        },
    )
    print(json.dumps(report["content"]["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
