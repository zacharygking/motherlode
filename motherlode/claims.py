"""Claims, checkers and the faithfulness report.

A model output is broken into claims. Each claim has a kind, and a checker that knows that kind
verifies it against the project's ground truth. Claims no checker can resolve stay ``unresolved``
and are reported, never hidden. The checkers themselves are domain code and live with the project.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol, runtime_checkable

from .stats import bootstrap

STATUSES = ("verified", "refuted", "unresolved")


@dataclass(frozen=True)
class Claim:
    id: str
    kind: str
    text: str
    data: Mapping[str, Any] = field(default_factory=dict)
    language: str | None = None
    item_id: str | None = None


@dataclass(frozen=True)
class Verdict:
    claim_id: str
    status: str
    checker: str
    note: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}, got {self.status!r}")


@runtime_checkable
class Checker(Protocol):
    """A project supplies these. ``kinds`` names the claim kinds it can verify."""

    name: str
    kinds: frozenset[str]

    def verify(self, claim: Claim, context: Any) -> Verdict: ...


def check_claims(claims: Iterable[Claim], checkers: Sequence[Checker], context: Any = None) -> list[Verdict]:
    """Dispatch each claim to the first checker that knows its kind. Unknown kinds are unresolved."""
    by_kind: dict[str, Checker] = {}
    for c in checkers:
        for k in c.kinds:
            by_kind.setdefault(k, c)
    out = []
    for claim in claims:
        checker = by_kind.get(claim.kind)
        if checker is None:
            out.append(Verdict(claim.id, "unresolved", "none", f"no checker for kind {claim.kind!r}"))
            continue
        v = checker.verify(claim, context)
        if v.claim_id != claim.id:
            raise ValueError(f"checker {checker.name} returned a verdict for {v.claim_id}, expected {claim.id}")
        out.append(v)
    return out


def faithfulness_report(
    verdicts_by_item: Mapping[str, Sequence[Verdict]],
    n_boot: int = 2000,
    seed: int = 0,
    by: Mapping[str, str] | None = None,
) -> dict:
    """Share of claims verified, with a bootstrap interval over items, plus counts per status.

    ``by`` maps item ids to a group (a language, a model) for a per-group breakdown.
    """
    items = list(verdicts_by_item)
    per_item = [_rates(verdicts_by_item[i]) for i in items]

    def share(rows, key):
        num = sum(r[key] for r in rows)
        den = sum(r["n"] for r in rows)
        return num / den if den else float("nan")

    def report(rows: list[dict]) -> dict:
        est, lo, hi = bootstrap(lambda rs: share(rs, "verified"), rows, n=n_boot, seed=seed)
        return {
            "items": len(rows),
            "claims": int(sum(r["n"] for r in rows)),
            "verified": est,
            "verified_ci95": [lo, hi],
            "refuted": share(rows, "refuted"),
            "unresolved": share(rows, "unresolved"),
            "claims_per_item": (sum(r["n"] for r in rows) / len(rows)) if rows else float("nan"),
        }

    out = {"overall": report(per_item)}
    if by:
        groups: dict[str, list[dict]] = {}
        for item, rows in zip(items, per_item):
            groups.setdefault(by.get(item, "unknown"), []).append(rows)
        out["by_group"] = {g: report(rs) for g, rs in sorted(groups.items())}
    return out


def verdict_rows(verdicts: Iterable[Verdict]) -> list[dict]:
    return [asdict(v) for v in verdicts]


def _rates(verdicts: Sequence[Verdict]) -> dict:
    n = len(verdicts)
    return {
        "n": n,
        "verified": sum(v.status == "verified" for v in verdicts),
        "refuted": sum(v.status == "refuted" for v in verdicts),
        "unresolved": sum(v.status == "unresolved" for v in verdicts),
    }
