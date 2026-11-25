"""Versioned center-weighted descriptors for S5 general catalysts."""

from copy import deepcopy
from math import isfinite

from catalyst_ai.features.physchem import PROPERTIES, ROLES
from catalyst_ai.features.pipeline import R1Features, project

VERSION = "f3-center-v2"


def descriptors(payload, properties, species):
    """Return values and applicability without inventing unsupported mappings."""
    row = project(payload)
    props = {(p["element"], p["property"]): p for p in properties["catalog"]["entries"]}
    mapping = {s["species"]: s for s in species["catalog"]["entries"]}
    if any(role not in ROLES and amount > 0 for (role, _), amount in row["amounts"].items()):
        raise ValueError("unsupported_source_role")
    result = {}
    for role, label in ROLES.items():
        components = [(name, amount) for (r, name), amount in row["amounts"].items()
                      if r == role and amount > 0]
        total = sum(amount for _, amount in components)
        result[label + "_material_mol_pct"] = total
        result[label + "_species_count"] = len(components)
        result[label + "_present"] = int(bool(components))
        weighted = {p: [] for p in PROPERTIES}
        for name, amount in components:
            entry = mapping.get(name, {})
            if entry.get("state") != "supported" or not entry.get("centers"):
                raise ValueError("unsupported_species:" + name)
            for element, count in entry["centers"].items():
                if not isfinite(count) or count <= 0:
                    raise ValueError("invalid_center_count:" + name)
                for prop in PROPERTIES:
                    item = props.get((element, prop), {})
                    if item.get("state") != "available" or not isfinite(item["value"]):
                        raise ValueError("property_unavailable:" + element + ":" + prop)
                    weighted[prop].append((amount * count, item["value"]))
        for prop, values in weighted.items():
            weight = sum(w for w, _ in values)
            mean = sum(w * v for w, v in values) / weight if weight else None
            variance = (sum(w * (v - mean) ** 2 for w, v in values) / weight
                        if weight else None)
            result[label + "_mean_" + prop] = mean
            result[label + "_variance_" + prop] = variance
    for prop in PROPERTIES:
        a = result["reported_active_mean_" + prop]
        b = result["reported_support_mean_" + prop]
        result["active_minus_support_" + prop] = a - b if a is not None and b is not None else None
    a = result["reported_active_material_mol_pct"]
    b = result["reported_support_material_mol_pct"]
    result["active_support_ratio"] = a / b if a > 0 and b > 0 else None
    return result


class F3Features:
    """Fold-local range checks with a fixed, catalog-bound descriptor block."""

    def __init__(self, base, feature_set, properties, species, names, ranges):
        self.base = base
        self.feature_set = feature_set
        self.properties = deepcopy(properties)
        self.species = deepcopy(species)
        self.names = names
        self.ranges = ranges
        self.version = VERSION

    @classmethod
    def fit(cls, payloads, feature_set, *, properties, species):
        if feature_set not in ("F3-P", "F3-H", "F3-I"):
            raise ValueError("unsupported feature set")
        payloads = list(payloads)
        base = R1Features.fit(payloads, "F_base" if feature_set == "F3-H" else "F_cond")
        rows = [descriptors(p, properties, species) for p in payloads]
        names = tuple(k for k in rows[0] if feature_set == "F3-I" or
                      not (k.startswith("active_minus_") or k == "active_support_ratio"))
        ranges = {}
        for name in names:
            present = [row[name] for row in rows if row[name] is not None]
            if present:
                ranges[name] = (min(present), max(present))
        return cls(base, feature_set, properties, species, names, ranges)

    def transform_one(self, payload, *, diagnostic=False):
        result = self.base.transform_one(payload, diagnostic=diagnostic)
        try:
            values = descriptors(payload, self.properties, self.species)
        except ValueError as error:
            result.update(status="unsupported", values=None, fully_encoded=False, reason=str(error))
            return result
        result["derived"] = {
            k: {"value": v, "state": "not_applicable" if v is None else "zero" if v == 0
                else "available"}
            for k, v in values.items()
        }
        warnings = []
        for name in self.names:
            value = values[name]
            if value is None:
                continue
            bounds = self.ranges.get(name)
            if bounds is None or not bounds[0] <= value <= bounds[1]:
                warnings.append(name)
        result["out_of_range"].extend(warnings)
        if warnings and result["status"] == "ok":
            result["status"] = "caution"
        if result["values"] is not None:
            result["values"] += [0.0 if values[k] is None else values[k] for k in self.names]
        return result
