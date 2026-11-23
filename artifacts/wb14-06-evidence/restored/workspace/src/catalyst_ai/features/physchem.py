"""Fixed, center-weighted physicochemical descriptors for complete inputs."""

from catalyst_ai.features.pipeline import project

VERSION = "physchem-v1"
PROPERTIES = ("pauling_electronegativity", "covalent_radius")
ROLES = {"compound": "reported_active", "support": "reported_support"}


def calculate(payload, properties, species):
    """Calculate descriptors; historical records also require source qualification.

    Null means an absent role, not a measured zero.
    """
    row = project(payload)
    props = {(p["element"], p["property"]): p for p in properties["catalog"]["entries"]}
    mappings = {s["species"]: s for s in species["catalog"]["entries"]}
    if any(role not in ROLES and amount > 0 for (role, _), amount in row["amounts"].items()):
        raise ValueError("unsupported_source_role")
    result = {}
    for role, label in ROLES.items():
        components = [
            (name, amount)
            for (r, name), amount in row["amounts"].items()
            if r == role and amount > 0
        ]
        result[label + "_material_mol_pct"] = sum(amount for _, amount in components)
        result[label + "_species_count"] = len(components)
        sums = dict.fromkeys(PROPERTIES, 0.0)
        weight = 0.0
        for name, amount in components:
            mapping = mappings.get(name, {})
            if mapping.get("state") != "supported" or not mapping.get("centers"):
                raise ValueError("unsupported_species:" + name)
            for element, count in mapping["centers"].items():
                w = amount * count
                weight += w
                for prop in PROPERTIES:
                    entry = props.get((element, prop), {})
                    if entry.get("state") != "available":
                        raise ValueError("property_unavailable:" + element + ":" + prop)
                    sums[prop] += w * entry["value"]
        for prop in PROPERTIES:
            result[label + "_mean_" + prop] = sums[prop] / weight if weight else None
    for prop in PROPERTIES:
        active = result["reported_active_mean_" + prop]
        support = result["reported_support_mean_" + prop]
        result["active_minus_support_" + prop] = (
            active - support if active is not None and support is not None else None
        )
    return result


def model_values(descriptors, feature_set):
    """Return fixed S1-B increments; absent-role nulls become array placeholders."""
    if feature_set not in ("F1", "F2"):
        raise ValueError("unsupported physicochemical feature set")
    names = []
    for role in ("reported_active",) if feature_set == "F1" else ROLES.values():
        names.extend((role + "_material_mol_pct", role + "_species_count"))
        names.extend(role + "_mean_" + prop for prop in PROPERTIES)
    if feature_set == "F2":
        names.extend("active_minus_support_" + prop for prop in PROPERTIES)
    return {name: 0.0 if descriptors[name] is None else descriptors[name] for name in names}
