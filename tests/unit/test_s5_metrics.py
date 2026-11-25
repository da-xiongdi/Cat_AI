import pytest

from catalyst_ai.modeling.s5_metrics import compare


def test_common_support_and_undefined_r2():
    a = [{"record_id": str(i), "observed": y, "fold": 0, "status": "ok",
          "raw_prediction": y + 1} for i, y in enumerate([1, 1, 3])]
    b = [dict(r) for r in a]
    b[2].update(status="rejected", raw_prediction=None)
    result = compare({"a": a, "b": b})["overall"]
    assert result["common_ids"] == ["0", "1"]
    assert result["arms"]["a"]["individual"]["r2"] is not None
    assert result["arms"]["a"]["common"]["r2"] is None
    assert result["arms"]["b"]["coverage"] == pytest.approx(2 / 3)
    b[0]["observed"] = 2
    with pytest.raises(ValueError, match="target or fold"):
        compare({"a": a, "b": b})
