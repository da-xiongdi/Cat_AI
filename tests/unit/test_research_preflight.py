import json
from pathlib import Path

import pytest

from catalyst_ai.modeling.research_preflight import preflight, sha

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / 'configs/research_preflight_example.json'


def test_frozen_preflight_and_tampered_split(tmp_path):
    result = preflight(CONFIG, root=ROOT)
    assert result['counts'] == {'train': 434, 'test': 108, 'folds': [87, 87, 87, 87, 86]}
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    split = result['split']
    split['test'].append(split['train'][0])
    path = tmp_path / 'split.json'
    path.write_text(json.dumps(split), encoding='utf-8')
    config['split'] = str(path)
    config['split_sha256'] = sha(path)
    bad = tmp_path / 'config.json'
    bad.write_text(json.dumps(config), encoding='utf-8')
    with pytest.raises(ValueError, match='membership'):
        preflight(bad, root=ROOT)


def test_config_rejects_unknown_parameter(tmp_path):
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    config['candidates'][0]['params']['random_state'] = 100
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(config), encoding='utf-8')
    with pytest.raises(ValueError, match='forbidden'):
        preflight(path, root=ROOT)
