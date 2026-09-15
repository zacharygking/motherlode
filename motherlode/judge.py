"""Prospect: validate a judge against human labels, per dimension.

Label rows are JSONL, one row per item, rater, dimension and pass::

    {"item_id": "3f2a9c1e", "rater": "zachary", "dimension": "D4", "label": "2",
     "rubric_hash": "b6d251d6a3fe", "pass": "blind"}

A row with no ``dimension`` is read as the single dimension ``label``, so single-label files
work unchanged. ``pass`` is ``blind`` for labels committed before the judge was shown,
``revealed`` for a revision after; it defaults to blind. The headline number is always the blind
pass. A rater named ``ground_truth`` is a rater like any other, so a checker's verdict on one
dimension gets the same agreement report as a person's.

Per dimension the report gives Cohen's kappa with a bootstrap interval, weighted kappa (linear
and quadratic) when the spec says the scale is ordinal, prevalence for both raters, the number
of items excluded because either side said NA, and Krippendorff's alpha across humans when there
are two or more. NA is never a label in the statistics: an item is dropped from a dimension when
either rater marked it NA, and the count is reported so a thin dimension shows as thin.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .rubric import NA, RubricSpec, single_label_spec
from .stats import agreement_report, cohen_kappa, krippendorff_alpha, weighted_kappa

ADJUDICATION_VERDICTS = ("judge_wrong", "human_wrong", "rubric_ambiguous")
TRUTH = "ground_truth"


def read_labels(path: Path | str) -> list[dict]:
    rows = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _dim(row: dict) -> str:
    return str(row.get("dimension", "label"))


def _by_item(rows: Iterable[dict], rater: str | None, dimension: str, pass_: str = "blind") -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:
        if rater is not None and r.get("rater") != rater:
            continue
        if r.get("pass", "blind") != pass_ or _dim(r) != dimension:
            continue
        out[str(r["item_id"])] = r
    return out


def raters(rows: Iterable[dict]) -> list[str]:
    return sorted({str(r.get("rater")) for r in rows if r.get("rater") is not None})


def dimensions_in(rows: Iterable[dict]) -> list[str]:
    return sorted({_dim(r) for r in rows})


def _spec_for(rows_a: Sequence[dict], rows_b: Sequence[dict], spec: RubricSpec | None) -> RubricSpec:
    if spec is not None:
        return spec
    dims = dimensions_in(list(rows_a) + list(rows_b))
    if dims == ["label"]:
        labels = sorted({str(r["label"]) for r in (*rows_a, *rows_b) if str(r["label"]) != NA}, key=str)
        return single_label_spec(labels)
    raise ValueError("label files have dimensions; pass the rubric spec so scales and ordinality are known")


def compare(human_rows: Sequence[dict], judge_rows: Sequence[dict], dimension: str, spec: RubricSpec,
            human_rater: str | None = None, judge_rater: str | None = None, n_boot: int = 2000, seed: int = 0) -> dict:
    """Agreement between one human's blind pass and one judge on one dimension."""
    d = spec.dimension(dimension)
    h_by = _by_item(human_rows, human_rater, dimension)
    j_by = _by_item(judge_rows, judge_rater, dimension)
    common = sorted(set(h_by) & set(j_by))
    pairs = [(str(h_by[i]["label"]), str(j_by[i]["label"])) for i in common]
    na_excluded = sum(1 for a, b in pairs if a == NA or b == NA)
    kept = [(a, b) for a, b in pairs if a != NA and b != NA]
    out: dict[str, Any] = {"dimension": dimension, "items_in_common": len(common), "na_excluded": na_excluded,
                           "n": len(kept)}
    if not kept:
        out.update({"kappa": float("nan"), "kappa_ci95": [float("nan"), float("nan")]})
        return out
    h = [a for a, _ in kept]
    j = [b for _, b in kept]
    out.update(agreement_report(h, j, list(d.scale), n_boot, seed))
    if d.ordinal and len(d.scale) > 2:
        out["weighted_kappa_linear"] = weighted_kappa(h, j, list(d.scale), "linear")
        out["weighted_kappa_quadratic"] = weighted_kappa(h, j, list(d.scale), "quadratic")
    revealed = _by_item(human_rows, human_rater, dimension, "revealed")
    rev_items = [i for i in common if i in revealed and str(h_by[i]["label"]) != NA and str(j_by[i]["label"]) != NA]
    if rev_items:
        h_bl = [str(h_by[i]["label"]) for i in rev_items]
        h_rv = [str(revealed[i]["label"]) for i in rev_items]
        j_rv = [str(j_by[i]["label"]) for i in rev_items]
        out["after_reveal"] = {
            "items": len(rev_items),
            "labels_changed": sum(a != b for a, b in zip(h_bl, h_rv)) / len(rev_items),
            "kappa": cohen_kappa(h_rv, j_rv, list(d.scale)),
            "moved_toward_judge": sum((a != b) and (b == c) for a, b, c in zip(h_bl, h_rv, j_rv)) / len(rev_items),
        }
    return out


def validate(human_rows: Sequence[dict], judge_rows: Sequence[dict], spec: RubricSpec | None = None,
             human_rater: str | None = None, judge_rater: str | None = None, truth_rows: Sequence[dict] = (),
             n_boot: int = 2000, seed: int = 0) -> dict:
    """The full report: every dimension, human versus judge, plus each against ground truth when
    truth rows exist, the rubric-hash check, and the human-human ceiling."""
    spec = _spec_for(human_rows, judge_rows, spec)
    if judge_rater is None:
        js = [r for r in raters(judge_rows) if r != TRUTH]
        if len(js) > 1:
            raise ValueError(f"several judges in the judge file {js}; pass judge_rater")
        judge_rater = js[0] if js else None
    if human_rater is None:
        hs = [r for r in raters(human_rows) if r != TRUTH]
        human_rater = hs[0] if len(hs) == 1 else None
    report: dict[str, Any] = {"pass": "blind", "human_rater": human_rater, "judge_rater": judge_rater,
                              "rubric_hash": spec.hash, "dimensions": {}}
    hashes = {r.get("rubric_hash") for r in (*human_rows, *judge_rows, *truth_rows) if r.get("rubric_hash")}
    report["rubric_hashes_seen"] = sorted(hashes)
    report["rubric_consistent"] = hashes <= {spec.hash} if spec.text else len(hashes) <= 1
    for d in spec.dimensions:
        entry = {"human_vs_judge": compare(human_rows, judge_rows, d.id, spec, human_rater, judge_rater, n_boot, seed)}
        if truth_rows and any(_dim(r) == d.id for r in truth_rows):
            entry["judge_vs_truth"] = compare(truth_rows, judge_rows, d.id, spec, TRUTH, judge_rater, n_boot, seed)
            entry["human_vs_truth"] = compare(truth_rows, human_rows, d.id, spec, TRUTH, human_rater, n_boot, seed)
        report["dimensions"][d.id] = entry
    humans = [r for r in raters(human_rows) if r != TRUTH]
    if len(humans) >= 2:
        report["human_human"] = {}
        for d in spec.dimensions:
            items = sorted({str(r["item_id"]) for r in human_rows if _dim(r) == d.id})
            matrix = []
            for h in humans:
                by = _by_item(human_rows, h, d.id)
                matrix.append([by[i]["label"] if i in by and str(by[i]["label"]) != NA else None for i in items])
            level = "interval" if d.ordinal else "nominal"
            data = [[(d.scale.index(v) if (level == "interval" and v is not None) else v) for v in row] for row in matrix]
            report["human_human"][d.id] = {"raters": humans, "level": level, "alpha": krippendorff_alpha(data, level)}
    return report


def summary_table(report: dict) -> str:
    """One line per dimension, the thing a person reads first."""
    lines = [f"{'dim':6s} {'n':>4s} {'NA':>3s} {'kappa':>7s} {'ci95':>16s} {'w-lin':>6s} {'vs truth':>9s}"]
    for dim, entry in report["dimensions"].items():
        c = entry["human_vs_judge"]
        k = c.get("kappa", float("nan"))
        ci = c.get("kappa_ci95", [float("nan")] * 2)
        wl = c.get("weighted_kappa_linear", float("nan"))
        jt = entry.get("judge_vs_truth", {}).get("kappa", float("nan"))
        f = lambda x: "  nan" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:5.2f}"
        lines.append(f"{dim:6s} {c['n']:4d} {c['na_excluded']:3d} {f(k):>7s} [{f(ci[0])},{f(ci[1])}] {f(wl):>6s} {f(jt):>9s}")
    return "\n".join(lines)


def validate_judge(human_rows: Sequence[dict], judge_rows: Sequence[dict], human_rater: str | None = None,
                   labels: Sequence[Any] | None = None, n_boot: int = 2000, seed: int = 0) -> dict:
    """v0.1 shape for single-label files: the ``label`` dimension's human-versus-judge block plus
    the rubric check and the human-human ceiling."""
    spec = single_label_spec(labels) if labels else None
    rep = validate(human_rows, judge_rows, spec, human_rater, n_boot=n_boot, seed=seed)
    dim = next(iter(rep["dimensions"]))
    out = {"pass": "blind", **rep["dimensions"][dim]["human_vs_judge"],
           "rubric_hashes": rep["rubric_hashes_seen"], "rubric_consistent": rep["rubric_consistent"]}
    if "human_human" in rep:
        hh = rep["human_human"][dim]
        out["human_human"] = {"raters": hh["raters"], "alpha_nominal": hh["alpha"]}
    return out


def adjudication_template(human_rows: Sequence[dict], judge_rows: Sequence[dict], human_rater: str | None = None,
                          judge_rater: str | None = None) -> list[dict]:
    """One row per disagreement and dimension, with an empty verdict to fill in: judge_wrong,
    human_wrong or rubric_ambiguous. The headline kappa is computed before adjudication, never after."""
    rows = []
    for dim in dimensions_in(list(human_rows) + list(judge_rows)):
        human = _by_item(human_rows, human_rater, dim)
        judge = _by_item(judge_rows, judge_rater, dim)
        for item in sorted(set(human) & set(judge)):
            h, j = str(human[item]["label"]), str(judge[item]["label"])
            if h != j:
                rows.append({"item_id": item, "dimension": dim, "human": h, "judge": j,
                             "kind": "applicability" if NA in (h, j) else "label",
                             "judge_rationale": judge[item].get("rationale", ""), "verdict": "", "note": ""})
    return rows


def write_jsonl(rows: Iterable[dict], path: Path | str) -> None:
    from .dataset import write_jsonl as _w
    _w(rows, path)
