import pytest
from pydantic import ValidationError
from catalyst_ai.modeling.config import Model
from catalyst_ai.modeling.research_preflight import ResearchConfig

@pytest.mark.parametrize('params', [
    {'n_estimators': None}, {'n_estimators': True}, {'n_estimators': 0},
    {'max_depth': None}, {'max_depth': 0}, {'max_depth': 1.5},
    {'learning_rate': None}, {'learning_rate': True}, {'learning_rate': 0},
    {'learning_rate': float('nan')}, {'learning_rate': 1.1}, {'n_jobs': 1},
])
def test_xgboost_invalid_parameters(params):
    with pytest.raises(ValidationError):
        Model(name='xgboost', params=params)

def test_xgboost_version_gate():
    base = dict(view='v', snapshot='s', split='s', split_sha256='x', candidates=[
        {'feature': 'F_base', 'model': 'extra_trees'},
        {'feature': 'F_base', 'model': 'xgboost', 'params': {'max_depth': 3}},
    ])
    with pytest.raises(ValidationError):
        ResearchConfig(**base)
    ResearchConfig(**base, schema_version=2, selection_rule='s5-paired-v1')
