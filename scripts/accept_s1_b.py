"""Verify the fixed S1-B v4 build, then record its engineering acceptance."""

import json
import math
import sqlite3
import subprocess
import sys
import uuid
from copy import deepcopy
from pathlib import Path

from catalyst_ai.features.build import build
from catalyst_ai.features.physchem import PROPERTIES, ROLES, calculate, model_values
from catalyst_ai.features.pipeline import project
from catalyst_ai.modeling.predictor import _payload
from catalyst_ai.storage.feature_build import persist
from catalyst_ai.storage.feature_catalog import get_catalog, get_evidence, query_entries
from catalyst_ai.workbench import adapters, backup, index, research, service
from catalyst_ai.workbench.predictions import sha


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def equal_values(left, right):
    assert left.keys() == right.keys()
    for key, value in left.items():
        other = right[key]
        assert (value is None and other is None) or (
            value is not None
            and other is not None
            and math.isclose(value, other, rel_tol=1e-12, abs_tol=1e-12)
        ), key


def main():
    root = Path(__file__).resolve().parents[1]
    tag = uuid.uuid4().hex[:12]
    out = root / "artifacts/reports" / ("s1-b-acceptance-20261117-" + tag)
    out.mkdir(parents=True)
    database = root / "data/catalog.sqlite"
    management = root / "data/workbench.sqlite"
    folder = root / "artifacts/reports/s1-b-20261113-v4"
    selection, features = load(folder / "selection.json"), load(folder / "features.json")
    binding = selection["content"]["binding"]
    paths = [database, folder / "selection.json", folder / "features.json"]
    paths += [
        p
        for directory in ("data/snapshots", "artifacts/models", "data/raw")
        for p in (root / directory).rglob("*")
        if p.is_file()
    ]
    paths += [
        root / "configs" / name
        for name in (
            "s1_element_properties_v2.json",
            "s1_species_mapping_v2.json",
            "s1_source_review_v2.json",
        )
    ]

    def hashes():
        return {p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in paths}

    before = hashes()
    backup.backup_database(database, out / "catalog-copy.sqlite")
    copied = out / "catalog-copy.sqlite"
    snapshot = load(root / "data/snapshots" / (binding["snapshot_id"] + ".json"))
    qualification = load(
        root / "data/snapshots/qualifications" / (binding["qualification_id"] + ".json")
    )
    split = load(root / "artifacts/reports/themecat-i2-20261110/split-verified.json")
    properties = get_catalog(copied, "properties", binding["property_version"])
    species = get_catalog(copied, "species", binding["mapping_version"])
    review = get_evidence(copied, binding["review_version"])
    query_entries(copied, "properties", binding["property_version"])
    query_entries(copied, "species", binding["mapping_version"])
    replay = build(snapshot, qualification, split, properties, species, review, root=root)
    assert replay == (selection, features)
    for name, expected in binding["implementation_sha256"].items():
        assert sha((root / "src/catalyst_ai/features" / name).read_bytes()) == expected
    indexed = adapters.verify_feature_catalog(
        database, folder / "selection.json", folder / "features.json"
    )
    persist(copied, *replay)
    persist(copied, *replay)
    with sqlite3.connect(copied) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    records = {r["record_id"]: r["payload"] for r in snapshot["content"]["records"]}
    mappings = {m["species"]: m for m in species["catalog"]["entries"]}
    props = {
        (p["element"], p["property"]): p["value"]
        for p in properties["catalog"]["entries"]
        if p["state"] == "available"
    }
    absent_roles = 0
    for row in features["content"]["rows"]:
        payload = records[row["record_id"]]
        projected = project(payload)
        expected = {name: value["value"] for name, value in row["derived"].items()}
        manual = {}
        for role, label in ROLES.items():
            components = [
                (name, amount)
                for (r, name), amount in projected["amounts"].items()
                if r == role and amount > 0
            ]
            weights = [
                (element, amount * count)
                for name, amount in components
                for element, count in mappings[name]["centers"].items()
            ]
            manual[label + "_material_mol_pct"] = math.fsum(amount for _, amount in components)
            manual[label + "_species_count"] = len(components)
            denominator = math.fsum(weight for _, weight in weights)
            absent_roles += not bool(denominator)
            for prop in PROPERTIES:
                manual[label + "_mean_" + prop] = (
                    math.fsum(weight * props[element, prop] for element, weight in weights)
                    / denominator
                    if denominator
                    else None
                )
        for prop in PROPERTIES:
            a, b = (manual[role + "_mean_" + prop] for role in ROLES.values())
            manual["active_minus_support_" + prop] = (
                a - b if a is not None and b is not None else None
            )
        equal_values(manual, expected)
        normalized = _payload(
            {
                **projected["conditions"],
                "components": [
                    dict(role=role, species=name, mol_pct=amount)
                    for (role, name), amount in projected["amounts"].items()
                ],
            }
        )
        equal_values(calculate(normalized, properties, species), expected)
        permuted = deepcopy(payload)
        permuted["recipe"]["components"].reverse()
        equal_values(calculate(permuted, properties, species), expected)
        merged = deepcopy(payload)
        component = next(
            c for c in merged["recipe"]["components"] if c["amount"]["normalized_value"] > 0
        )
        duplicate = deepcopy(component)
        component["amount"]["normalized_value"] /= 2
        duplicate["amount"]["normalized_value"] = component["amount"]["normalized_value"]
        merged["recipe"]["components"].append(duplicate)
        equal_values(calculate(merged, properties, species), expected)
        assert len(model_values(expected, "F1")) == 4
        assert len(model_values(expected, "F2")) == 10
        assert all(
            v["state"] == ("not_applicable" if v["value"] is None else "available")
            for v in row["derived"].values()
        )
    counts = selection["content"]["counts"]
    assert [counts[p]["retained"]["records"] for p in ("train", "validation", "test")] == [
        454,
        47,
        52,
    ]
    assert [counts[p]["excluded"]["records"] for p in ("train", "validation", "test")] == [39, 0, 1]
    retained = selection["content"]["retained"]
    assert len(set().union(*(set(ids) for ids in retained.values()))) == 553
    excluded_species = []
    for part, ids in retained.items():
        original = set(split["content"]["splits"][part]["record_ids"])
        assert set(ids) <= original
        for excluded in selection["content"]["excluded"][part]:
            assert excluded["reason"] and excluded["record_id"] in original
            names = {c["species"] for c in records[excluded["record_id"]]["recipe"]["components"]}
            excluded_species.append("InNi3O0.5" if "InNi3O0.5" in names else "CoGaAlO4")
            assert "InNi3O0.5" in names or "CoGaAlO4" in names
    assert excluded_species.count("InNi3O0.5") == 39 and excluded_species.count("CoGaAlO4") == 1
    tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--junitxml=" + str(out / "tests.xml")],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )
    (out / "tests.log").write_text(tests.stdout + tests.stderr, encoding="utf-8")
    assert tests.returncode == 0, tests.stdout + tests.stderr
    assert before == hashes(), "protected source data changed"
    report = dict(
        actor="Codex",
        scope="S1-B engineering acceptance only",
        indexed=indexed,
        binding=binding,
        counts=counts,
        exact_replay=True,
        manual_formula_rows=553,
        normalized_input_rows=553,
        permutation_rows=553,
        split_merge_rows=553,
        absent_roles=absent_roles,
        pytest_returncode=tests.returncode,
        protected_unchanged=True,
        protected_hashes=before,
        limitations=[
            "No F1/F2 model training or performance claim",
            "No enhanced prediction package",
            "Dataset source acceptance; pressure assumption; historical test only",
        ],
    )
    target = out / "verification.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    backup.backup_database(management, out / "workbench-before.sqlite")
    artifact_id = "S1B-acceptance-" + tag
    index.register(
        management,
        "cat-ai",
        artifact_id,
        "attachment",
        target.relative_to(root).as_posix(),
        request_id=artifact_id,
        actor="Codex",
    )
    index.register(
        management,
        "cat-ai",
        "S1B-acceptance-tests-" + tag,
        "attachment",
        (out / "tests.log").relative_to(root).as_posix(),
        request_id="tests-" + tag,
        actor="Codex",
    )
    index.scan(management, "cat-ai")
    task = service.get_task(management, "S1B-01")
    if task["status"] == "done":
        print("Already accepted; verified new evidence at " + str(target))
        return
    assert task["status"] == "planned", task["status"]
    service.update_task(
        management,
        "S1B-01",
        task["revision"],
        {"deliverables": ["v4 selection/features, 5530 indexed values, replay verification"]},
        request_id="deliver-" + tag,
        actor="Codex",
    )
    for state in ("ready", "in_progress"):
        task = service.get_task(management, "S1B-01")
        service.transition(
            management, "S1B-01", task["revision"], state, request_id=state + tag, actor="Codex"
        )
    task = service.get_task(management, "S1B-01")
    results = [
        dict(
            criterion_id=c["criterion_id"],
            passed=True,
            evidence_id=artifact_id,
            evidence_version=sha(target.read_bytes()),
            explanation="Verified fixed v4 build; see report",
        )
        for c in task["criteria"]
    ]
    service.submit_review(
        management,
        "S1B-01",
        task["revision"],
        results,
        "Engineering scope passed; F1/F2 training and enhanced prediction remain S2.",
        request_id="submit-" + tag,
        actor="Codex",
    )
    task = service.get_task(management, "S1B-01")
    service.accept_review(
        management,
        "S1B-01",
        task["revision"],
        "Accepted fixed v4 feature construction; no model performance conclusion.",
        request_id="accept-" + tag,
        actor="Codex",
    )
    issues = [
        i for i in research.list_records(management, "cat-ai", "issues") if i["id"] == "DIFF-S1B"
    ]
    content = issues[0]["content"]
    for ref in content["evidence"]:
        ref.pop("status", None)
    content.update(
        status="resolved", conclusion="Fixed v4 replay and engineering acceptance completed."
    )
    content["evidence"].append(
        dict(id=artifact_id, version=sha(target.read_bytes()), role="acceptance")
    )
    research.save(
        management,
        "cat-ai",
        "issues",
        "DIFF-S1B",
        content,
        issues[0]["revision"],
        request_id="resolve-" + tag,
        actor="Codex",
    )
    print(str(target))


if __name__ == "__main__":
    main()
