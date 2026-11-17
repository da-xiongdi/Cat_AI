"""Persist and use a bound R1 prediction package. Only load trusted packages."""

import hashlib
import importlib.metadata
import json
import math
import pickle
import platform
from pathlib import Path

from catalyst_ai.features.pipeline import VERSION
from catalyst_ai.reporting.evidence import digest


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def save_package(path, report, fitted):
    if report.get("content_sha256") != digest(
        {k: v for k, v in report.items() if k != "content_sha256"}
    ):
        raise ValueError("comparison report hash mismatch")
    features, model = fitted["features"], fitted["model"]
    if features.feature_set != "F_base" or report["selected"]["feature_set"] != "F_base":
        raise ValueError("unsupported feature set")
    data = pickle.dumps({"features": features, "model": model}, protocol=4)
    metadata = {
        "schema_version": "r1-prediction-package-v1",
        "input_schema": {
            "version": "r1-prediction-input-v1",
            "required": [
                "components",
                "temperature_k",
                "pressure_bar_abs",
                "h2_co2_ratio",
                "reactants_flow_nl_g_h",
            ],
            "component_fields": ["role", "species", "mol_pct"],
            "composition_basis": "whole catalyst material mol%",
            "conditions": {
                "temperature_k": "K",
                "pressure_bar_abs": "bar(abs)",
                "h2_co2_ratio": "H2/CO2 molar ratio",
                "reactants_flow_nl_g_h": (
                    "NL/g_cat/h at 293.15 K and 1.01325 bar(abs), reactants only"
                ),
            },
            "additional_fields": False,
        },
        "feature_version": VERSION,
        "feature_set_id": features.feature_set,
        "model_name": report["selected"]["model"],
        "training_record_ids": report["selection"]["content"]["retained"]["train"],
        "snapshot_id": report["selection"]["content"]["snapshot_id"],
        "report_sha256": report["content_sha256"],
        "target_definition": report.get("target_definition", "CO2 conversion"),
        "target_unit": "%",
        "dependencies": report["dependencies"],
        "feature_implementation_sha256": report["feature_implementation_sha256"],
        "design_implementation_sha256": _sha(
            (Path(__file__).parents[1] / "features" / "design.py").read_bytes()
        ),
        "artifact_sha256": _sha(data),
    }
    metadata["model_id"] = "r1-" + digest(metadata)
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    (path / "model.pkl").write_bytes(data)
    (path / "manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return metadata


def load_package(path):
    path = Path(path)
    metadata = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    identifier = metadata.get("model_id")
    if identifier != "r1-" + digest({k: v for k, v in metadata.items() if k != "model_id"}):
        raise ValueError("manifest hash mismatch")
    data = (path / "model.pkl").read_bytes()
    if _sha(data) != metadata["artifact_sha256"]:
        raise ValueError("model hash mismatch")
    dependencies = {
        "python": platform.python_version(),
        **{n: importlib.metadata.version(n) for n in ("numpy", "scikit-learn")},
    }
    if dependencies != metadata["dependencies"]:
        raise ValueError("dependency version mismatch")
    for name, key in (
        ("pipeline.py", "feature_implementation_sha256"),
        ("design.py", "design_implementation_sha256"),
    ):
        if _sha((Path(__file__).parents[1] / "features" / name).read_bytes()) != metadata[key]:
            raise ValueError("feature implementation hash mismatch")
    if (
        metadata["feature_version"] != VERSION
        or metadata["schema_version"] != "r1-prediction-package-v1"
    ):
        raise ValueError("unsupported package version")
    return metadata, pickle.loads(data)


def _measurement(value, unit):
    return {"state": "reported", "normalized_value": value, "normalized_unit": unit}


def _payload(item):
    if not isinstance(item, dict) or set(item) != {
        "components",
        "temperature_k",
        "pressure_bar_abs",
        "h2_co2_ratio",
        "reactants_flow_nl_g_h",
    }:
        raise ValueError("expected components and four condition fields")
    components = item["components"]
    if not isinstance(components, list):
        raise ValueError("components must be a list")
    converted = []
    for component in components:
        if not isinstance(component, dict) or set(component) != {"role", "species", "mol_pct"}:
            raise ValueError("component requires role, species and mol_pct")
        converted.append(
            {
                "role": component["role"],
                "species": component["species"],
                "amount": _measurement(component["mol_pct"], "%"),
            }
        )
    return {
        "recipe": {
            "composition_basis": "mol_pct",
            "composition_scope": "whole catalyst material",
            "components": converted,
        },
        "test": {
            "temperature": _measurement(item["temperature_k"], "K"),
            "pressure": _measurement(item["pressure_bar_abs"], "bar(abs)"),
            "pressure_type": "absolute",
            "reactant_ratio": {
                "numerator": "H2",
                "denominator": "CO2",
                "value": _measurement(item["h2_co2_ratio"], "1"),
            },
            "mass_normalized_volume_flow": {
                "mass_basis": "catalyst",
                "gas_scope": "reactants_only",
                "reference_temperature": _measurement(293.15, "K"),
                "reference_pressure": _measurement(1.01325, "bar(abs)"),
                "reference_pressure_type": "absolute",
                "value": _measurement(item["reactants_flow_nl_g_h"], "NL/g_cat/h"),
            },
        },
    }


def predict_one(package, item):
    metadata, fitted = package
    result = {
        "status": "invalid_input",
        "co2_conversion_pct": None,
        "raw_prediction": None,
        "target_definition": metadata["target_definition"],
        "unit": "%",
        "model_id": metadata["model_id"],
        "feature_set_id": metadata["feature_set_id"],
        "validation": [],
        "unseen_species_roles": [],
        "out_of_range": [],
        "limitations": [
            "Source acceptance does not imply row-by-row verification.",
            "Pressure is assumed absolute.",
            "Training ranges do not establish a validated applicability domain; "
            "extrapolation is limited.",
        ],
    }
    try:
        transformed = fitted["features"].transform_one(_payload(item))
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        result["validation"] = [str(error)]
        return result
    result.update({k: transformed[k] for k in ("status", "unseen_species_roles", "out_of_range")})
    if transformed["values"] is None:
        result["validation"] = ["unsupported_species_role"]
        return result
    value = float(fitted["model"].predict([transformed["values"]])[0])
    if not math.isfinite(value):
        result.update(status="nonfinite_prediction", validation=["nonfinite_prediction"])
    elif not 0 <= value <= 100:
        result.update(
            status="output_out_of_range", raw_prediction=value, validation=["output_out_of_range"]
        )
    else:
        result.update(co2_conversion_pct=value, raw_prediction=value)
    return result


def predict_batch(package, items):
    return [predict_one(package, item) for item in items]
