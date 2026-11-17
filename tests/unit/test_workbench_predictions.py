import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from test_experiments import prepared

from catalyst_ai.features.pipeline import project
from catalyst_ai.modeling.experiments import compare_r1
from catalyst_ai.modeling.predictor import load_package, predict_one, save_package
from catalyst_ai.storage.workbench import transaction
from catalyst_ai.web.app import create_app
from catalyst_ai.workbench import backup, index, predictions


@pytest.fixture
def setup_predictions(tmp_path, sample):
    db = tmp_path / "wb.sqlite"
    client = TestClient(create_app(db, tmp_path, "p"), base_url="http://localhost")
    snapshot, qualification, split = prepared(sample)
    report, fitted = compare_r1(snapshot, qualification, split)
    package = tmp_path / "package"
    save_package(package, report, fitted)
    index.register(
        db, "p", "model", "model", "package/manifest.json", request_id="model", actor="test"
    )
    index.scan(db, "p")
    version = predictions.sha((package / "manifest.json").read_bytes())
    row = project(snapshot["content"]["records"][0]["payload"])
    item = {
        **row["conditions"],
        "components": [dict(role=r, species=s, mol_pct=a) for (r, s), a in row["amounts"].items()],
    }
    return db, tmp_path, client, version, item


def enqueue(setup, rid="enqueue"):
    db, _, _, version, item = setup
    return predictions.enqueue(db, "p", "model", version, [item, {}], request_id=rid, actor="test")


def test_worker_subprocess_matches_python_and_registers_outputs(setup_predictions):
    db, root, client, version, item = setup_predictions
    job = enqueue(setup_predictions)
    assert enqueue(setup_predictions) == job
    page = client.get("/predictions")
    assert page.status_code == 200
    assert 'value="model|' + version + '"' in page.text
    assert client.post("/api/workbench/v1/prediction-jobs", json={}).status_code == 403
    config = root / "workbench.yaml"
    config.write_text("workspace: .\ndatabase: wb.sqlite\nproject_id: p\n", encoding="utf-8")
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "catalyst_ai.cli",
            "workbench",
            "worker",
            "--config",
            str(config),
            "--once",
        ],
        capture_output=True,
        timeout=60,
    )
    assert process.returncode == 0, process.stderr.decode("utf-8")
    result = predictions.get(db, "p", job["id"])
    assert result["status"] == "succeeded", result["error"]
    expected = predict_one(load_package(root / "package"), item)
    assert result["result"]["rows"][0]["co2_conversion_pct"] == expected["co2_conversion_pct"]
    assert result["result"]["rows"][1]["status"] == "invalid_input"
    restored = root / "restored"
    bundle = backup.create_bundle(db, root)
    backup.restore_bundle(bundle, restored, backup.preview_bundle(bundle)["sha256"])
    assert (
        predictions.get(restored / "workbench.sqlite", "p", job["id"])["result"] == result["result"]
    )
    assert (
        restored / "workspace/artifacts/workbench-predictions" / job["id"] / "model.pkl"
    ).is_file()


def test_tampering_recovery_retry_and_atomic_claim(setup_predictions):
    db, root, _, _, _ = setup_predictions
    job = enqueue(setup_predictions)
    directory = predictions.job_dir(root, job["id"])
    (directory / "input.json").write_text("[]")
    predictions.run_once(db, "p")
    assert predictions.get(db, "p", job["id"])["status"] == "failed"
    (root / "package/manifest.json").unlink()
    retried = predictions.retry(db, "p", job["id"], request_id="retry", actor="test")
    with transaction(db) as conn:
        conn.execute(
            "UPDATE prediction_job SET status='running',heartbeat='2000',lease='dead' WHERE id=?",
            (retried["id"],),
        )
    assert predictions.recover(db, "p") == [retried["id"]]
    third = predictions.retry(db, "p", retried["id"], request_id="retry2", actor="test")
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: predictions.run_once(db, "p"), range(2)))
    assert results.count(third["id"]) == 1
    assert predictions.get(db, "p", third["id"])["status"] == "succeeded"


def test_cancel_during_execution_cannot_publish_success(setup_predictions, monkeypatch):
    from catalyst_ai.modeling import predictor

    db, _, _, _, _ = setup_predictions
    job = enqueue(setup_predictions)
    original = predictor.predict_one

    def cancel_then_predict(package, item):
        current = predictions.get(db, "p", job["id"])
        predictions.cancel(
            db, "p", job["id"], current["revision"], request_id="cancel", actor="test"
        )
        return original(package, item)

    monkeypatch.setattr(predictor, "predict_one", cancel_then_predict)
    predictions.run_once(db, "p")
    assert predictions.get(db, "p", job["id"])["status"] == "cancelled"
    with transaction(db) as conn:
        assert conn.execute("SELECT count(*) FROM model_run").fetchone()[0] == 0
