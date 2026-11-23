from pathlib import Path

import pytest

from catalyst_ai.modeling import research_run
from catalyst_ai.modeling.research_preflight import preflight

ROOT = Path(__file__).resolve().parents[2]


def test_small_run_locks_scoring_and_rejects_changes(tmp_path, monkeypatch):
    checked = preflight(ROOT / "configs/research_preflight_example.json", root=ROOT)
    original = checked["split"]["train"]
    training, testing = original[:12], original[12:16]
    checked["split"] = {
        "train": training,
        "test": testing,
        "validation_folds": [training[:6], training[6:]],
    }
    checked["config"]["candidates"] = [{"feature": "F_base", "model": "dummy", "params": {}}]
    monkeypatch.setattr(research_run, "preflight", lambda *args, **kwargs: checked)
    run = tmp_path / "run"
    heldout = [r for r in checked["snapshot"]["content"]["records"] if r["record_id"] in testing]
    labels = [r["payload"]["observations"] for r in heldout]
    for row in heldout:
        row["payload"]["observations"] = []
    lock = research_run.fit("ignored", run, root=ROOT)
    for row, observations in zip(heldout, labels, strict=True):
        row["payload"]["observations"] = observations
    assert lock["test_scored"] is False
    assert not (run / "holdout").exists()
    result = research_run.score(run, root=ROOT)
    assert result["metrics"]["records"] == 4
    assert (run / "holdout" / "observed-predicted.svg").is_file()
    assert (run / "holdout" / "residuals.svg").is_file()
    assert (run / "holdout" / "error-distribution.svg").is_file()
    assert (run / "holdout" / "manifest.json").is_file()
    with pytest.raises(FileExistsError):
        research_run.score(run, root=ROOT)
    with (run / "model.pkl").open("ab") as stream:
        stream.write(b"tamper")
    with pytest.raises(ValueError, match="locked artifact mismatch"):
        research_run.score(run, root=ROOT)


def test_failed_preflight_is_logged(tmp_path, monkeypatch):
    def reject(*args, **kwargs):
        raise ValueError("invalid input")

    monkeypatch.setattr(research_run, "preflight", reject)
    run = tmp_path / "failed"
    with pytest.raises(ValueError, match="invalid input"):
        research_run.fit("ignored", run, root=ROOT)
    assert "invalid input" in (run / "failure.log").read_text(encoding="utf-8")
    assert not (run / "lock.json").exists()


def test_batch_preserves_independent_results(tmp_path, monkeypatch):
    configs = tmp_path / "configs"
    configs.mkdir()
    (configs / "a.json").write_text("{}", encoding="utf-8")
    (configs / "b.json").write_text("{}", encoding="utf-8")

    def fake_fit(path, output, *, root):
        if path.stem == "b":
            raise ValueError("bad config")

    monkeypatch.setattr(research_run, "fit", fake_fit)
    output = tmp_path / "batch"
    rows = research_run.fit_batch(configs, output, root=ROOT)
    assert [r["status"] for r in rows] == ["completed", "failed"]
    assert (output / "batch.json").is_file()
