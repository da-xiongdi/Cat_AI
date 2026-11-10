import pytest
from pydantic import ValidationError

from catalyst_ai.config import Settings
from catalyst_ai.schemas.domain import ExperimentBatch, Measurement


@pytest.mark.parametrize("state", ["unknown", "not_reported", "not_applicable", "not_measured"])
def test_missing_is_not_zero(state):
    assert Measurement(state=state).raw_value is None
    with pytest.raises(ValidationError):
        Measurement(state=state, raw_value="0")


def test_zero_keeps_raw_text():
    assert Measurement(state="zero", raw_value="0.00").raw_value == "0.00"
    with pytest.raises(ValidationError):
        Measurement(state="reported")


def test_capacity_default_and_limits():
    assert Settings().batch_capacity == 4
    assert ExperimentBatch(candidate_ids=[str(i) for i in range(4)]).capacity == 4
    assert ExperimentBatch(capacity=6, candidate_ids=[str(i) for i in range(6)])
    for capacity in (0, 7, 4.5, True):
        with pytest.raises(ValidationError):
            Settings(batch_capacity=capacity)
        with pytest.raises(ValidationError):
            ExperimentBatch(capacity=capacity, candidate_ids=[])
    with pytest.raises(ValidationError, match="exceeds"):
        ExperimentBatch(candidate_ids=[str(i) for i in range(5)])
    with pytest.raises(ValidationError, match="duplicate"):
        ExperimentBatch(candidate_ids=["same", "same"])
