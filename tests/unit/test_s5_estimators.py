import pickle

import pytest
from pydantic import ValidationError

from catalyst_ai.modeling.config import Model
from catalyst_ai.modeling import research_training


def test_new_estimators_train_and_reload(monkeypatch):
    class Transformer:
        @classmethod
        def fit(cls, payloads, feature):
            return cls()

        def transform_one(self, payload, diagnostic=False):
            return {'values': [payload['x']], 'status': 'ok'}

    monkeypatch.setattr(research_training, 'R1Features', Transformer)
    monkeypatch.setattr(research_training, 'target_value', lambda row, content: row['payload']['x'])
    rows = [{'record_id': str(i), 'payload': {'x': float(i), 'source': {'doi': '10.1/test'}}} for i in range(40)]
    candidates = [{'feature': 'F_base', 'model': n, 'params': p} for n, p in [
        ('extra_trees', {'n_estimators': 3, 'n_jobs': 1}),
        ('random_forest', {'n_estimators': 3, 'n_jobs': 1}),
        ('gradient_boosting', {'n_estimators': 3, 'max_depth': 2, 'learning_rate': 0.1})]]
    result = research_training.train(rows, {}, [[str(i) for i in range(k, 40, 5)] for k in range(5)], candidates, selection_rule='s5-paired-v1')
    for package in result['packages']:
        model = pickle.loads(pickle.dumps(package['model']))
        assert model.predict([[2.0]])[0] == package['model'].predict([[2.0]])[0]
    with pytest.raises(ValidationError):
        Model.model_validate({'name': 'gradient_boosting', 'params': {'learning_rate': 0}})
    with pytest.raises(ValidationError):
        Model.model_validate({'name': 'random_forest', 'params': {'unknown': 1}})
