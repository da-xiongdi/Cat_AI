"""Read domain test records without initializing or changing the catalog."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path


def list_samples(path: Path, *, offset: int = 0, limit: int = 30) -> dict:
    path = Path(path).resolve()
    if not path.is_file():
        return {"status": "unavailable", "items": [], "total": None}
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("分页参数无效")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        total = conn.execute("SELECT count(*) FROM test_run").fetchone()[0]
        rows = conn.execute(
            "SELECT id,synthesis_id,payload FROM test_run ORDER BY id LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        items = []
        for row in rows:
            observations = conn.execute(
                "SELECT payload FROM performance_observation WHERE test_id=? ORDER BY id",
                (row["id"],),
            ).fetchall()
            items.append(
                {
                    "id": row["id"],
                    "synthesis_id": row["synthesis_id"],
                    "test": json.loads(row["payload"]),
                    "observations": [json.loads(x[0]) for x in observations],
                }
            )
            if "synthesis_run" in tables:
                synthesis = conn.execute(
                    "SELECT recipe_id,payload FROM synthesis_run WHERE id=?", (row["synthesis_id"],)
                ).fetchone()
                if synthesis:
                    items[-1]["synthesis"] = json.loads(synthesis["payload"])
                    if "catalyst_recipe" in tables:
                        recipe = conn.execute(
                            "SELECT payload FROM catalyst_recipe WHERE id=?",
                            (synthesis["recipe_id"],),
                        ).fetchone()
                        items[-1]["recipe"] = json.loads(recipe[0]) if recipe else None
    return {"status": "available", "items": items, "total": total, "offset": offset}
