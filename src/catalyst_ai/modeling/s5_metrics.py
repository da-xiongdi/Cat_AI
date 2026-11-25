"""Descriptive S5 comparisons; never used for model selection."""

import math

from catalyst_ai.modeling.baseline import metrics
from catalyst_ai.modeling.s5_selection import _available


def compare(arms):
    """Compare named prediction lists on their individual and strict shared support."""
    if not arms:
        raise ValueError("no arms")
    indexed = {}
    reference = None
    for name, rows in arms.items():
        mapping = {row["record_id"]: row for row in rows}
        if not mapping or len(mapping) != len(rows):
            raise ValueError("empty or duplicate predictions")
        if reference is not None:
            if set(mapping) != set(reference):
                raise ValueError("different members")
            for key, row in mapping.items():
                if (row.get("observed"), row.get("fold")) != (
                    reference[key].get("observed"), reference[key].get("fold")
                ):
                    raise ValueError("target or fold mismatch")
        else:
            reference = mapping
        if any(not isinstance(r.get("observed"), (int, float)) or isinstance(r["observed"], bool)
               or not math.isfinite(r["observed"]) for r in rows):
            raise ValueError("invalid target")
        indexed[name] = mapping

    def summary(mapping, ids):
        rows = [mapping[i] for i in sorted(ids)]
        if not rows:
            return {"records": 0, "mae": None, "rmse": None, "r2": None,
                    "r2_unavailable_reason": "no available records"}
        return {"records": len(rows), **metrics([r["observed"] for r in rows],
                                                [r["raw_prediction"] for r in rows])}

    def section(ids):
        valid = {name: {i for i in ids if _available(mapping[i])}
                 for name, mapping in indexed.items()}
        shared = set.intersection(*valid.values())
        return {"denominator": len(ids), "common_ids": sorted(shared),
                "arms": {name: {"available": len(valid[name]),
                                "coverage": len(valid[name]) / len(ids) if ids else None,
                                "individual": summary(mapping, valid[name]),
                                "common": summary(mapping, shared)}
                         for name, mapping in indexed.items()}}

    all_ids = set(reference)
    folds = {r.get("fold") for r in reference.values()}
    result = {"overall": section(all_ids)}
    if folds != {None}:
        if None in folds:
            raise ValueError("inconsistent folds")
        result["folds"] = {str(f): section({i for i in all_ids if reference[i]["fold"] == f})
                           for f in sorted(folds)}
    return result
