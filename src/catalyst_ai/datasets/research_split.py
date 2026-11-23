"""Deterministic grouped research partitions, independent of historical splits."""

import hashlib
from collections import defaultdict


def partition(rows, *, strategy="random", train_fraction=0.8, folds=5, seed=42):
    """Allocate indivisible repeat groups (and DOI components when requested).

    Rows require record_id, doi and optionally repeat_group. No targets are read.
    """
    if strategy not in ("random", "doi") or not 0 < train_fraction < 1 or folds < 2:
        raise ValueError("invalid split settings")
    ids = [r["record_id"] for r in rows]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("empty dataset or duplicate record IDs")
    parent = {i: i for i in ids}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[max(a, b)] = min(a, b)

    seen = {}
    for r in rows:
        keys = []
        if r.get("repeat_group"):
            keys.append(("repeat", r["repeat_group"]))
        if strategy == "doi":
            if not r.get("doi"):
                raise ValueError("DOI required")
            keys.append(("doi", r["doi"]))
        for key in keys:
            if key in seen:
                union(r["record_id"], seen[key])
            else:
                seen[key] = r["record_id"]
    groups = defaultdict(list)
    for i in ids:
        groups[find(i)].append(i)
    ordered = sorted((sorted(v) for v in groups.values()), key=lambda v: hashlib.sha256(f"{seed}:{v[0]}".encode()).hexdigest())
    if len(ordered) < folds + 1:
        raise ValueError("insufficient independent groups")
    # Choose the prefix closest to the requested record count, preserving groups.
    n = min(range(folds, len(ordered)), key=lambda k: abs(sum(map(len, ordered[:k])) - len(ids) * train_fraction))
    train, test = ordered[:n], ordered[n:]
    buckets = [[] for _ in range(folds)]
    for group in sorted(train, key=lambda g: -len(g)):
        min(buckets, key=lambda b: sum(map(len, b))).append(group)
    return {"strategy": strategy, "seed": seed, "train_fraction": train_fraction,
            "folds": folds, "train": sorted(i for g in train for i in g),
            "test": sorted(i for g in test for i in g),
            "validation_folds": [sorted(i for g in b for i in g) for b in buckets],
            "groups": [g for g in ordered]}
