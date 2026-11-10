import csv
import hashlib
import io
from decimal import Decimal, InvalidOperation

from catalyst_ai.sources.files import InputRow

COLUMNS = [
    "reference",
    "doi_link",
    "catalyst_name",
    "catalyst_composition_available",
    "starting_material_active_1",
    "active_comp_1",
    "active_1_percent",
    "starting_material_2",
    "active_comp_2",
    "active_2_percent",
    "support_comp_1",
    "support_1_percent",
    "support_comp_2",
    "support_2_percent",
    "catalyst_surface_area_m2_g",
    "mean_pore_diameter_nm",
    "temperature_k",
    "pressure_bar",
    "pH2_pCO2_ratio",
    "GHSV_nlph_gcat",
    "catalyst_load_g",
    "CO2_conversion",
    "selectivity_CH3OH",
    "yield_CH3OH",
    "STY_g_per_gcath",
]


def adapt(content: bytes):
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
    if reader.fieldnames != COLUMNS:
        raise ValueError("TheMeCat v1 CSV列不匹配，拒绝导入未知版本")
    rows = []
    skipped = 0
    while True:
        start = reader.line_num + 1
        try:
            raw = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            raise ValueError(f"TheMeCat CSV解析失败: {exc}") from exc
        if None in raw or any(v is None for v in raw.values()):
            raise ValueError(f"TheMeCat CSV字段数错误，行{start}")
        if not any(v.strip() for v in raw.values()):
            skipped += 1
            continue
        locator = f"lines:{start}-{reader.line_num}"
        source_key = hashlib.sha256(
            (raw["reference"] + "|" + raw["doi_link"]).encode()
        ).hexdigest()[:20]
        row_key = hashlib.sha256(
            (hashlib.sha256(content).hexdigest() + ":" + str(start)).encode()
        ).hexdigest()[:20]
        eid, rid, sid, tid = (
            f"themecat-{row_key}-{s}" for s in ("extraction", "recipe", "synthesis", "test")
        )

        def measurement(key, unit, raw=raw, eid=eid):
            value = raw[key].strip()
            if not value or value.upper() == "NA":
                return {"state": "unknown"}
            try:
                state = "zero" if Decimal(value) == 0 else "reported"
            except InvalidOperation:
                state = "invalid"
            return {"raw_value": value, "raw_unit": unit, "state": state, "source_locator": eid}

        components = []
        for name, amount, role in [
            ("active_comp_1", "active_1_percent", "compound"),
            ("active_comp_2", "active_2_percent", "compound"),
            ("support_comp_1", "support_1_percent", "support"),
            ("support_comp_2", "support_2_percent", "support"),
        ]:
            species = raw[name].strip()
            if species and species.upper() != "NA":
                components.append(
                    {"species": species, "role": role, "amount": measurement(amount, "%")}
                )
        if not components:
            components = [
                {
                    "species": raw["catalyst_name"].strip() or "unknown",
                    "role": "compound",
                    "amount": {"state": "unknown"},
                }
            ]
        observations = []
        for column, metric, unit in [
            ("CO2_conversion", "co2_conversion", "%"),
            ("selectivity_CH3OH", "methanol_selectivity", "%"),
            ("yield_CH3OH", "methanol_yield", "%"),
            ("STY_g_per_gcath", "methanol_sty", "g_MeOH/g_cat/h"),
        ]:
            observations.append(
                {
                    "observation_id": f"{tid}-{column}",
                    "test_id": tid,
                    "metric": metric,
                    "value": measurement(column, unit),
                }
            )
        props = {
            key: measurement(key, unit)
            for key, unit in [
                ("catalyst_surface_area_m2_g", "m2/g"),
                ("mean_pore_diameter_nm", "nm"),
            ]
        }
        source_id = f"themecat-source-{source_key}"
        doi = raw["doi_link"].strip().removeprefix("https://doi.org/") or None
        payload = {
            "dataset_kind": "research",
            "source": {
                "source_id": source_id,
                "kind": "literature",
                "title": raw["reference"].strip() or "unknown",
                "doi": doi,
                "license": "unknown",
                "access": "TheMeCat v1 via Zenodo CC-BY-4.0; underlying source rights not audited",
            },
            "extraction": {
                "extraction_id": eid,
                "source_id": source_id,
                "locator": f"TheMeCat_v1.csv {locator}",
                "method": "TheMeCat v1 adapter; original paper location not supplied",
                "method_version": "1",
            },
            "recipe": {
                "recipe_id": rid,
                "material_family": raw["catalyst_name"].strip() or "unknown",
                "composition_basis": "unknown",
                "components": components,
            },
            "synthesis": {
                "synthesis_id": sid,
                "recipe_id": rid,
                "precursors": [
                    raw[k].strip()
                    for k in ("starting_material_active_1", "starting_material_2")
                    if raw[k].strip() and raw[k].strip().upper() != "NA"
                ],
            },
            "test": {
                "test_id": tid,
                "synthesis_id": sid,
                "temperature": measurement("temperature_k", "K"),
                "pressure": measurement("pressure_bar", "bar"),
                "pressure_type": "unknown",
                "ghsv": measurement("GHSV_nlph_gcat", "NL/g_cat/h"),
                "feed_basis": "unknown",
                "catalyst_mass": measurement("catalyst_load_g", "g"),
            },
            "observations": observations,
            "characterizations": [
                {
                    "characterization_id": f"{sid}-characterization",
                    "synthesis_id": sid,
                    "technique": "unspecified in TheMeCat CSV",
                    "properties": {**props},
                }
            ],
        }
        rows.append(InputRow(locator, payload, raw_payload=raw))
    return rows, skipped


def adapt_v2(content: bytes):
    """Interpret the same raw rows under the dataset-level v2 semantics."""
    rows, skipped = adapt(content)
    definition_source = "TheMeCat dataset paper: https://doi.org/10.1038/s41597-025-06482-8"
    for row in rows:
        payload, raw = row.payload, row.raw_payload
        payload["schema_version"] = "2"
        payload["extraction"]["method_version"] = "2"
        payload["recipe"]["composition_basis"] = "mol_pct"
        payload["recipe"]["composition_scope"] = "whole catalyst material"
        available = raw["catalyst_composition_available"].strip()
        payload["recipe"]["composition_available_raw"] = raw["catalyst_composition_available"]
        payload["recipe"]["composition_available"] = (
            available.lower() if available.lower() in {"yes", "no"} else "unknown"
        )
        payload["recipe"]["composition_definition_source"] = definition_source
        for component in payload["recipe"]["components"]:
            component["amount"]["provenance"] = {
                "value_source": "dataset CSV",
                "definition_source": definition_source,
            }
        for observation in payload["observations"]:
            observation["value"]["provenance"] = {
                "value_source": "dataset CSV; original measurement or derivation unconfirmed"
            }
        for value in payload["characterizations"][0]["properties"].values():
            value["provenance"] = {"value_source": "dataset CSV; conversion history unconfirmed"}
        payload["test"]["temperature"]["provenance"] = {
            "value_source": "dataset CSV; temperature conversion follows dataset convention",
            "definition_source": definition_source,
        }
        payload["recipe"]["orphan_amount_fields"] = [
            amount
            for species, amount in [
                ("active_comp_1", "active_1_percent"),
                ("active_comp_2", "active_2_percent"),
                ("support_comp_1", "support_1_percent"),
                ("support_comp_2", "support_2_percent"),
            ]
            if raw[species].strip().upper() in {"", "NA"}
            and raw[amount].strip().upper() not in {"", "NA"}
        ]
        synthesis = payload["synthesis"]
        synthesis["initial_materials"] = synthesis.pop("precursors")
        test = payload["test"]
        eid = payload["extraction"]["extraction_id"]
        flow = test.pop("ghsv")
        flow["provenance"] = {"definition_source": definition_source, "value_source": "dataset CSV"}

        def reference(value, unit, eid=eid):
            return {
                "raw_value": value,
                "raw_unit": unit,
                "state": "reported",
                "source_locator": eid,
                "provenance": {"definition_source": definition_source},
            }

        ratio_raw = raw["pH2_pCO2_ratio"].strip()
        if not ratio_raw or ratio_raw.upper() == "NA":
            ratio = {"state": "unknown"}
        else:
            try:
                state = "zero" if Decimal(ratio_raw) == 0 else "reported"
            except InvalidOperation:
                state = "invalid"
            ratio = {
                "raw_value": ratio_raw,
                "raw_unit": "1",
                "state": state,
                "source_locator": eid,
                "provenance": {"value_source": "dataset CSV"},
            }
        test.update(
            {
                "flow_mode": "mass_normalized_reactants",
                "mass_normalized_volume_flow": {
                    "value": flow,
                    "reference_temperature": reference("293.15", "K"),
                    "reference_pressure": reference("101325", "Pa"),
                    "reference_pressure_type": "absolute",
                    "mass_basis": "catalyst",
                    "gas_scope": "reactants_only",
                    "definition_source": definition_source,
                },
                "reactant_ratio": {"value": ratio, "definition_source": definition_source},
            }
        )
    return rows, skipped
