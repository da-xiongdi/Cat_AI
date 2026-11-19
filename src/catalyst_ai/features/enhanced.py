"""S1-bound physicochemical additions to the fold-fitted R1 representation."""

from copy import deepcopy

from catalyst_ai.features.build import build
from catalyst_ai.features.physchem import calculate, model_values
from catalyst_ai.features.pipeline import R1Features


def verify_s1_binding(
    snapshot, qualification, split, properties, species, review, selection, features, *, root
):
    """Rebuild from source evidence and reject any mismatched historical artifact."""
    expected_selection, expected_features = build(
        snapshot, qualification, split, properties, species, review, root=root
    )
    if selection != expected_selection or features != expected_features:
        raise ValueError("S1 feature binding mismatch")


class EnhancedFeatures:
    """Fit the base vocabulary per fold; fixed descriptors are never fitted."""

    def __init__(self, base, feature_set, properties, species):
        self.base = base
        self.feature_set = feature_set
        self.properties = deepcopy(properties)
        self.species = deepcopy(species)

    @classmethod
    def fit(cls, payloads, feature_set, *, properties, species):
        if feature_set not in ("F1", "F2"):
            raise ValueError("unsupported feature set")
        payloads = list(payloads)
        base = R1Features.fit(payloads, "F_base")
        for payload in payloads:
            calculate(payload, properties, species)
        return cls(base, feature_set, properties, species)

    def transform_one(self, payload, *, diagnostic=False):
        result = self.base.transform_one(payload, diagnostic=diagnostic)
        descriptors = calculate(payload, self.properties, self.species)
        result["derived"] = {
            name: {"value": value, "state": "available" if value is not None else "not_applicable"}
            for name, value in descriptors.items()
        }
        if result["values"] is not None:
            result["values"] += list(model_values(descriptors, self.feature_set).values())
        return result
