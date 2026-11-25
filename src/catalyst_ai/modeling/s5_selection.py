"""S5 training-side paired selection, versioned separately from S4 selection."""

import math


class SelectionUnavailable(ValueError):
    def __init__(self, decision):
        self.decision = decision
        super().__init__("S5 baseline does not meet selection support; no model can be locked")


def _available(row):
    value = row.get("raw_prediction")
    return (
        row.get("status") in ("ok", "caution")
        and isinstance(value, (float, int))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def select(results):
    """Compare identical OOF records; return auditable selection or an explicit gap.

    Frozen S5 thresholds: >=80% total coverage, no more than 5 percentage
    points below baseline, >=30 and >=80% baseline common support; 0.1 pp tie.
    """
    if not results:
        raise ValueError("empty candidate list")
    expected = None
    maps = []
    for result in results:
        rows = result["predictions"]
        indexed = {r["record_id"]: r for r in rows}
        if not indexed or len(indexed) != len(rows):
            raise ValueError("empty or duplicate OOF records")
        if expected is None:
            expected = indexed
        elif set(indexed) != set(expected):
            raise ValueError("candidates must share OOF members")
        for key, row in indexed.items():
            if row.get("fold") != expected[key].get("fold") or row.get("observed") != expected[
                key
            ].get("observed"):
                raise ValueError("OOF fold or target mismatch")
            if not isinstance(row.get("observed"), (int, float)) or not math.isfinite(
                row["observed"]
            ):
                raise ValueError("invalid target")
        maps.append(indexed)
    base = results[0]["candidate"]
    if base.get("feature") != "F_base" or base.get("model") != "extra_trees":
        raise ValueError("first candidate must be F_base/extra_trees baseline")
    n = len(expected)
    available = [{i for i, row in m.items() if _available(row)} for m in maps]
    baseline = available[0]
    base_coverage = len(baseline) / n
    minimum = max(30, math.ceil(0.8 * len(baseline)))

    def mae(index, ids):
        return sum(
            abs(maps[index][i]["observed"] - maps[index][i]["raw_prediction"]) for i in ids
        ) / len(ids)

    comparisons = []
    for index, avail in enumerate(available):
        common = avail & baseline
        reasons = []
        if len(avail) / n < 0.8:
            reasons.append("coverage_below_80_percent")
        if len(avail) / n + 1e-12 < base_coverage - 0.05:
            reasons.append("coverage_below_baseline_minus_5pp")
        if len(common) < minimum:
            reasons.append("insufficient_baseline_common_support")
        comparisons.append(
            {
                "candidate_index": index,
                "total": n,
                "available": len(avail),
                "coverage": len(avail) / n,
                "coverage_delta_vs_baseline": (len(avail) - len(baseline)) / n,
                "common_with_baseline": len(common),
                "common_ids": sorted(common),
                "candidate_mae": mae(index, common) if common else None,
                "baseline_mae": mae(0, common) if common else None,
                "mae_delta_vs_baseline": (mae(index, common) - mae(0, common)) if common else None,
                "new_coverage_ids": sorted(avail - baseline),
                "lost_coverage_ids": sorted(baseline - avail),
                "eligible": not reasons,
                "reasons": reasons,
            }
        )
    eligible = [i for i, c in enumerate(comparisons) if c["eligible"]]
    decision = {
        "version": "s5-paired-v1",
        "minimum_common": minimum,
        "comparisons": comparisons,
        "selected_index": None,
        "reason": None,
    }
    if 0 not in eligible:
        decision["reason"] = "baseline_not_eligible_no_selection"
        return decision
    shared = set.intersection(*(available[i] for i in eligible))
    decision["selection_common_ids"] = sorted(shared)
    if len(shared) < minimum:
        decision.update(
            selected_index=0, reason="insufficient_all_candidate_common_support_baseline_fallback"
        )
        return decision
    scores = {i: mae(i, shared) for i in eligible}
    best = min(scores.values())
    tied = [i for i in eligible if scores[i] <= best + 0.1 + 1e-12]
    chosen = 0 if 0 in tied else min(tied)
    decision.update(
        selected_index=chosen,
        reason="baseline_tie" if chosen == 0 else "lowest_oof_mae_within_0.1pp_then_catalog_order",
        selection_common_mae=scores,
    )
    return decision


def predict(transformer, model, records):
    """Keep one output per input, including hard rejection and non-finite output."""
    out = []
    valid = []
    vectors = []
    for row in records:
        item = dict(transformer.transform_one(row["payload"], diagnostic=True))
        values = item.pop("values", None)
        item["raw_prediction"] = None
        if values is None or any(v is None or not math.isfinite(v) for v in values):
            item["status"] = (
                item.get("status")
                if item.get("status") not in (None, "ok", "caution")
                else "unencodable"
            )
        else:
            valid.append(len(out))
            vectors.append(values)
        out.append(item)
    if vectors:
        for idx, value in zip(valid, model.predict(vectors), strict=True):
            value = float(value)
            if not math.isfinite(value):
                out[idx]["status"] = "non_finite_prediction"
            else:
                out[idx]["raw_prediction"] = value
                if not 0 <= value <= 100:
                    status = out[idx].get("status", "ok")
                    out[idx]["status"] = (
                        "output_out_of_range" if status == "ok" else status + "+output_out_of_range"
                    )
    return out


def diagnostics(rows):
    """Report diagnostic, available and rejected denominators for nullable rows."""
    from collections import Counter

    from catalyst_ai.modeling.experiments import _score

    finite = [
        r
        for r in rows
        if isinstance(r.get("raw_prediction"), (int, float))
        and not isinstance(r["raw_prediction"], bool)
        and math.isfinite(r["raw_prediction"])
    ]
    available = [r for r in rows if _available(r)]
    return {
        "total_records": len(rows),
        "diagnostic_records": len(finite),
        "available_records": len(available),
        "available_fraction": len(available) / len(rows) if rows else None,
        "null_prediction_records": sum(r.get("raw_prediction") is None for r in rows),
        "statuses": dict(sorted(Counter(r.get("status", "unknown") for r in rows).items())),
        "diagnostic_metrics": _score(finite) if finite else None,
        "available_metrics": _score(available) if available else None,
    }
