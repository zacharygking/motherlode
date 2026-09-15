"""Chance-corrected agreement and bootstrap intervals.

Every agreement number reported by a motherlode consumer is chance-corrected, with an interval.
Raw agreement is computed too, labelled as raw, because base rates inflate it.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np


def prevalence(labels: Sequence[Any]) -> dict[Any, float]:
    """Share of each label. Empty input gives an empty dict."""
    n = len(labels)
    if n == 0:
        return {}
    return {k: v / n for k, v in sorted(Counter(labels).items(), key=lambda kv: str(kv[0]))}


def raw_agreement(a: Sequence[Any], b: Sequence[Any]) -> float:
    _same_length(a, b)
    return float(np.mean([x == y for x, y in zip(a, b)])) if len(a) else float("nan")


def cohen_kappa(a: Sequence[Any], b: Sequence[Any], labels: Sequence[Any] | None = None) -> float:
    """Cohen's kappa for two raters on nominal labels.

    Returns 1.0 when both raters agree everywhere on more than one label and NaN when both raters
    used a single label throughout, where kappa is undefined: observed and expected agreement are
    both 1 and there is nothing to correct for. Report prevalence beside kappa so that case shows.
    """
    _same_length(a, b)
    n = len(a)
    if n == 0:
        return float("nan")
    cats = list(labels) if labels is not None else sorted({*a, *b}, key=str)
    idx = {c: i for i, c in enumerate(cats)}
    m = np.zeros((len(cats), len(cats)))
    for x, y in zip(a, b):
        m[idx[x], idx[y]] += 1
    po = np.trace(m) / n
    pe = float(np.sum(m.sum(axis=1) * m.sum(axis=0)) / (n * n))
    if pe >= 1.0:
        return float("nan")
    return float((po - pe) / (1.0 - pe))


def weighted_kappa(a: Sequence[Any], b: Sequence[Any], scale: Sequence[Any], weights: str = "linear") -> float:
    """Cohen's weighted kappa for an ordinal scale, linear or quadratic disagreement weights.

    ``scale`` gives the order. Labels not on the scale raise. NaN when expected disagreement is
    zero (both raters used one label throughout), as for the unweighted version.
    """
    if weights not in ("linear", "quadratic"):
        raise ValueError("weights must be 'linear' or 'quadratic'")
    _same_length(a, b)
    n = len(a)
    if n == 0:
        return float("nan")
    idx = {c: i for i, c in enumerate(scale)}
    for x in (*a, *b):
        if x not in idx:
            raise ValueError(f"{x!r} is not on the scale {list(scale)}")
    k = len(scale)
    m = np.zeros((k, k))
    for x, y in zip(a, b):
        m[idx[x], idx[y]] += 1
    i, j = np.indices((k, k))
    w = np.abs(i - j) / max(k - 1, 1)
    if weights == "quadratic":
        w = w ** 2
    expected = np.outer(m.sum(axis=1), m.sum(axis=0)) / n
    d_o = float((w * m).sum())
    d_e = float((w * expected).sum())
    if d_e == 0:
        return float("nan")
    return float(1.0 - d_o / d_e)


def krippendorff_alpha(data: Sequence[Sequence[Any]], level: str = "nominal") -> float:
    """Krippendorff's alpha for any number of raters with missing values.

    ``data`` is raters x items; use ``None`` for a missing rating. ``level`` is ``nominal`` or
    ``interval``. Items rated by fewer than two raters are ignored.
    """
    if level not in ("nominal", "interval"):
        raise ValueError("level must be 'nominal' or 'interval'")
    units: list[list[Any]] = []
    n_items = max((len(r) for r in data), default=0)
    for j in range(n_items):
        vals = [r[j] for r in data if j < len(r) and r[j] is not None]
        if len(vals) >= 2:
            units.append(vals)
    if not units:
        return float("nan")

    def delta(x, y) -> float:
        if level == "nominal":
            return 0.0 if x == y else 1.0
        return float(x - y) ** 2

    # observed disagreement: within-unit pairs, weighted by 1/(m_u - 1)
    n_total = sum(len(u) for u in units)
    d_o = 0.0
    for u in units:
        m = len(u)
        s = sum(delta(u[i], u[k]) for i in range(m) for k in range(m) if i != k)
        d_o += s / (m - 1)
    d_o /= n_total
    # expected disagreement: all pairs across all values
    allv = [v for u in units for v in u]
    s = 0.0
    for i in range(len(allv)):
        for k in range(len(allv)):
            if i != k:
                s += delta(allv[i], allv[k])
    d_e = s / (n_total * (n_total - 1))
    if d_e == 0:
        return 1.0
    return float(1.0 - d_o / d_e)


def bootstrap(
    stat: Callable[..., float],
    *arrays: Sequence[Any],
    n: int = 2000,
    seed: int = 0,
    alpha: float = 0.05,
) -> tuple[float, float, float]:
    """Paired percentile bootstrap over items. Returns (estimate, low, high).

    ``stat`` receives the resampled arrays in the same order they were passed.
    """
    if not arrays:
        raise ValueError("bootstrap needs at least one array")
    size = len(arrays[0])
    for arr in arrays:
        if len(arr) != size:
            raise ValueError("all arrays must have the same length")
    arrays = tuple(list(a) for a in arrays)
    est = float(stat(*arrays))
    if size == 0:
        return est, float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    draws = np.empty(n)
    for b in range(n):
        ix = rng.integers(0, size, size)
        draws[b] = stat(*([a[i] for i in ix] for a in arrays))
    draws = draws[~np.isnan(draws)]
    if len(draws) == 0:
        return est, float("nan"), float("nan")
    lo, hi = np.percentile(draws, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return est, float(lo), float(hi)


def agreement_report(
    human: Sequence[Any],
    judge: Sequence[Any],
    labels: Sequence[Any] | None = None,
    n_boot: int = 2000,
    seed: int = 0,
) -> dict:
    """Kappa with a bootstrap interval, prevalence for both raters, and raw agreement labelled as such."""
    _same_length(human, judge)
    k, lo, hi = bootstrap(lambda a, b: cohen_kappa(a, b, labels), human, judge, n=n_boot, seed=seed)
    return {
        "n": len(human),
        "kappa": k,
        "kappa_ci95": [lo, hi],
        "raw_agreement_do_not_report": raw_agreement(human, judge),
        "prevalence_human": prevalence(human),
        "prevalence_judge": prevalence(judge),
    }


def _same_length(a: Sequence[Any], b: Sequence[Any]) -> None:
    if len(a) != len(b):
        raise ValueError(f"length mismatch: {len(a)} vs {len(b)}")
