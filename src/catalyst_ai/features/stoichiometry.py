"""Small flat-formula checker for reviewed catalogs, never an eligibility decision."""

import re
from decimal import Decimal


def formula_counts(formula):
    # No aliases, parentheses, hydrates, charges, variables, or formula rescaling.
    from catalyst_ai.storage.feature_catalog import _ELEMENTS

    if not isinstance(formula, str) or len(formula) > 80:
        raise ValueError("unsupported formula")
    tokens = list(re.finditer(r"([A-Z][a-z]?)([0-9]+(?:\.[0-9]+)?)?", formula))
    if not tokens or "".join(t.group() for t in tokens) != formula:
        raise ValueError("unsupported formula")
    counts = {}
    for token in tokens:
        element, count = token.groups()
        n = Decimal(count or "1")
        if element not in _ELEMENTS or not n.is_finite() or n <= 0:
            raise ValueError("unsupported formula element or coefficient")
        counts[element] = counts.get(element, Decimal(0)) + n
    return {e: float(n) for e, n in counts.items()}
