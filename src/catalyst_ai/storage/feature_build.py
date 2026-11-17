"""Immutable S1-B build and per-record derived-value storage."""

import json
import sqlite3

from catalyst_ai.reporting.evidence import canonical, digest


def persist(database, selection, features):
    if digest(selection["content"]) != selection["content_sha256"]:
        raise ValueError("selection hash mismatch")
    if digest(features["content"]) != features["content_sha256"]:
        raise ValueError("feature snapshot hash mismatch")
    if features["content"]["selection_id"] != selection["selection_id"]:
        raise ValueError("selection binding mismatch")
    if selection["selection_id"] != "selection-" + selection["content_sha256"] or (
        features["feature_snapshot_id"] != "features-" + features["content_sha256"]
    ):
        raise ValueError("artifact identity mismatch")
    with sqlite3.connect(database) as con:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute(
            "CREATE TABLE IF NOT EXISTS feature_build_s1b (id TEXT PRIMARY KEY, "
            "selection TEXT NOT NULL, snapshot TEXT NOT NULL)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS feature_value_s1b ("
            "build_id TEXT NOT NULL REFERENCES feature_build_s1b(id), "
            "record_id TEXT NOT NULL, name TEXT NOT NULL, value REAL, state TEXT NOT NULL, "
            "PRIMARY KEY(build_id, record_id, name))"
        )
        key = features["feature_snapshot_id"]
        encoded = (canonical(selection), canonical(features))
        old = con.execute(
            "SELECT selection, snapshot FROM feature_build_s1b WHERE id=?", (key,)
        ).fetchone()
        if old:
            if old != encoded:
                raise ValueError("conflicting feature build")
            expected = sorted(
                (r["record_id"], name, v["value"], v["state"])
                for r in features["content"]["rows"]
                for name, v in r["derived"].items()
            )
            actual = con.execute(
                "SELECT record_id,name,value,state FROM feature_value_s1b "
                "WHERE build_id=? ORDER BY record_id,name",
                (key,),
            ).fetchall()
            if actual != expected:
                raise ValueError("derived value index mismatch")
            return
        con.execute("INSERT INTO feature_build_s1b VALUES (?,?,?)", (key, *encoded))
        con.executemany(
            "INSERT INTO feature_value_s1b VALUES (?,?,?,?,?)",
            (
                (key, row["record_id"], name, value["value"], value["state"])
                for row in features["content"]["rows"]
                for name, value in row["derived"].items()
            ),
        )


def get_build(database, key):
    with sqlite3.connect(database) as con:
        row = con.execute(
            "SELECT selection,snapshot FROM feature_build_s1b WHERE id=?", (key,)
        ).fetchone()
    if row is None:
        raise ValueError("unknown feature build")
    selection, features = (json.loads(value) for value in row)
    if features.get("feature_snapshot_id") != key:
        raise ValueError("stored feature identity mismatch")
    persist(database, selection, features)
    return selection, features
