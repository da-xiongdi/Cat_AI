import hashlib
import json
import sqlite3
from copy import deepcopy

import pytest
from test_feature_catalog import catalog

from catalyst_ai.features.qualification import qualify, validate_review
from catalyst_ai.features.stoichiometry import formula_counts
from catalyst_ai.storage.feature_catalog import (
    get_evidence,
    import_evidence,
    migrate,
    parse_catalog,
    query_entries,
)


@pytest.mark.parametrize(
    "name,counts",
    [
        ("LaMn0.1Cu0.9O3", {"La": 1, "Mn": 0.1, "Cu": 0.9, "O": 3}),
        ("CoGaAlO4", {"Co": 1, "Ga": 1, "Al": 1, "O": 4}),
        ("InNi3O0.5", {"In": 1, "Ni": 3, "O": 0.5}),
        ("BaCO3", {"Ba": 1, "C": 1, "O": 3}),
        ("SiO2", {"Si": 1, "O": 2}),
    ],
)
def test_explicit_formula_units(name, counts):
    assert formula_counts(name) == counts


@pytest.mark.parametrize("name", ["LaMn1-xCuxO3", "CeO2δ", "CuO0", "Cu1e3", "X2O", "Cu/ZnO"])
def test_undetermined_formula_rejected(name):
    with pytest.raises(ValueError):
        formula_counts(name)


def test_rescaled_element_counts_and_unknown_schema_rejected():
    row = {
        "species": "LaMn0.1Cu0.9O3",
        "elements": formula_counts("LaMn0.1Cu0.9O3"),
        "state": "supported",
        "centers": {"La": 1, "Mn": 0.1, "Cu": 0.9},
        "formula_unit_basis": "one nominal formula unit",
        "evidence": "descriptor convention",
    }
    obj = catalog("species", [row])
    obj["schema_version"] = 2
    assert parse_catalog(json.dumps(obj).encode())["entries"][0]["centers"]["Mn"] == 0.1
    row["elements"] = {e: n * 10 for e, n in row["elements"].items()}
    with pytest.raises(ValueError, match="unscaled"):
        parse_catalog(json.dumps(obj).encode())
    obj["schema_version"] = True
    with pytest.raises(ValueError, match="schema"):
        parse_catalog(json.dumps(obj).encode())


def test_index_tampering_is_not_masked_by_original_package(tmp_path):
    from catalyst_ai.storage.feature_catalog import import_catalog

    db = tmp_path / "old.sqlite"
    sqlite3.connect(db).close()
    migrate(db)
    obj = catalog(
        "species",
        [
            {
                "species": "BaCO3",
                "state": "supported",
                "centers": {"Ba": 1},
                "evidence": "carbonate convention",
            }
        ],
    )
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(obj), encoding="utf8")
    import_catalog(db, path, dry_run=False)
    assert query_entries(db, "species", "v1", "BaCO3")["entries"][0]["centers"] == {"Ba": 1}
    with sqlite3.connect(db) as con:
        con.execute("UPDATE feature_catalog_entry SET entry_json='{}'")
    with pytest.raises(ValueError, match="integrity"):
        query_entries(db, "species", "v1")
    with pytest.raises(ValueError, match="conflict"):
        migrate(db)


def review_inputs(sample, tmp_path):
    from test_experiments import prepared
    from test_split import rehash_snapshot

    from catalyst_ai.datasets.split import build_paper_split
    from catalyst_ai.reporting.evidence import digest

    snapshot, qualification, _ = prepared(sample)
    for r in snapshot["content"]["records"]:
        r["payload"]["recipe"]["components"][0]["species"] = "Cu"
    rehash_snapshot(snapshot, qualification)
    split = build_paper_split(snapshot, qualification)
    evidence = tmp_path / "source.txt"
    evidence.write_text("test evidence")
    sha = hashlib.sha256(evidence.read_bytes()).hexdigest()
    rows = []
    for r in snapshot["content"]["records"]:
        p = r["payload"]
        rows.append(
            {
                "record_id": r["record_id"],
                "component_index": 0,
                "original_species": "Cu",
                "role": "compound",
                "source_doi": p["source"]["doi"],
                "dataset_sample_name": p["recipe"]["material_family"],
                "dataset_locator": p["extraction"]["locator"],
                "evidence_location": "test",
                "rationale": "test convention",
                "evidence_sha256": [sha],
                "status": "dataset_accepted",
            }
        )
    rows[0]["status"] = "evidence_insufficient"
    review = {
        "schema_version": 1,
        "version": "test-review-v1",
        "rule_version": "test-v1",
        "reviewer": "synthetic test",
        "parent_snapshot_id": snapshot["snapshot_id"],
        "parent_content_sha256": snapshot["content_sha256"],
        "evidence": [{"path": "source.txt", "sha256": sha, "type": "synthetic"}],
        "components": rows,
    }
    props = catalog(
        "properties",
        [
            {"element": "Cu", "property": p, "unit": u, "state": "available", "value": 1}
            for p, u in [("pauling_electronegativity", "1"), ("covalent_radius", "pm")]
        ],
    )
    mapping = catalog(
        "species",
        [{"species": "Cu", "state": "supported", "centers": {"Cu": 1}, "evidence": "synthetic"}],
    )
    return (
        snapshot,
        qualification,
        split,
        {"catalog": props, "sha256": digest(props)},
        {"catalog": mapping, "sha256": digest(mapping)},
        {"review": review, "sha256": digest(review)},
    )


def test_parseable_mapped_species_still_requires_record_evidence(sample, tmp_path):
    args = review_inputs(sample, tmp_path)
    report = qualify(*args, root=tmp_path)["content"]
    assert report["summary"]["records"]["formula_parseable"] == 12
    assert report["summary"]["records"]["mapping_supported"] == 12
    assert report["summary"]["records"]["joint_supported"] == 11
    assert report["summary"]["denominator_records"] == 12
    assert report["records"][0]["roles"]["support"] == "not_applicable"
    assert sum(p["denominator_records"] for p in report["by_partition"].values()) == 12
    assert report["by_species"]["Cu"]["supported_occurrences"]["joint_supported"] == 11
    bad = deepcopy(args)
    bad[-1]["review"]["components"][0]["candidate_species"] = "Zn"
    bad[-1]["review"]["components"][0]["status"] = "dataset_accepted"
    with pytest.raises(ValueError, match="candidate"):
        qualify(*bad, root=tmp_path)
    bad = deepcopy(args)
    bad[-1]["review"]["components"][0]["source_doi"] = "10.1234/another"
    with pytest.raises(ValueError, match="identity"):
        qualify(*bad, root=tmp_path)
    bad = deepcopy(args)
    bad[-1]["review"]["components"].pop()
    with pytest.raises(ValueError, match="scope"):
        qualify(*bad, root=tmp_path)
    (tmp_path / "source.txt").write_text("changed")
    with pytest.raises(ValueError, match="evidence hash"):
        qualify(*args, root=tmp_path)


def test_review_persistence_is_versioned_and_pending_is_not_disposition(sample, tmp_path):
    review = review_inputs(sample, tmp_path)[-1]["review"]
    db = tmp_path / "old.sqlite"
    sqlite3.connect(db).close()
    migrate(db)
    path = tmp_path / "review.json"
    path.write_text(json.dumps(review), encoding="utf8")
    assert import_evidence(db, path)["status"] == "validated"
    assert import_evidence(db, path, dry_run=False)["status"] == "imported"
    assert import_evidence(db, path, dry_run=False)["status"] == "existing"
    assert get_evidence(db, "test-review-v1")["review"] == review
    review["reviewer"] = "changed"
    path.write_text(json.dumps(review), encoding="utf8")
    with pytest.raises(ValueError, match="conflict"):
        import_evidence(db, path)
    review["components"][0]["status"] = "pending"
    with pytest.raises(ValueError, match="unresolved"):
        validate_review(review)


def test_unsupported_component_excludes_whole_record_without_hiding_supported_species(
    sample, tmp_path
):
    from test_split import rehash_snapshot

    from catalyst_ai.datasets.split import build_paper_split

    args = list(review_inputs(sample, tmp_path))
    snapshot, qualification = args[:2]
    record = snapshot["content"]["records"][0]
    component = record["payload"]["recipe"]["components"][0]
    component["amount"]["normalized_value"] = 50
    other = deepcopy(component)
    other.update(species="ZnO", role="support")
    record["payload"]["recipe"]["components"].append(other)
    rehash_snapshot(snapshot, qualification)
    args[2] = build_paper_split(snapshot, qualification)
    review = args[-1]["review"]
    review.update(
        parent_snapshot_id=snapshot["snapshot_id"], parent_content_sha256=snapshot["content_sha256"]
    )
    review["components"][0]["status"] = "dataset_accepted"
    review["components"].append(
        dict(review["components"][0], component_index=1, original_species="ZnO", role="support")
    )
    report = qualify(*args, root=tmp_path)["content"]
    assert not report["records"][0]["joint_supported"]
    assert "unsupported_species:ZnO" in report["records"][0]["reasons"]
    assert report["by_species"]["Cu"]["supported_occurrences"]["joint_supported"] == 12
    assert report["summary"]["records"]["joint_supported"] == 11


def test_missing_database_evidence_import_does_not_create_database(tmp_path):
    db = tmp_path / "missing.sqlite"
    with pytest.raises(ValueError, match="database does not exist"):
        import_evidence(db, tmp_path / "missing.json")
    assert not db.exists()
