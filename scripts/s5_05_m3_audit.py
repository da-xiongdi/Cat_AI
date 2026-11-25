"""Check the frozen M3 metrics and derive the missing explicit paired summaries."""

import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

from catalyst_ai.modeling.baseline import target_value

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts/reports/s5-05-e05-20261124-v1"
SEEDS = (45, 46, 47)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(expected, actual):
    if expected is None or actual is None:
        assert expected == actual, (expected, actual)
    else:
        assert math.isclose(expected, actual, rel_tol=1e-11, abs_tol=1e-12), (expected, actual)


def finite(row):
    value = row["raw_prediction"]
    return type(value) in (int, float) and math.isfinite(value)


def available(row):
    return row["status"] in {"ok", "caution"} and finite(row)


def error(row):
    return row["raw_prediction"] - row["observed"]


def metrics(rows):
    if not rows:
        return {"mae": None, "rmse": None, "r2": None}
    errors = [error(r) for r in rows]
    sse = math.fsum(e**2 for e in errors)
    targets = [r["observed"] for r in rows]
    mean_target = mean(targets)
    sst = math.fsum((v - mean_target) ** 2 for v in targets)
    return {
        "mae": mean(abs(e) for e in errors),
        "rmse": math.sqrt(sse / len(rows)),
        "r2": 1 - sse / sst if len(rows) >= 2 and sst else None,
    }


def check_metrics(rows, saved):
    for key, value in metrics(rows).items():
        close(value, saved[key])
    assert bool(saved["r2_unavailable_reason"]) == (saved["r2"] is None)


def check_summary(rows, summary):
    diagnostic = [r for r in rows if finite(r)]
    usable = [r for r in rows if available(r)]
    assert (summary["total"], summary["diagnostic_n"], summary["available_n"]) == (
        len(rows),
        len(diagnostic),
        len(usable),
    )
    assert summary["statuses"] == Counter(r["status"] for r in rows)
    close(len(usable) / len(rows) if rows else None, summary["coverage"])
    check_metrics(diagnostic, summary["diagnostic"])
    check_metrics(usable, summary["available"])
    papers = defaultdict(list)
    for row in usable:
        papers[row["doi"]].append(abs(error(row)))
    assert summary["doi_n"] == len(papers) and summary["doi_strata"].keys() == papers.keys()
    for doi, errors in papers.items():
        assert summary["doi_strata"][doi]["n"] == len(errors)
        close(mean(errors), summary["doi_strata"][doi]["mae"])
    close(mean(map(mean, papers.values())) if papers else None, summary["doi_equal_mae"])
    if usable:
        errors = [error(r) for r in usable]
        close(mean(errors), summary["bias"])
        for value, saved in zip(
            (min(errors), median(errors), max(errors)),
            summary["residual_min_median_max"],
            strict=True,
        ):
            close(value, saved)


def check_common(arms, saved):
    have = [{r["record_id"] for r in rows if available(r)} for rows in arms]
    shared = set.intersection(*have)
    assert sorted(shared) == saved["common_ids"]
    assert saved["denominator"] == len(arms[0])
    for i, rows in enumerate(arms):
        summary = saved["arms"][str(i)]
        assert (
            summary["available"],
            summary["individual"]["records"],
            summary["common"]["records"],
        ) == (len(have[i]), len(have[i]), len(shared))
        close(len(have[i]) / len(rows), summary["coverage"])
        check_metrics([r for r in rows if available(r)], summary["individual"])
        check_metrics([r for r in rows if r["record_id"] in shared], summary["common"])


def selection(arms, decision):
    maps = [{r["record_id"]: r for r in arm["predictions"] if available(r)} for arm in arms]
    n = len(arms[0]["predictions"])
    minimum = max(30, math.ceil(0.8 * len(maps[0])))
    assert minimum == decision["minimum_common"]
    eligible = []
    for i, rows in enumerate(maps):
        overlap = rows.keys() & maps[0].keys()
        qualified = (
            len(rows) / n >= 0.8
            and (len(maps[0]) - len(rows)) / n <= 0.05
            and len(overlap) >= minimum
        )
        saved = decision["comparisons"][i]
        assert (qualified, sorted(overlap)) == (saved["eligible"], saved["common_ids"])
        assert sorted(rows.keys() - maps[0].keys()) == saved["new_coverage_ids"]
        assert sorted(maps[0].keys() - rows.keys()) == saved["lost_coverage_ids"]
        if qualified:
            eligible.append(i)
    assert 0 in eligible
    shared = set.intersection(*(set(maps[i]) for i in eligible))
    assert sorted(shared) == decision["selection_common_ids"] and len(shared) >= minimum
    scores = {i: mean(abs(error(maps[i][key])) for key in shared) for i in eligible}
    for i, score in scores.items():
        close(score, decision["selection_common_mae"][str(i)])
    return shared, scores


def paired(arms, ids):
    maps = [{row["record_id"]: row for row in arm} for arm in arms]
    ids = sorted(ids)
    result = {}
    for i, rows in enumerate(maps):
        deltas = [abs(error(rows[key])) - abs(error(maps[0][key])) for key in ids]
        by_doi = defaultdict(list)
        for key, delta in zip(ids, deltas, strict=True):
            by_doi[rows[key]["doi"]].append(delta)
        result[str(i)] = {
            "mae_delta_vs_baseline": mean(deltas),
            "doi_n": len(by_doi),
            "doi_equal_mae_delta_vs_baseline": mean(map(mean, by_doi.values())),
        }
    return {"n": len(ids), "arms": result}


def check_run(seed, all_metrics, f3):
    run = REPORT / f"run-{seed}"
    frozen = read(REPORT / f"configs/{seed}.json")
    config = read(run / "config.json")
    assert config == dict(
        frozen, catalog_database=frozen.get("catalog_database", "data/catalog.sqlite")
    )
    assert config["model_seed"] == 42 and config["selection_rule"] == "s5-paired-v1"
    lock = read(run / "lock.json")
    for name, digest in lock["artifacts"].items():
        assert sha(run / name) == digest
    for name, digest in read(run / "holdout/manifest.json")["files"].items():
        assert sha(run / "holdout" / name) == digest
    assert not lock["test_scored"]
    split = read(run / "split.json")
    assert sha(ROOT / frozen["split"]) == frozen["split_sha256"] == sha(run / "split.json")
    assert split["seed"] == seed and len(split["validation_folds"]) == 5
    folds = {key: f for f, ids in enumerate(split["validation_folds"]) for key in ids}
    train, test = set(split["train"]), set(split["test"])
    assert set(folds) == train and not train & test and (len(train), len(test)) == (434, 108)
    assert sum(map(len, split["validation_folds"])) == len(train)
    assert sum(map(len, split["groups"])) == len(train | test)
    assert {key for group in split["groups"] for key in group} == train | test
    for group in split["groups"]:
        assert len({folds.get(key, "holdout") for key in group}) == 1
    snapshot = read(ROOT / frozen["snapshot"])["content"]
    targets = {
        r["record_id"]: float(target_value(r, snapshot))
        for r in snapshot["records"]
        if r["record_id"] in train | test
    }
    cv = read(run / "cross_validation.json")
    arms = cv["results"]
    candidates = [a["candidate"] for a in arms]
    assert candidates == frozen["candidates"] == all_metrics["candidates"]
    assert Counter((a["feature"], a["model"]) for a in candidates) == {
        (f, m): 3 for f in ("F_base", "F3-P") for m in ("extra_trees", "random_forest", "xgboost")
    }
    assert len({json.dumps(a, sort_keys=True) for a in candidates}) == 18
    for i in range(9):
        assert dict(candidates[i], feature="F3-P") == candidates[i + 9]
    training = [a["predictions"] for a in arms]
    holdout_items = read(run / "holdout/all_arms.json")
    assert [a["candidate_index"] for a in holdout_items] == list(range(18))
    holdout = [a["predictions"] for a in holdout_items]
    assert holdout[0] == read(run / "holdout/predictions.json")
    for i, (oof, held) in enumerate(zip(training, holdout, strict=True)):
        for rows, ids in ((oof, train), (held, test)):
            assert len(rows) == len(ids) and {r["record_id"] for r in rows} == ids
            assert all(r["observed"] == targets[r["record_id"]] for r in rows)
            assert all(r.get("fold") == folds.get(r["record_id"]) for r in rows)
        check_summary(oof, all_metrics["oof"][str(i)])
        check_summary(held, all_metrics["holdout"][str(i)])
        for timing in arms[i]["fold_timing"]:
            validation = split["validation_folds"][timing["fold"]]
            for field, ids in (
                ("fit_ids_sha256", train - set(validation)),
                ("validation_ids_sha256", validation),
            ):
                assert hashlib.sha256(json.dumps(sorted(ids)).encode()).hexdigest() == timing[field]
    for label, rows in (("oof", training), ("holdout", holdout)):
        check_common(rows, all_metrics[label + "_common"]["overall"])
    for fold in range(5):
        rows = [[r for r in arm if r["fold"] == fold] for arm in training]
        for i, arm in enumerate(rows):
            check_summary(arm, all_metrics["folds"][str(i)][str(fold)])
        check_common(rows, all_metrics["oof_common"]["folds"][str(fold)])
    shared, scores = selection(arms, cv["selection_decision"])
    gap = scores[0] - min(scores.values())
    assert gap <= 0.1 and cv["selection_decision"]["reason"] == "baseline_tie"
    assert cv["selected_index"] == lock["selected_index"] == all_metrics["selected_index"] == 0
    e01 = ROOT / f3["e01_oof_path"]
    assert sha(e01) == f3["sha256"]
    assert sha(e01.parent / "split.json") == sha(run / "split.json")
    _, f3_scores = selection([read(e01)["results"][i] for i in (0, 4, 5, 6)], f3["decision"])
    best_f3 = min(score for i, score in f3_scores.items() if i > 0)
    assert min(i for i, score in f3_scores.items() if i > 0 and score <= best_f3 + 0.1) == 1
    assert f3["chosen"] == "F3-P"
    statuses = defaultdict(list)
    for row in holdout[0]:
        statuses[row["status"]].append(row)
    return {
        "training_common_n": len(shared),
        "selected_baseline_mae_gap": gap,
        "holdout_paired": paired(holdout, all_metrics["holdout_common"]["overall"]["common_ids"]),
        "baseline_oof_fold_mae": [
            all_metrics["folds"]["0"][str(f)]["available"]["mae"] for f in range(5)
        ],
        "baseline_holdout_status_strata": {
            k: {
                "total": len(rows),
                "finite_n": sum(map(finite, rows)),
                "diagnostic": metrics([r for r in rows if finite(r)]),
            }
            for k, rows in statuses.items()
        },
    }


def main():
    manifest = REPORT / "evidence-sha256.json"
    files = read(manifest)["files"]
    assert len(files) == 265
    for path, digest in files.items():
        assert sha(ROOT / path) == digest, path
    saved = read(REPORT / "metrics.json")
    f3 = read(REPORT / "f3-training-selection.json")
    runs = {str(s): check_run(s, saved[str(s)], f3[str(s)]) for s in SEEDS}
    history = read(REPORT / "historical-r2.json")
    assert not history["gaps"] and len(history["runs"]) == 30
    counts = Counter()
    for path, record in history["runs"].items():
        run = ROOT / path
        cv = run / "cross_validation.json"
        assert sha(cv) == record["cross_validation_sha256"]
        for i, arm in enumerate(read(cv)["results"]):
            check_summary(arm["predictions"], record["oof"][str(i)])
            counts["oof_arms"] += 1
        if "holdout" in record:
            held = run / "holdout/all_arms.json"
            for arm in read(held):
                check_summary(arm["predictions"], record["holdout"][str(arm["candidate_index"])])
                counts["holdout_arms"] += 1
        else:
            held = run / "holdout/predictions.json"
            check_summary(read(held), record["holdout_selected"])
            counts["holdout_selected_only"] += 1
        assert sha(held) == record["holdout_sha256"]
    print(
        json.dumps(
            {
                "manifest_sha256": sha(manifest),
                "manifest_files_verified": len(files),
                "historical_runs_verified": len(history["runs"]),
                "historical_counts": counts,
                "e05": runs,
            },
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
