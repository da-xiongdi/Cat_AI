"""Exercise the real preflight, fit and scoring flow on an isolated small view."""

import json
from pathlib import Path

import pytest

from catalyst_ai.datasets.research_prepare import prepare
from catalyst_ai.modeling import research_run
from catalyst_ai.modeling.research_preflight import preflight, sha
from catalyst_ai.modeling.research_run import fit, predict_payloads, score
from catalyst_ai.reporting.evidence import digest

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "artifacts/reports/s4-02-20261120-v1"


def save(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.mark.parametrize("strategy", ["random", "doi"])
def test_small_real_pipeline(tmp_path, strategy, monkeypatch):
    view = json.loads((BASE / "all-view.json").read_text(encoding="utf-8"))
    source_rows = json.loads((BASE / "ledger.json").read_text(encoding="utf-8"))["records"]
    eligible = set(view["content"]["common_record_ids"])
    by_doi = {}
    for row in source_rows:
        if row["record_id"] in eligible:
            by_doi.setdefault(row["doi"], []).append(row["record_id"])
    ids = sorted(
        i for rows in list(sorted(by_doi.values(), key=lambda r: r[0]))[:12] for i in rows[:3]
    )
    view["content"]["common_record_ids"] = ids
    view["content"]["target_record_ids"] = ids
    view["content_sha256"] = digest(view["content"])
    view["view_id"] = "test-view-" + view["content_sha256"]
    save(tmp_path / "view.json", view)
    for name in ("ledger.json", "distributions.json"):
        (tmp_path / name).write_bytes((BASE / name).read_bytes())
    snapshot = (
        ROOT
        / "data/snapshots"
        / "snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json"
    )
    split = prepare(tmp_path / "view.json", snapshot, root=ROOT, strategy=strategy, folds=3)
    save(tmp_path / "split.json", split)
    config = {
        "view": str(tmp_path / "view.json"),
        "snapshot": str(snapshot),
        "split": str(tmp_path / "split.json"),
        "split_sha256": sha(tmp_path / "split.json"),
        "candidates": [
            {"feature": feature, "model": "dummy"} for feature in ("F_base", "F1", "F2")
        ],
    }
    save(tmp_path / "config.json", config)
    checked = preflight(tmp_path / "config.json", root=ROOT)
    assert checked["counts"]["train"] + checked["counts"]["test"] == len(ids)
    run = tmp_path / "run"
    fit(tmp_path / "config.json", run, root=ROOT)
    assert not (run / "holdout").exists()
    records = checked["snapshot"]["content"]["records"]
    payload = next(r["payload"] for r in records if r["record_id"] == split["train"][0])
    prediction = predict_payloads(run, [payload])
    assert prediction["predictions"][0]["status"] in ("ok", "caution")
    if strategy == "random":
        replay = tmp_path / "replay"
        fit(tmp_path / "config.json", replay, root=ROOT)
        assert json.loads(
            (run / "cross_validation.json").read_text(encoding="utf-8")
        ) == json.loads((replay / "cross_validation.json").read_text(encoding="utf-8"))
        assert predict_payloads(replay, [payload])["predictions"] == prediction["predictions"]
    if strategy == "random":
        original = research_run._score_holdout

        def fail(*args):
            raise OSError("simulated output failure")

        monkeypatch.setattr(research_run, "_score_holdout", fail)
        with pytest.raises(OSError, match="simulated output failure"):
            score(run, root=ROOT)
        assert (run / "holdout/failure.log").is_file()
        monkeypatch.setattr(research_run, "_score_holdout", original)
        result = score(run, root=ROOT, retry=True)
        assert (run / "holdout-retry-001/manifest.json").is_file()
    else:
        result = score(run, root=ROOT)
    assert result["metrics"]["records"] == len(split["test"])
    with pytest.raises(FileExistsError):
        score(run, root=ROOT)
