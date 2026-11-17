"""Freeze the initial source-review queue without changing catalyst facts."""

import hashlib
import json
from pathlib import Path

from catalyst_ai.reporting.evidence import digest, write_json

SNAPSHOT = Path(
    "data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json"
)
EVIDENCE = Path("data/raw/s1-a-crossref-131111.json")
OUTPUT = Path("artifacts/reports/s1-a-source-candidates-v1.json")


def main():
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    sha = digest(snapshot["content"])
    if sha != snapshot["content_sha256"] or snapshot["snapshot_id"] != "snapshot-" + sha:
        raise ValueError("snapshot identity mismatch")
    raw = EVIDENCE.read_bytes()
    evidence_sha = hashlib.sha256(raw).hexdigest()
    if evidence_sha != "0936df76b764391c414f70b37f307c77f44f8eca24a711168a79fc0b15b27c49":
        raise ValueError("source evidence hash mismatch")
    metadata = json.loads(raw)["message"]
    if metadata["DOI"].lower() != "10.1016/j.fuel.2024.131111":
        raise ValueError("source DOI mismatch")
    rows = []
    for record in snapshot["content"]["records"]:
        payload = record["payload"]
        for index, component in enumerate(payload["recipe"]["components"]):
            if component["species"] != "InNi3O0.5":
                continue
            rows.append(
                {
                    "parent_snapshot_id": snapshot["snapshot_id"],
                    "record_id": record["record_id"],
                    "component_index": index,
                    "role": component["role"],
                    "original_species": component["species"],
                    "candidate_species": "InNi3C0.5",
                    "source_doi": payload["source"]["doi"],
                    "dataset_sample_name": payload["recipe"]["material_family"],
                    "dataset_locator": payload["extraction"]["locator"],
                    "evidence_location": (
                        "Crossref metadata title; original sample/test location unverified"
                    ),
                    "evidence_sha256": evidence_sha,
                    "review_status": "pending",
                    "rationale": (
                        "Metadata title and dataset sample name suggest C; original sample, "
                        "composition and test correspondence require review."
                    ),
                    "revision_version": "s1-a-candidate-v1",
                }
            )
    if len(rows) != 39 or any(r["source_doi"] != metadata["DOI"] for r in rows):
        raise ValueError("unexpected review scope")
    write_json(
        OUTPUT,
        {
            "schema_version": 1,
            "parent_snapshot_id": snapshot["snapshot_id"],
            "evidence": {
                "path": str(EVIDENCE),
                "sha256": evidence_sha,
                "url": "https://api.crossref.org/works/10.1016%2Fj.fuel.2024.131111",
                "type": "bibliographic_metadata_not_original_paper",
            },
            "records": rows,
        },
    )
    print(f"Wrote {len(rows)} pending candidates to {OUTPUT}")


if __name__ == "__main__":
    main()
