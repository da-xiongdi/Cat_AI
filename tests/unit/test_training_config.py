from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from catalyst_ai.modeling.config import Model, TrainingConfig, catalog, load_config

ROOT = Path(__file__).resolve().parents[2]


def test_parameter_validation():
    assert Model(name="ridge", params={"alpha": 2.0}).params["alpha"] == 2
    for name, params in [
        ("ridge", {"alpha": float("nan")}),
        ("extra_trees", {"n_jobs": -1}),
        ("extra_trees", {"random_state": 3}),
        ("dummy", {"strategy": "median"}),
    ]:
        with pytest.raises(ValidationError):
            Model(name=name, params=params)
    assert catalog()["models"]["extra_trees"]["n_jobs"] == 1


def test_unknown_and_duplicate_configuration():
    data = yaml.safe_load((ROOT / "configs/s2_custom.example.yaml").read_text(encoding="utf-8-sig"))
    data["unexpected"] = True
    with pytest.raises(ValidationError):
        TrainingConfig.model_validate(data)
    del data["unexpected"]
    data["models"] = [{"name": "unknown"}]
    with pytest.raises(ValidationError):
        TrainingConfig.model_validate(data)
    data["models"] = [{"name": "ridge"}, {"name": "ridge"}]
    with pytest.raises(ValidationError):
        TrainingConfig.model_validate(data)


def test_baseline_cannot_override_parameters():
    data = {
        "dataset": {
            k: "missing"
            for k in (
                "snapshot",
                "qualification",
                "split",
                "selection",
                "features",
                "catalog_database",
                "evidence_root",
            )
        },
        "features": {"property_version": "v", "species_mapping_version": "v"},
        "output": "new",
        "models": [{"name": "ridge", "params": {"alpha": 2}}],
    }
    with pytest.raises(ValidationError):
        TrainingConfig.model_validate(data)
    data["mode"] = "custom_train"
    assert TrainingConfig.model_validate(data).models[0].name == "ridge"


@pytest.mark.parametrize("name", ["baseline", "custom"])
def test_real_examples(name, tmp_path):
    path = ROOT / "configs" / f"s2_{name}.example.yaml"
    if not (ROOT / "data/catalog.sqlite").exists():
        pytest.skip("local S1 evidence not installed")
    data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    for key, value in data["dataset"].items():
        data["dataset"][key] = str((path.parent / value).resolve())
    data["output"] = str(tmp_path / "run")
    test_config = tmp_path / "config.yaml"
    test_config.write_text(yaml.safe_dump(data), encoding="utf-8")
    result = load_config(test_config)
    assert result["training_doi_groups"] == 26
    assert not (tmp_path / "run").exists()
    if name == "custom":
        assert result["parameter_sources"]["ridge"]["alpha"] == "user"
        assert result["parameter_sources"]["extra_trees"]["min_samples_leaf"] == "default"


def test_duplicate_yaml_and_missing_dependencies(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("mode: custom_train\nmode: baseline_compare\n", encoding="utf8")
    with pytest.raises(ValueError, match="duplicate"):
        load_config(path)
    source = yaml.safe_load(
        (ROOT / "configs/s2_custom.example.yaml").read_text(encoding="utf-8-sig")
    )
    source["dataset"]["snapshot"] = "absent.json"
    path.write_text(yaml.safe_dump(source), encoding="utf8")
    with pytest.raises(ValueError, match="missing snapshot"):
        load_config(path)


def test_fold_limit_and_tampered_build(tmp_path):
    if not (ROOT / "data/catalog.sqlite").exists():
        pytest.skip("local S1 evidence not installed")
    data = yaml.safe_load((ROOT / "configs/s2_custom.example.yaml").read_text(encoding="utf-8-sig"))
    for key, value in data["dataset"].items():
        data["dataset"][key] = str((ROOT / "configs" / value).resolve())
    data["output"] = str(tmp_path / "new-output")
    data["validation"]["n_splits"] = 27
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf8")
    with pytest.raises(ValueError, match="insufficient"):
        load_config(path)
    data["validation"]["n_splits"] = 3
    selection = tmp_path / "selection.json"
    selection.write_text('{"content": {}, "content_sha256": "forged"}', encoding="utf8")
    data["dataset"]["selection"] = str(selection)
    path.write_text(yaml.safe_dump(data), encoding="utf8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_config(path)
