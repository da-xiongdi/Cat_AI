"""Immutable, source-backed property and species mapping catalogs for S1.

Catalogs are explicit JSON evidence packages, not inferred chemical formulae.
"""

import hashlib
import json
import math
import re
import sqlite3
from pathlib import Path

from catalyst_ai.features.pipeline import project
from catalyst_ai.features.stoichiometry import formula_counts
from catalyst_ai.reporting.evidence import digest
from catalyst_ai.sources.files import strict_json

_UNITS = {"pauling_electronegativity": "1", "covalent_radius": "pm"}
_ELEMENTS = set(
    (
        "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn "
        "Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La "
        "Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi "
        "Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt "
        "Ds Rg Cn Nh Fl Mc Lv Ts Og"
    ).split()
)


def _text(value, field):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"invalid {field}")
    return value


def _keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"expected fields: {', '.join(expected)}")


def parse_catalog(raw):
    obj = strict_json(raw.decode("utf-8-sig"))
    _keys(obj, ("schema_version", "kind", "version", "source", "entries"))
    if type(obj["schema_version"]) is not int or obj["schema_version"] not in (1, 2):
        raise ValueError("unsupported catalog schema")
    if obj["kind"] not in ("properties", "species"):
        raise ValueError("unsupported catalog schema or kind")
    if obj["schema_version"] == 2 and obj["kind"] != "species":
        raise ValueError("schema version 2 is only supported for species")
    _text(obj["version"], "version")
    source = obj["source"]
    _keys(source, ("name", "reference", "license", "evidence"))
    for key, value in source.items():
        _text(value, key)
    if not isinstance(obj["entries"], list) or not obj["entries"]:
        raise ValueError("entries must be a nonempty list")
    seen = set()
    for row in obj["entries"]:
        if obj["kind"] == "properties":
            _keys(row, ("element", "property", "unit", "state", "value"))
            if row["element"] not in _ELEMENTS or row["property"] not in _UNITS:
                raise ValueError("unsupported element or property")
            if row["unit"] != _UNITS[row["property"]]:
                raise ValueError("property unit mismatch")
            key = (row["element"], row["property"])
            state, value = row["state"], row["value"]
            if state == "available":
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or value <= 0
                ):
                    raise ValueError("available property must be finite and positive")
            elif state not in ("unknown", "not_applicable") or value is not None:
                raise ValueError("unknown or not_applicable must have null value")
        else:
            fields = ("species", "state", "centers", "evidence")
            if obj["schema_version"] == 2:
                fields += ("elements", "formula_unit_basis")
            _keys(row, fields)
            species = _text(row["species"], "species")
            if not re.fullmatch(r"[A-Za-z0-9().+/_-]{1,80}", species):
                raise ValueError("invalid species")
            _text(row["evidence"], "mapping evidence")
            key = species
            centers = row["centers"]
            if not isinstance(centers, dict):
                raise ValueError("centers must be an object")
            if obj["schema_version"] == 2:
                elements = row["elements"]
                _text(row["formula_unit_basis"], "formula unit basis")
                if not isinstance(elements, dict):
                    raise ValueError("elements must be an object")
                for counts in (elements, centers):
                    if any(
                        e not in _ELEMENTS
                        or isinstance(n, bool)
                        or not isinstance(n, (int, float))
                        or not math.isfinite(n)
                        or n <= 0
                        for e, n in counts.items()
                    ):
                        raise ValueError("invalid stoichiometric counts")
                if any(e not in elements or n > elements[e] for e, n in centers.items()):
                    raise ValueError("center counts exceed element counts")
            if row["state"] == "supported":
                if not centers or any(
                    e not in _ELEMENTS
                    or isinstance(n, bool)
                    or not isinstance(n, (int, float))
                    or not math.isfinite(n)
                    or n <= 0
                    or (obj["schema_version"] == 1 and not isinstance(n, int))
                    for e, n in centers.items()
                ):
                    raise ValueError("invalid center counts")
            elif row["state"] != "unsupported" or centers:
                raise ValueError("unsupported mapping must have empty centers")
            if obj["schema_version"] == 2 and row["state"] == "supported" and not elements:
                raise ValueError("supported mapping requires element counts")
            if obj["schema_version"] == 2 and elements != formula_counts(species):
                raise ValueError("element counts must match the unscaled formula unit")
        if key in seen:
            raise ValueError(f"duplicate catalog identity: {key}")
        seen.add(key)
    return obj


def migrate(database):
    """Add catalog table to an existing database without modifying existing tables."""
    database = Path(database)
    if not database.is_file():
        raise ValueError("database does not exist")
    with sqlite3.connect(database) as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS feature_catalog (kind TEXT NOT NULL, "
            "version TEXT NOT NULL, sha256 TEXT NOT NULL, original BLOB NOT NULL, "
            "PRIMARY KEY(kind, version))"
        )
        columns = [r[1] for r in con.execute("PRAGMA table_info(feature_catalog)")]
        if columns != ["kind", "version", "sha256", "original"]:
            raise ValueError("incompatible feature_catalog table")
        con.execute(
            "CREATE TABLE IF NOT EXISTS feature_catalog_entry (kind TEXT NOT NULL, "
            "version TEXT NOT NULL, identity TEXT NOT NULL, entry_json TEXT NOT NULL, "
            "PRIMARY KEY(kind, version, identity), FOREIGN KEY(kind, version) "
            "REFERENCES feature_catalog(kind, version))"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS feature_evidence (version TEXT PRIMARY KEY, "
            "sha256 TEXT NOT NULL, original BLOB NOT NULL)"
        )
        for kind, version, sha, raw in con.execute("SELECT * FROM feature_catalog").fetchall():
            if hashlib.sha256(raw).hexdigest() != sha:
                raise ValueError("catalog content hash mismatch")
            catalog = parse_catalog(raw)
            if (catalog["kind"], catalog["version"]) != (kind, version):
                raise ValueError("catalog identity mismatch")
            _index_catalog(con, catalog)
        if con.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("database foreign key check failed")
        return con.execute("PRAGMA integrity_check").fetchone()[0]


def _identity(kind, row):
    return row["species"] if kind == "species" else row["element"] + ":" + row["property"]


def _index_catalog(con, catalog):
    for row in catalog["entries"]:
        identity = _identity(catalog["kind"], row)
        encoded = json.dumps(row, sort_keys=True, allow_nan=False)
        old = con.execute(
            "SELECT entry_json FROM feature_catalog_entry "
            "WHERE kind=? AND version=? AND identity=?",
            (catalog["kind"], catalog["version"], identity),
        ).fetchone()
        if old and old[0] != encoded:
            raise ValueError("catalog entry conflict")
        if not old:
            con.execute(
                "INSERT INTO feature_catalog_entry VALUES (?, ?, ?, ?)",
                (catalog["kind"], catalog["version"], identity, encoded),
            )


def import_catalog(database, path, *, dry_run=True):
    raw = Path(path).read_bytes()
    catalog = parse_catalog(raw)
    sha = hashlib.sha256(raw).hexdigest()
    database = Path(database)
    if not database.is_file():
        raise ValueError("database does not exist")
    with sqlite3.connect(database) as con:
        exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='feature_catalog'"
        ).fetchone()
        old = (
            con.execute(
                "SELECT sha256, original FROM feature_catalog WHERE kind=? AND version=?",
                (catalog["kind"], catalog["version"]),
            ).fetchone()
            if exists
            else None
        )
        if old and (old[0] != sha or old[1] != raw):
            raise ValueError("catalog version conflict")
        if not dry_run and not exists:
            raise ValueError("run migrate first")
        if not dry_run and not old:
            con.execute(
                "INSERT INTO feature_catalog VALUES (?, ?, ?, ?)",
                (catalog["kind"], catalog["version"], sha, raw),
            )
        if not dry_run:
            _index_catalog(con, catalog)
    return {
        "kind": catalog["kind"],
        "version": catalog["version"],
        "sha256": sha,
        "entries": len(catalog["entries"]),
        "status": "existing" if old else "validated" if dry_run else "imported",
    }


def get_catalog(database, kind, version):
    if not Path(database).is_file():
        raise ValueError("database does not exist")
    with sqlite3.connect(database) as con:
        row = con.execute(
            "SELECT sha256, original FROM feature_catalog WHERE kind=? AND version=?",
            (kind, version),
        ).fetchone()
    if row is None:
        raise ValueError("catalog version not found")
    if hashlib.sha256(row[1]).hexdigest() != row[0]:
        raise ValueError("catalog content hash mismatch")
    catalog = parse_catalog(row[1])
    if (catalog["kind"], catalog["version"]) != (kind, version):
        raise ValueError("catalog identity mismatch")
    return {"sha256": row[0], "catalog": catalog}


def query_entries(database, kind, version, identity=None):
    """Query individual persisted facts and verify them against the immutable package."""
    package = get_catalog(database, kind, version)
    with sqlite3.connect(database) as con:
        rows = con.execute(
            "SELECT identity, entry_json FROM feature_catalog_entry WHERE kind=? AND version=?",
            (kind, version),
        ).fetchall()
    expected = {_identity(kind, r): r for r in package["catalog"]["entries"]}
    actual = {key: json.loads(raw) for key, raw in rows}
    if actual != expected:
        raise ValueError("catalog entry integrity mismatch")
    if identity is not None and identity not in actual:
        raise ValueError("catalog entry not found")
    return {
        "kind": kind,
        "version": version,
        "sha256": package["sha256"],
        "source": package["catalog"]["source"],
        "entries": [actual[k] for k in sorted(actual) if identity is None or k == identity],
    }


def import_evidence(database, path, *, dry_run=True):
    """Persist a validated record-level S1 qualification, separately from mappings."""
    from catalyst_ai.features.qualification import validate_review

    if not Path(database).is_file():
        raise ValueError("database does not exist")
    raw = Path(path).read_bytes()
    obj = strict_json(raw.decode("utf-8-sig"))
    validate_review(obj)
    sha = hashlib.sha256(raw).hexdigest()
    with sqlite3.connect(database) as con:
        old = con.execute(
            "SELECT sha256, original FROM feature_evidence WHERE version=?", (obj["version"],)
        ).fetchone()
        if old and old != (sha, raw):
            raise ValueError("evidence version conflict")
        if not dry_run and not old:
            con.execute("INSERT INTO feature_evidence VALUES (?, ?, ?)", (obj["version"], sha, raw))
    return {
        "version": obj["version"],
        "sha256": sha,
        "status": "existing" if old else "validated" if dry_run else "imported",
    }


def get_evidence(database, version):
    from catalyst_ai.features.qualification import validate_review

    if not Path(database).is_file():
        raise ValueError("database does not exist")
    with sqlite3.connect(database) as con:
        row = con.execute(
            "SELECT sha256, original FROM feature_evidence WHERE version=?", (version,)
        ).fetchone()
    if not row or hashlib.sha256(row[1]).hexdigest() != row[0]:
        raise ValueError("evidence missing or hash mismatch")
    obj = strict_json(row[1].decode("utf-8-sig"))
    validate_review(obj)
    if obj["version"] != version:
        raise ValueError("evidence identity mismatch")
    return {"sha256": row[0], "review": obj}


def coverage(snapshot, properties, species):
    """Report potential R2 input coverage; no derived feature values are calculated."""
    if (
        digest(snapshot["content"]) != snapshot["content_sha256"]
        or snapshot["snapshot_id"] != "snapshot-" + snapshot["content_sha256"]
    ):
        raise ValueError("snapshot identity mismatch")
    if properties["catalog"]["kind"] != "properties" or species["catalog"]["kind"] != "species":
        raise ValueError("catalog kind mismatch")
    props = {(x["element"], x["property"]): x for x in properties["catalog"]["entries"]}
    mappings = {x["species"]: x for x in species["catalog"]["entries"]}
    rows = []
    for record in snapshot["content"]["records"]:
        reasons = []
        try:
            inputs = project(record["payload"])
            for (_, name), amount in inputs["amounts"].items():
                if amount <= 0:
                    continue
                mapping = mappings.get(name)
                if not mapping or mapping["state"] != "supported":
                    reasons.append("unsupported_species:" + name)
                    continue
                for element in mapping["centers"]:
                    for prop in _UNITS:
                        if props.get((element, prop), {}).get("state") != "available":
                            reasons.append(f"missing_property:{element}:{prop}")
        except ValueError as exc:
            reasons.append(str(exc))
        rows.append({"record_id": record["record_id"], "reasons": sorted(set(reasons))})
    return {
        "snapshot_id": snapshot["snapshot_id"],
        "property_sha256": properties["sha256"],
        "mapping_sha256": species["sha256"],
        "total": len(rows),
        "supported": sum(not r["reasons"] for r in rows),
        "records": rows,
    }
