"""Read-only source inspection for explicitly registered workbench artifacts."""

import hashlib
import json
from pathlib import Path

from catalyst_ai.reporting.evidence import digest
from catalyst_ai.sources.files import strict_json

KINDS = {
    "snapshot",
    "qualification",
    "split",
    "selection",
    "features",
    "report",
    "model",
    "document",
    "attachment",
}
CONTENT_IDS = {
    "snapshot": ("snapshot_id", "snapshot-"),
    "qualification": ("qualification_id", "qualification-"),
    "split": ("split_id", "split-"),
    "selection": ("selection_id", "selection-"),
    "features": ("feature_snapshot_id", "features-"),
}


class InvalidArtifact(ValueError):
    pass


def safe_path(root, relative):
    root = Path(root).resolve(strict=True)
    p = Path(relative)
    if p.is_absolute() or p.drive or not p.parts or ".." in p.parts:
        raise ValueError("path must be relative to the workspace")
    result = (root / p).resolve()
    if not result.is_relative_to(root):
        raise ValueError("path escapes workspace")
    return result


def read_limited(path, limit):
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise InvalidArtifact("file exceeds size limit")
    return data


def inspect(root, relative, kind, max_bytes):
    if kind not in KINDS:
        raise ValueError("unknown artifact kind")
    path = safe_path(root, relative)
    raw = read_limited(path, max_bytes)
    sha = hashlib.sha256(raw).hexdigest()
    meta = {"size": len(raw)}
    content_id = content_hash = None
    if kind in CONTENT_IDS or kind in {"report", "model"}:
        try:
            obj = strict_json(raw.decode("utf-8-sig"))
            if not isinstance(obj, dict):
                raise ValueError("expected JSON object")
            if kind in CONTENT_IDS:
                id_key, prefix = CONTENT_IDS[kind]
                content_hash = digest(obj["content"])
                content_id = obj[id_key]
                if content_hash != obj["content_sha256"] or content_id != prefix + content_hash:
                    raise ValueError("content hash or identity mismatch")
                content = obj["content"]
                meta["binding"] = content.get("binding", {})
                meta["version"] = content.get("version", content.get("schema_version"))
                if kind == "features":
                    meta["rows"] = len(content["rows"])
                    meta["selection_id"] = content["selection_id"]
                if kind == "selection":
                    meta["retained"] = {k: len(v) for k, v in content["retained"].items()}
                if kind == "snapshot":
                    meta["records"] = len(content["records"])
                    meta["target"] = content.get("target")
                if kind == "split":
                    meta["snapshot_id"] = content.get("snapshot_id")
            elif kind == "report":
                content_hash = digest({k: v for k, v in obj.items() if k != "content_sha256"})
                if obj.get("content_sha256") != content_hash:
                    raise ValueError("report content hash mismatch")
                content_id = "report-" + content_hash
                meta.update(
                    {
                        k: obj.get(k)
                        for k in ("schema_version", "feature_version", "limitations", "selected")
                    }
                )
                if obj.get("schema_version") == "r1-oof-comparison-v1":
                    selected = obj["selected"]
                    feature = selected["feature_set"]
                    model_name = selected["model"]
                    meta["r1_summary"] = {
                        "selection": selected,
                        "binding": {
                            k: obj["selection"]["content"].get(k)
                            for k in ("snapshot_id", "qualification_id", "split_id", "counts")
                        },
                        "configuration": obj["configuration"],
                        "oof_metrics": obj["oof_scores"][feature][model_name],
                        "oof_availability": obj["oof_availability"][feature][model_name],
                        "partitions": {
                            part: {
                                key: obj[part]["candidates"][feature][key]
                                for key in ("metrics", "availability")
                            }
                            for part in ("validation", "test")
                        },
                    }
            else:
                content_id = obj["model_id"]
                content_hash = digest({k: v for k, v in obj.items() if k != "model_id"})
                if content_id != "r1-" + content_hash:
                    raise ValueError("model manifest identity mismatch")
                model = safe_path(root, str(Path(relative).parent / "model.pkl"))
                model_bytes = read_limited(model, max_bytes)
                if hashlib.sha256(model_bytes).hexdigest() != obj["artifact_sha256"]:
                    raise ValueError("model file hash mismatch")
                meta.update(
                    {
                        k: obj.get(k)
                        for k in (
                            "schema_version",
                            "snapshot_id",
                            "report_sha256",
                            "feature_version",
                            "model_name",
                            "target_definition",
                            "target_unit",
                            "artifact_sha256",
                        )
                    }
                )
                meta["model_path"] = str(Path(relative).parent / "model.pkl")
        except (ValueError, KeyError, TypeError, UnicodeError) as exc:
            raise InvalidArtifact(str(exc)) from exc
    else:
        content_id = f"{kind}-{sha}"
    return {
        "file_sha256": sha,
        "content_id": content_id,
        "content_sha256": content_hash,
        "metadata": meta,
    }


def verify_feature_catalog(database, selection_path, features_path, *, max_bytes=64 * 1024 * 1024):
    """Compare a fixed S1-B build with its existing SQLite index without any writes."""
    import sqlite3

    selection = strict_json(read_limited(Path(selection_path), max_bytes).decode("utf-8-sig"))
    features = strict_json(read_limited(Path(features_path), max_bytes).decode("utf-8-sig"))
    for obj, key, prefix in (
        (selection, "selection_id", "selection-"),
        (features, "feature_snapshot_id", "features-"),
    ):
        value = digest(obj["content"])
        if obj["content_sha256"] != value or obj[key] != prefix + value:
            raise InvalidArtifact("feature build identity mismatch")
    if features["content"]["selection_id"] != selection["selection_id"]:
        raise InvalidArtifact("selection binding mismatch")
    uri = Path(database).resolve(strict=True).as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        row = db.execute(
            "SELECT selection,snapshot FROM feature_build_s1b WHERE id=?",
            (features["feature_snapshot_id"],),
        ).fetchone()
        if not row or json.loads(row[0]) != selection or json.loads(row[1]) != features:
            raise InvalidArtifact("catalog build mismatch")
        actual = db.execute(
            "SELECT record_id,name,value,state FROM feature_value_s1b "
            "WHERE build_id=? ORDER BY record_id,name",
            (features["feature_snapshot_id"],),
        ).fetchall()
    expected = sorted(
        (r["record_id"], name, v["value"], v["state"])
        for r in features["content"]["rows"]
        for name, v in r["derived"].items()
    )
    if actual != expected:
        raise InvalidArtifact("catalog derived values mismatch")
    return {
        "feature_snapshot_id": features["feature_snapshot_id"],
        "selection_id": selection["selection_id"],
        "rows": len(features["content"]["rows"]),
        "values": len(expected),
    }
