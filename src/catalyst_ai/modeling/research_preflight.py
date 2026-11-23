"""Read-only validation for the first frozen research dataset contract."""

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from catalyst_ai.datasets.split import normalize_doi
from catalyst_ai.modeling.config import Model
from catalyst_ai.reporting.evidence import digest


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    feature: Literal["F_cond", "F_base", "F1", "F2"]
    model: Literal["dummy", "ridge", "extra_trees"]
    params: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_model(self):
        Model.model_validate({"name": self.model, "params": self.params})
        return self


class ResearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    view: str
    snapshot: str
    split: str
    split_sha256: str
    target: str = Field(default="co2_conversion", min_length=1)
    catalog_database: str = "data/catalog.sqlite"
    candidates: list[Candidate] = Field(min_length=1)
    model_seed: int = Field(default=42, ge=0, le=4294967295)
    metrics: list[Literal["mae", "rmse", "r2", "availability"]] = Field(
        default_factory=lambda: ["mae", "rmse", "r2", "availability"], min_length=1
    )
    outputs: list[Literal["predictions", "plots"]] = Field(
        default_factory=lambda: ["predictions", "plots"]
    )

    @model_validator(mode="after")
    def unique_options(self):
        if len(self.metrics) != len(set(self.metrics)) or len(self.outputs) != len(
            set(self.outputs)
        ):
            raise ValueError("duplicate metrics or outputs")
        if "mae" not in self.metrics:
            raise ValueError("mae is required for model selection")
        return self


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError(f"duplicate JSON field: {key}")
            out[key] = value
        return out

    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=pairs)


def preflight(config_path, *, root):
    """Check data lineage, locked split, grouping and candidates without fitting."""
    root = Path(root).resolve()
    config = ResearchConfig.model_validate(read_json(Path(config_path)))
    view_path, snapshot_path, split_path = [
        (root / name).resolve() for name in (config.view, config.snapshot, config.split)
    ]
    view, snapshot, split = [read_json(p) for p in (view_path, snapshot_path, split_path)]
    vc = view["content"]
    if digest(vc) != view["content_sha256"] or not view["view_id"].endswith(view["content_sha256"]):
        raise ValueError("view identity mismatch")
    if sha(split_path) != config.split_sha256:
        raise ValueError("split hash mismatch")
    if "content_sha256" in split:
        content_hash = digest(
            {k: v for k, v in split.items() if k not in ("split_id", "content_sha256")}
        )
        if (
            split["content_sha256"] != content_hash
            or split.get("split_id") != "research-split-" + content_hash
        ):
            raise ValueError("split identity mismatch")
    if (
        digest(snapshot["content"]) != snapshot["content_sha256"]
        or snapshot["snapshot_id"] != vc["binding"]["parent_snapshot_id"]
        or snapshot["content_sha256"] != vc["binding"]["parent_content_sha256"]
    ):
        raise ValueError("snapshot identity mismatch")
    if snapshot["content"]["target"] != config.target:
        raise ValueError("target mismatch")
    for name, expected in vc["binding"]["sources"].items():
        if sha(root / name) != expected:
            raise ValueError(f"frozen source mismatch: {name}")
    feature_validation = "unbound"
    if vc["binding"].get("selection_id"):
        from catalyst_ai.storage.feature_catalog import get_catalog

        paths = [p for p in vc["binding"]["sources"] if p.endswith("/selection.json")]
        if len(paths) != 1:
            raise ValueError("feature selection binding is ambiguous")
        selection = read_json(root / paths[0])
        binding = selection["content"]["binding"]
        if (
            digest(selection["content"]) != selection["content_sha256"]
            or selection["selection_id"] != vc["binding"]["selection_id"]
            or binding["snapshot_id"] != snapshot["snapshot_id"]
            or binding["snapshot_sha256"] != snapshot["content_sha256"]
        ):
            raise ValueError("feature selection binding mismatch")
        database = root / config.catalog_database
        for kind, version, expected in (
            ("properties", binding["property_version"], binding["property_sha256"]),
            ("species", binding["mapping_version"], binding["mapping_sha256"]),
        ):
            if get_catalog(database, kind, version)["sha256"] != expected:
                raise ValueError(f"feature catalog mismatch: {kind}")
        feature_validation = "verified"
    for name in ("ledger", "distributions"):
        if sha(view_path.parent / f"{name}.json") != vc[f"{name}_sha256"]:
            raise ValueError(f"frozen {name} mismatch")
    if split.get("dataset_view_id") != view["view_id"]:
        raise ValueError("split view mismatch")
    ids = vc["common_record_ids"]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate view members")
    members = set(ids)
    train, test = set(split["train"]), set(split["test"])
    if (
        len(train) != len(split["train"])
        or len(test) != len(split["test"])
        or not train
        or not test
        or train & test
        or train | test != members
    ):
        raise ValueError("invalid train/test membership")
    folds = split["validation_folds"]
    flat = [x for fold in folds for x in fold]
    if (
        len(folds) != split["folds"]
        or len(folds) < 2
        or any(not fold for fold in folds)
        or len(flat) != len(set(flat))
        or set(flat) != train
    ):
        raise ValueError("invalid validation folds")
    ledger = read_json(view_path.parent / "ledger.json")["records"]
    ledger = {r["record_id"]: r for r in ledger}
    repeat_groups = {}
    for i in members:
        if i not in ledger:
            raise ValueError("missing repeat identity")
        row = ledger[i]
        status = row["repeat_identity_status"]
        if status == "no_confirmed_repeat":
            continue
        if status != "confirmed_repeat" or not row.get("confirmed_repeat_group"):
            raise ValueError("unsupported or unresolved repeat identity")
        repeat_groups.setdefault(row["confirmed_repeat_group"], set()).add(i)
    for group in repeat_groups.values():
        if group & train and group & test:
            raise ValueError("repeat group train/test leakage")
        if sum(bool(group & set(fold)) for fold in folds) > 1:
            raise ValueError("repeat group fold leakage")
    rows = {r["record_id"]: r for r in snapshot["content"]["records"]}
    if len(rows) != len(snapshot["content"]["records"]) or not members <= rows.keys():
        raise ValueError("snapshot member mismatch")
    strategy = split["strategy"]
    if strategy not in ("doi", "random", "random_projection"):
        raise ValueError("unsupported split strategy")
    if strategy == "doi":
        doi = {i: normalize_doi(rows[i]["payload"]["source"]["doi"]) for i in members}
        if None in doi.values():
            raise ValueError("missing DOI")
        if {doi[i] for i in train} & {doi[i] for i in test}:
            raise ValueError("DOI train/test leakage")
        for fold in folds:
            held = set(fold)
            if {doi[i] for i in held} & {doi[i] for i in train - held}:
                raise ValueError("DOI fold leakage")
    return {
        "config": config.model_dump(),
        "view": view,
        "snapshot": snapshot,
        "split": split,
        "hashes": {
            "view": sha(view_path),
            "snapshot": sha(snapshot_path),
            "split": sha(split_path),
        },
        "counts": {"train": len(train), "test": len(test), "folds": [len(f) for f in folds]},
        "feature_validation": feature_validation,
    }
