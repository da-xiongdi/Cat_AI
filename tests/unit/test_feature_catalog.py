import json
import sqlite3

import pytest

from catalyst_ai.reporting.evidence import digest
from catalyst_ai.storage.feature_catalog import (
    coverage,
    get_catalog,
    import_catalog,
    migrate,
    parse_catalog,
)


def catalog(kind, entries):
    return {
        "schema_version": 1,
        "kind": kind,
        "version": "v1",
        "source": {"name": "test", "reference": "test", "license": "test", "evidence": "test"},
        "entries": entries,
    }


def test_catalog_migration_import_conflicts_and_coverage(tmp_path):
    db = tmp_path / "old.sqlite"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE existing (value TEXT)")
        con.execute("INSERT INTO existing VALUES ('retained')")
    assert migrate(db) == migrate(db) == "ok"
    props = catalog(
        "properties",
        [
            {"element": "Cu", "property": p, "unit": u, "state": "available", "value": 1.0}
            for p, u in [("pauling_electronegativity", "1"), ("covalent_radius", "pm")]
        ],
    )
    mappings = catalog(
        "species",
        [{"species": "Cu", "state": "supported", "centers": {"Cu": 1}, "evidence": "test"}],
    )
    for name, data in [("p", props), ("s", mappings)]:
        path = tmp_path / (name + ".json")
        path.write_text(json.dumps(data), encoding="utf8")
        assert import_catalog(db, path)["status"] == "validated"
        assert import_catalog(db, path, dry_run=False)["status"] == "imported"
        assert import_catalog(db, path, dry_run=False)["status"] == "existing"
    props["entries"][0]["value"] = 2
    (tmp_path / "p.json").write_text(json.dumps(props), encoding="utf8")
    with pytest.raises(ValueError, match="conflict"):
        import_catalog(db, tmp_path / "p.json")
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT value FROM existing").fetchone()[0] == "retained"
    content = {"records": [{"record_id": "r1", "payload": {}}]}
    sha = digest(content)
    snapshot = {"content": content, "content_sha256": sha, "snapshot_id": "snapshot-" + sha}
    result = coverage(
        snapshot, get_catalog(db, "properties", "v1"), get_catalog(db, "species", "v1")
    )
    assert result["supported"] == 0
    assert result["records"][0]["reasons"]
    snapshot["content"]["records"].clear()
    with pytest.raises(ValueError, match="identity"):
        coverage(snapshot, get_catalog(db, "properties", "v1"), get_catalog(db, "species", "v1"))


def test_catalog_rejects_missing_data_and_duplicates(tmp_path):
    db = tmp_path / "db.sqlite"
    sqlite3.connect(db).close()
    row = {
        "element": "Cu",
        "property": "covalent_radius",
        "unit": "pm",
        "state": "unknown",
        "value": 0,
    }
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog("properties", [row])), encoding="utf8")
    with pytest.raises(ValueError, match="null"):
        import_catalog(db, path)
    row["value"] = None
    path.write_text(json.dumps(catalog("properties", [row, row])), encoding="utf8")
    with pytest.raises(ValueError, match="duplicate"):
        import_catalog(db, path)


def test_coverage_supported_and_missing_property(sample):
    from test_r1_features import payload

    props = catalog(
        "properties",
        [
            {"element": "Cu", "property": name, "unit": unit, "state": "available", "value": 1}
            for name, unit in (("pauling_electronegativity", "1"), ("covalent_radius", "pm"))
        ],
    )
    mappings = catalog(
        "species", [{"species": "Cu", "state": "supported", "centers": {"Cu": 1}, "evidence": "x"}]
    )
    content = {"records": [{"record_id": "r", "payload": payload(sample)}]}
    sha = digest(content)
    snapshot = {"content": content, "content_sha256": sha, "snapshot_id": "snapshot-" + sha}
    p, s = {"catalog": props, "sha256": "p"}, {"catalog": mappings, "sha256": "s"}
    assert coverage(snapshot, p, s)["supported"] == 1
    props["entries"].pop()
    result = coverage(snapshot, p, s)
    assert result["supported"] == 0
    assert result["records"][0]["reasons"] == ["missing_property:Cu:covalent_radius"]


def test_species_v2_stoichiometry_and_v1_compatibility():
    row = {
        "species": "CoGa0.5AlO4",
        "state": "supported",
        "centers": {"Co": 1, "Ga": 0.5},
        "elements": {"Co": 1, "Ga": 0.5, "Al": 1, "O": 4},
        "formula_unit_basis": "reported formula unit",
        "evidence": "reviewed example",
    }
    data = catalog("species", [row])
    data["schema_version"] = 2

    def encode():
        return json.dumps(data).encode()

    assert parse_catalog(encode())["entries"][0]["centers"]["Ga"] == 0.5
    row["centers"]["Ga"] = 2
    with pytest.raises(ValueError, match="exceed"):
        parse_catalog(encode())
    row["centers"]["Ga"] = float("inf")
    with pytest.raises(ValueError):
        parse_catalog(encode())
    old = catalog(
        "species", [{"species": "Cu", "state": "supported", "centers": {"Cu": 1}, "evidence": "x"}]
    )
    assert parse_catalog(json.dumps(old).encode())["schema_version"] == 1
