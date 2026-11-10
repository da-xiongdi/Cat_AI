"""Generate explicitly fictional format fixtures, never scientific training data."""

import csv
import json
from pathlib import Path


def main():
    output = Path(__file__).resolve().parents[1] / "data/examples"
    output.mkdir(parents=True, exist_ok=True)

    def m(value, unit, definition=None):
        return {
            "raw_value": value,
            "raw_unit": unit,
            "state": "zero" if value == "0" else "reported",
            "source_locator": "demo-extraction-1",
            "definition": definition,
        }

    record = {
        "schema_version": "1",
        "dataset_kind": "synthetic_demo",
        "source": {
            "source_id": "demo-document-1",
            "kind": "literature",
            "title": "synthetic_demo: fictional format fixture, not a publication",
            "license": "synthetic_demo_only",
            "access": "demo",
        },
        "extraction": {
            "extraction_id": "demo-extraction-1",
            "source_id": "demo-document-1",
            "locator": "synthetic_demo: fictional table 1 row 1",
            "method": "synthetic_demo_generator",
            "method_version": "1",
            "original_excerpt": "All values are fictional software test inputs.",
        },
        "recipe": {
            "recipe_id": "demo-recipe-1",
            "material_family": "In2O3/ZrO2 demo",
            "composition_basis": "wt_pct",
            "composition_scope": "all nominal oxides",
            "components": [
                {"species": "In2O3", "role": "compound", "amount": m("80", "%")},
                {"species": "ZrO2", "role": "support", "amount": m("20", "%")},
            ],
            "supports": ["ZrO2"],
        },
        "synthesis": {
            "synthesis_id": "demo-syn-1",
            "recipe_id": "demo-recipe-1",
            "route": "synthetic_demo route; not an experimental instruction",
            "precursors": [],
            "batch_label": "synthetic_demo",
            "steps": [
                {
                    "name": "fictional calcination",
                    "parameters": {"temperature": m("400", "degC"), "duration": m("3", "h")},
                }
            ],
        },
        "test": {
            "test_id": "demo-test-1",
            "synthesis_id": "demo-syn-1",
            "reactor": "demo",
            "temperature": m("250.00", "degC"),
            "pressure": m("3.0", "MPa"),
            "pressure_type": "absolute",
            "ghsv": m("12000", "h^-1"),
            "ghsv_basis": {
                "reference_temperature": m("273.15", "K"),
                "reference_pressure": m("1.01325", "bar"),
                "reference_pressure_type": "absolute",
                "catalyst_volume_basis": "packed_bed",
                "description": "synthetic_demo: fictional inlet reference and packed-bed volume",
            },
            "feed_basis": "mol_pct",
            "feed": [
                {"species": "H2", "role": "gas", "amount": m("75", "%")},
                {"species": "CO2", "role": "gas", "amount": m("25", "%")},
            ],
            "catalyst_mass": m("0.5", "g"),
        },
        "observations": [
            {
                "observation_id": "demo-obs-1",
                "test_id": "demo-test-1",
                "metric": "co2_conversion",
                "value": m("20.0", "%", "synthetic_demo: (CO2_in - CO2_out)/CO2_in, molar"),
            },
            {
                "observation_id": "demo-obs-2",
                "test_id": "demo-test-1",
                "metric": "methanol_selectivity",
                "value": m("60.0", "%", "synthetic_demo: carbon in MeOH / converted CO2 carbon"),
            },
        ],
        "characterizations": [],
    }
    (output / "synthetic_demo.json").write_text(
        json.dumps([record], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (output / "synthetic_demo.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(record))
        writer.writeheader()
        writer.writerow(
            {
                k: v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
                for k, v in record.items()
            }
        )


if __name__ == "__main__":
    main()
