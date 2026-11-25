"""Copper descriptors from the frozen nominal species catalog.

Amounts refer to source material mol%, not measured loadings or active sites.
"""
from math import isfinite

from catalyst_ai.features.pipeline import project
from catalyst_ai.features.physchem import ROLES

VERSION = 'copper-nominal-v1'


def descriptors(payload, species):
    row = project(payload)
    mapping = {item['species']: item for item in species['catalog']['entries']}
    centers = {role: {} for role in ROLES}
    copper_material = 0.0
    for (role, name), amount in row['amounts'].items():
        if amount <= 0:
            continue
        if role not in ROLES:
            raise ValueError('unsupported_source_role')
        item = mapping.get(name, {})
        if item.get('state') != 'supported' or not item.get('centers'):
            raise ValueError('unsupported_species:' + name)
        for element, count in item['centers'].items():
            if not isfinite(count) or count <= 0:
                raise ValueError('invalid_center_count:' + name)
            centers[role][element] = centers[role].get(element, 0.0) + amount * count
        if 'Cu' in item['centers']:
            copper_material += amount
    total_cu = sum(c.get('Cu', 0.0) for c in centers.values())
    if total_cu <= 0:
        raise ValueError('not_copper')
    result = {'cu_species_material_mol_pct': copper_material}
    for role, label in ROLES.items():
        values = centers[role]
        cu = values.get('Cu', 0.0)
        total = sum(values.values())
        result[label + '_cu_center_fraction'] = cu / total if total > 0 else None
        for element in ('Zn', 'Zr', 'Al'):
            denominator = values.get(element, 0.0)
            result[label + '_cu_' + element.lower() + '_ratio'] = (
                cu / denominator if cu > 0 and denominator > 0 else None
            )
    return result

class CopperFeatures:
    """Append nominal copper descriptors to a fold-fitted general transformer."""
    def __init__(self, base, species, names, ranges):
        from copy import deepcopy
        self.base = base
        self.species = deepcopy(species)
        self.names = names
        self.ranges = ranges
        self.version = VERSION

    @classmethod
    def fit(cls, base, payloads, species):
        rows = [descriptors(p, species) for p in payloads]
        if not rows:
            raise ValueError('empty training inputs')
        names = tuple(rows[0])
        ranges = {}
        for name in names:
            values = [r[name] for r in rows if r[name] is not None]
            if values:
                ranges[name] = (min(values), max(values))
        return cls(base, species, names, ranges)

    def transform_one(self, payload, *, diagnostic=False):
        result = self.base.transform_one(payload, diagnostic=diagnostic)
        try:
            values = descriptors(payload, self.species)
        except ValueError as error:
            result.update(status='unsupported', values=None, fully_encoded=False, reason=str(error))
            return result
        result['copper_derived'] = {k: {'value': v, 'state': 'not_applicable' if v is None else 'zero' if v == 0 else 'available'} for k, v in values.items()}
        warnings = [k for k, v in values.items() if v is not None and (k not in self.ranges or not self.ranges[k][0] <= v <= self.ranges[k][1])]
        result['out_of_range'].extend(warnings)
        if warnings and result['status'] == 'ok':
            result['status'] = 'caution'
        if result['values'] is not None:
            # Explicit applicability flags distinguish absent denominators from zeros.
            for k in self.names:
                v = values[k]
                result['values'].extend([0.0 if v is None else v, float(v is not None)])
        return result
