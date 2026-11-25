from copy import deepcopy
import pytest
from test_r1_features import payload
from catalyst_ai.features.copper import descriptors


def test_nominal_compound_and_ratio(sample):
    species = {'catalog': {'entries': [
        {'species': 'Cu2ZnO3', 'state': 'supported', 'centers': {'Cu': 2, 'Zn': 1}},
        {'species': 'Al2O3', 'state': 'supported', 'centers': {'Al': 2}},
    ]}}
    x = payload(sample, 'Cu2ZnO3', 40)
    part = deepcopy(x['recipe']['components'][0]); part['species'] = 'Al2O3'; part['role'] = 'support'; part['amount']['normalized_value'] = 60
    x['recipe']['components'].append(part)
    d = descriptors(x, species)
    assert d['cu_species_material_mol_pct'] == 40
    assert d['reported_active_cu_center_fraction'] == pytest.approx(2/3)
    assert d['reported_active_cu_zn_ratio'] == 2
    assert d['reported_active_cu_al_ratio'] is None
    assert d['reported_support_cu_center_fraction'] == 0
    y = deepcopy(x); y['recipe']['components'].reverse()
    assert descriptors(y, species) == d
    species['catalog']['entries'].pop()
    with pytest.raises(ValueError, match='unsupported_species'):
        descriptors(x, species)


def test_transform_reload_and_non_copper(sample):
    import pickle
    from catalyst_ai.features.copper import CopperFeatures
    from catalyst_ai.features.pipeline import R1Features
    species = {'catalog': {'entries': [
        {'species': 'Cu', 'state': 'supported', 'centers': {'Cu': 1}},
        {'species': 'ZnO', 'state': 'supported', 'centers': {'Zn': 1}},
    ]}}
    x = payload(sample, 'Cu')
    transform = CopperFeatures.fit(R1Features.fit([x]), [x], species)
    assert pickle.loads(pickle.dumps(transform)).transform_one(x) == transform.transform_one(x)
    y = payload(sample, 'ZnO')
    assert transform.transform_one(y)['reason'] == 'not_copper'


def test_zero_denominator_invalid_units_and_mapping(sample):
    species = {'catalog': {'entries': [
        {'species': 'Cu', 'state': 'supported', 'centers': {'Cu': 1}},
        {'species': 'ZnO', 'state': 'supported', 'centers': {'Zn': 1}},
    ]}}
    x = payload(sample, 'Cu')
    d = descriptors(x, species)
    assert d['reported_active_cu_zn_ratio'] is None
    assert d['reported_support_cu_center_fraction'] is None
    x['recipe']['components'][0]['amount']['normalized_unit'] = 'g'
    with pytest.raises(ValueError, match='invalid_composition'):
        descriptors(x, species)
    x = payload(sample, 'Cu')
    species['catalog']['entries'][0]['centers']['Cu'] = 0
    with pytest.raises(ValueError, match='invalid_center_count'):
        descriptors(x, species)
