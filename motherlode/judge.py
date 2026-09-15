"""Validate a judge against human labels.

Label files are JSONL, one row per label::

    {"item_id": "...", "rater": "zachary", "label": "sound", "rubric_hash": "...", "pass": "blind"}

The judge's file has the same shape with ``rater`` set to the judge's name. ``pass`` is ``blind``
for labels committed before the judge was shown, ``revealed`` for a revision after. The headline
number is always the blind pass. If a revealed pass exists, the shift is reported beside it.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .stats import agreement_report, cohen_kappa, krippendorff_alpha

ADJUDICATION_VERDICTS = ("judge_wrong", "human_wrong", "rubric_ambiguous")


def read_labels(path: Path | str) -> list[dict]:
    rows = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _by_item(rows: Iterable[dict], rater: str | None = None, pass_: str = "blind") -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:
        if rater is not None and r.get("rater") != rater:
            continue
        if r.get("pass", "blind") != pass_:
            continue
        out[str(r["item_id"])] = r
    return out


def validate_judge(
    human_rows: Sequence[dict],
    judge_rows: Sequence[dict],
    human_rater: str | None = None,
    labels: Sequence[Any] | None = None,
    n_boot: int = 2000,
    seed: int = 0,
) -> dict:
    """Kappa between the blind human pass and the judge, prevalence, rubric-hash check, and the
    post-reveal shift if the human file has a ``revealed`` pass. Second human raters, if present,
    give Krippendorff's alpha across all humans as the human-human ceiling."""
    human_blind = _by_item(human_rows, human_rater, "blind")
    judge_by = _by_item(judge_rows, None, "blind")
    common = sorted(set(human_blind) & set(judge_by))
    if not common:
        raise ValueError("no items in common between the human blind pass and the judge")
    h = [human_blind[i]["label"] for i in common]
    j = [judge_by[i]["label"] for i in common]
    report: dict[str, Any] = {"pass": "blind", **agreement_report(h, j, labels, n_boot, seed)}
    hashes = {r.get("rubric_hash") for r in human_rows} | {r.get("rubric_hash") for r in judge_rows}
    report["rubric_hashes"] = sorted(x for x in hashes if x)
    report["rubric_consistent"] = len(report["rubric_hashes"]) <= 1

    revealed = _by_item(human_rows, human_rater, "revealed")
    if revealed:
        rev_items = [i for i in common if i in revealed]
        if rev_items:
            h_rev = [revealed[i]["label"] for i in rev_items]
            h_bl = [human_blind[i]["label"] for i in rev_items]
            j_rev = [judge_by[i]["label"] for i in rev_items]
            report["after_reveal"] = {
                "items": len(rev_items),
                "labels_changed": sum(a != b for a, b in zip(h_bl, h_rev)) / len(rev_items),
                "kappa": cohen_kappa(h_rev, j_rev, labels),
                "moved_toward_judge": sum((a != b) and (b == c) for a, b, c in zip(h_bl, h_rev, j_rev)) / len(rev_items),
            }

    raters = sorted({r.get("rater") for r in human_rows if r.get("pass", "blind") == "blind"})
    if len(raters) >= 2:
        items = sorted({str(r["item_id"]) for r in human_rows})
        matrix = []
        for rater in raters:
            by = _by_item(human_rows, rater, "blind")
            matrix.append([by[i]["label"] if i in by else None for i in items])
        report["human_human"] = {"raters": raters, "alpha_nominal": krippendorff_alpha(matrix, "nominal")}
    return report


def adjudication_template(human_rows: Sequence[dict], judge_rows: Sequence[dict], human_rater: str | None = None) -> list[dict]:
    """One row per disagreement, with an empty verdict to fill in: judge_wrong, human_wrong or
    rubric_ambiguous. The headline kappa is computed before adjudication, never after."""
    human = _by_item(human_rows, human_rater, "blind")
    judge = _by_item(judge_rows, None, "blind")
    rows = []
    for item in sorted(set(human) & set(judge)):
        if human[item]["label"] != judge[item]["label"]:
            rows.append({
                "item_id": item,
                "human": human[item]["label"],
                "judge": judge[item]["label"],
                "verdict": "",
                "note": "",
            })
    return rows


def write_jsonl(rows: Iterable[dict], path: Path | str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
