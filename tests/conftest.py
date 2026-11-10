import json
from pathlib import Path

import pytest

from catalyst_ai.config import Settings


@pytest.fixture
def sample():
    return json.loads(
        (Path(__file__).parents[1] / "data/examples/synthetic_demo.json").read_text(
            encoding="utf-8"
        )
    )[0]


@pytest.fixture
def settings(tmp_path):
    return Settings(
        database=tmp_path / "data/catalog.sqlite",
        data_dir=tmp_path / "data",
        report_dir=tmp_path / "reports",
    )


@pytest.fixture
def input_file(tmp_path):
    def create(records):
        path = tmp_path / "input.json"
        path.write_text(json.dumps(records), encoding="utf-8")
        return path

    return create
