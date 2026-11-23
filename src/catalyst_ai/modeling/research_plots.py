"""Dependency-free SVG diagnostic plots for numeric holdout results."""

from catalyst_ai.reporting.evidence import write_new


def _svg(path, title, points, xlabel, ylabel, diagonal=False):
    xs, ys = zip(*points, strict=True)
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    if diagonal:
        xmin = ymin = min(xmin, ymin)
        xmax = ymax = max(xmax, ymax)
    if xmin == xmax:
        xmin, xmax = xmin - 1, xmax + 1
    if ymin == ymax:
        ymin, ymax = ymin - 1, ymax + 1

    def xy(x, y):
        return 65 + (x - xmin) / (xmax - xmin) * 500, 350 - (y - ymin) / (ymax - ymin) * 290

    circles = "".join(
        f'<circle cx="{a:.2f}" cy="{b:.2f}" r="3" fill="#2878a8" fill-opacity="0.65"/>'
        for a, b in (xy(x, y) for x, y in points)
    )
    line = '<line x1="65" y1="350" x2="565" y2="60" stroke="#999"/>' if diagonal else ""
    doc = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="420" '
        'viewBox="0 0 640 420"><rect width="640" height="420" fill="white"/>'
        f'<text x="320" y="28" text-anchor="middle">{title}</text>'
        f'<path d="M65 60V350H565" fill="none" stroke="black"/>{line}{circles}'
        f'<text x="315" y="400" text-anchor="middle">{xlabel} ({xmin:.3g} to {xmax:.3g})</text>'
        '<text x="18" y="210" transform="rotate(-90 18 210)" text-anchor="middle">'
        f'{ylabel} ({ymin:.3g} to {ymax:.3g})</text></svg>'
    )
    write_new(path, doc.encode("utf-8"))


def write_plots(output, predictions):
    observed = [p["observed"] for p in predictions]
    predicted = [p["raw_prediction"] for p in predictions]
    residual = [y - x for x, y in zip(observed, predicted, strict=True)]
    _svg(
        output / "observed-predicted.svg",
        "Observed vs predicted",
        list(zip(observed, predicted, strict=True)),
        "Observed",
        "Predicted",
        True,
    )
    _svg(
        output / "residuals.svg",
        "Residuals vs observed",
        list(zip(observed, residual, strict=True)),
        "Observed",
        "Predicted - observed",
    )
    low, high = min(residual), max(residual)
    width = (high - low) / 10 if high != low else 1
    counts = [0] * 10
    for r in residual:
        counts[min(9, int((r - low) / width))] += 1
    _svg(
        output / "error-distribution.svg",
        "Residual distribution",
        [(low + (i + 0.5) * width, n) for i, n in enumerate(counts)],
        "Residual bin center",
        "Count",
    )
