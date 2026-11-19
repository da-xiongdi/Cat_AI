"""Standalone S2 training configuration validation; does not execute training."""

import json
import math
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from catalyst_ai.datasets.split import normalize_doi
from catalyst_ai.reporting.evidence import digest


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Dataset(StrictModel):
    snapshot: str
    qualification: str
    split: str
    selection: str
    features: str
    catalog_database: str
    evidence_root: str


class Features(StrictModel):
    preset: Literal["R1", "R2"] = "R2"
    sets: list[Literal["F_cond", "F_base", "F1", "F2"]] = ["F_base", "F1", "F2"]
    property_version: str
    species_mapping_version: str

    @field_validator("sets")
    @classmethod
    def unique_sets(cls, value):
        if not value or len(value) != len(set(value)):
            raise ValueError("feature sets must be nonempty and unique")
        return value


class Model(StrictModel):
    name: Literal["dummy", "ridge", "extra_trees"]
    params: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_params(self):
        allowed = {
            "dummy": set(),
            "ridge": {"alpha"},
            "extra_trees": {
                "n_estimators",
                "min_samples_leaf",
                "max_depth",
                "max_features",
                "n_jobs",
            },
        }
        if set(self.params) - allowed[self.name]:
            raise ValueError("unknown or forbidden model parameter")
        for key, value in self.params.items():
            if key in {"n_estimators", "min_samples_leaf", "n_jobs", "max_depth"}:
                if key == "max_depth" and value is None:
                    continue
                if type(value) is not int or value < 1 or (key == "n_jobs" and value > 8):
                    raise ValueError(f"invalid {key}")
            elif key == "alpha":
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    raise ValueError("alpha must be finite and nonnegative")
            elif key == "max_features":
                if value is None or value in ("sqrt", "log2"):
                    continue
                if type(value) is int and value >= 1:
                    continue
                if type(value) is float and math.isfinite(value) and 0 < value <= 1:
                    continue
                raise ValueError("invalid max_features")
        return self


class Validation(StrictModel):
    strategy: Literal["group_kfold"] = "group_kfold"
    group: Literal["doi"] = "doi"
    n_splits: StrictInt = Field(default=3, ge=2)


class TrainingConfig(StrictModel):
    schema_version: Literal[1] = 1
    mode: Literal["baseline_compare", "custom_train"] = "baseline_compare"
    dataset: Dataset
    features: Features
    models: list[Model] = Field(
        default_factory=lambda: [Model(name=n) for n in ("dummy", "extra_trees", "ridge")]
    )
    validation: Validation = Field(default_factory=Validation)
    seed: StrictInt = Field(default=42, ge=0, le=4294967295)
    output: str

    @field_validator("output")
    @classmethod
    def nonempty_output(cls, value):
        if not value.strip():
            raise ValueError("output must be a nonempty path")
        return value

    @model_validator(mode="after")
    def check_mode(self):
        names = [m.name for m in self.models]
        if not names or len(names) != len(set(names)):
            raise ValueError("models must be nonempty and unique")
        if self.mode == "baseline_compare":
            expected = {"R1": ["F_cond", "F_base"], "R2": ["F_base", "F1", "F2"]}
            if (
                names != ["dummy", "extra_trees", "ridge"]
                or any(
                    any(DEFAULT_PARAMS[m.name][k] != v for k, v in m.params.items())
                    for m in self.models
                )
                or self.seed != 42
                or self.validation.n_splits != 3
                or self.features.sets != expected[self.features.preset]
            ):
                raise ValueError(
                    "baseline_compare requires fixed models, defaults, seed, folds and preset"
                )
        return self


DEFAULT_PARAMS = {
    "dummy": {},
    "ridge": {"alpha": 1.0},
    "extra_trees": {
        "n_estimators": 100,
        "min_samples_leaf": 2,
        "max_depth": None,
        "max_features": 1.0,
        "n_jobs": 1,
    },
}


def catalog():
    return {
        "models": DEFAULT_PARAMS,
        "features": ["F_cond", "F_base", "F1", "F2"],
        "parameter_rules": {
            "alpha": "finite number >= 0",
            "n_estimators": "integer >= 1",
            "min_samples_leaf": "integer >= 1",
            "max_depth": "null or integer >= 1",
            "max_features": "null, sqrt, log2, positive integer or float in (0, 1]",
            "n_jobs": "integer 1..8",
            "seed": "integer 0..4294967295",
        },
    }


def load_config(path):
    """Load YAML or JSON, reject duplicates, and validate dependencies without writing."""

    class UniqueLoader(yaml.SafeLoader):
        pass

    def mapping(loader, node):
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node)
            if key in result:
                raise ValueError(f"duplicate field: {key}")
            result[key] = loader.construct_object(value_node)
        return result

    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    path = Path(path).resolve()
    config = TrainingConfig.model_validate(
        yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)
    )
    base = path.parent
    docs = {}
    for name in ("snapshot", "qualification", "split", "selection", "features"):
        value = getattr(config.dataset, name)
        file = (base / value).resolve()
        if not file.is_file():
            raise ValueError(f"missing {name}: {file}; import or calculate the dependency first")
        docs[name] = json.loads(file.read_text(encoding="utf-8"))
        if digest(docs[name].get("content")) != docs[name].get("content_sha256"):
            raise ValueError(f"{name} content hash mismatch")
    snapshot, qualification, split = (docs[k] for k in ("snapshot", "qualification", "split"))
    from catalyst_ai.features.pipeline import select_inputs

    select_inputs(snapshot, qualification, split)
    selection, features = docs["selection"], docs["features"]
    binding = selection["content"]["binding"]
    if (
        binding != features["content"]["binding"]
        or features["content"]["selection_id"] != selection["selection_id"]
        or binding["snapshot_id"] != snapshot["snapshot_id"]
        or binding["qualification_id"] != qualification["qualification_id"]
        or binding["split_id"] != split["split_id"]
        or binding["property_version"] != config.features.property_version
        or binding["mapping_version"] != config.features.species_mapping_version
    ):
        raise ValueError("feature binding mismatch")
    # Replay the accepted build, including external evidence and implementation hashes.
    # This catches altered catalogs, selections, derived values and code together.
    from catalyst_ai.features.build import build
    from catalyst_ai.storage.feature_catalog import get_catalog, get_evidence

    database = (base / config.dataset.catalog_database).resolve()
    root = (base / config.dataset.evidence_root).resolve()
    if not database.is_file() or not root.is_dir():
        raise ValueError("missing catalog database or evidence root; import dependencies first")
    try:
        properties = get_catalog(database, "properties", binding["property_version"])
        species = get_catalog(database, "species", binding["mapping_version"])
        review = get_evidence(database, binding["review_version"])
        replay = build(snapshot, qualification, split, properties, species, review, root=root)
    except (FileNotFoundError, KeyError) as error:
        raise ValueError(f"missing dependency; import or calculate it first: {error}") from error
    if replay != (selection, features):
        raise ValueError("feature build replay or binding mismatch")
    records = {r["record_id"]: r for r in snapshot["content"]["records"]}
    ids = selection["content"]["retained"]["train"]
    if not set(ids) <= set(split["content"]["splits"]["train"]["record_ids"]):
        raise ValueError("selection contains records outside training split")
    groups = {normalize_doi(records[i]["payload"]["source"]["doi"]) for i in ids}
    if None in groups or len(groups) < config.validation.n_splits:
        raise ValueError("insufficient valid training DOI groups for requested folds")
    if (base / config.output).exists():
        raise ValueError("output must be a new path")
    effective = config.model_dump()

    def source_tree(obj, inherited_default=False):
        if isinstance(obj, BaseModel):
            result = {}
            for name in type(obj).model_fields:
                value = getattr(obj, name)
                is_default = inherited_default or name not in obj.model_fields_set
                if isinstance(value, BaseModel):
                    result[name] = source_tree(value, is_default)
                elif isinstance(value, list) and value and isinstance(value[0], BaseModel):
                    result[name] = [source_tree(item, is_default) for item in value]
                else:
                    result[name] = "default" if is_default else "user"
            return result
        return "user"

    config_sources = source_tree(config)
    sources = {}
    for model in effective["models"]:
        supplied = model["params"]
        model["params"] = {**DEFAULT_PARAMS[model["name"]], **supplied}
        sources[model["name"]] = {
            k: "user" if k in supplied else "default" for k in model["params"]
        }
    return {
        "effective_config": effective,
        "parameter_sources": sources,
        "config_sources": config_sources,
        "training_doi_groups": len(groups),
    }
