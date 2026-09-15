"""A rubric is text plus a spec: the dimensions it scores, each with a scale, whether the scale is
ordinal, and whether "NA" is a legal label. The text is what graders read; the spec is what
handpick renders and prospect validates against, so the two cannot disagree.

    {"dimensions": [
      {"id": "D1", "name": "Task success", "scale": ["0", "1"], "ordinal": true, "na_allowed": false},
      {"id": "D4", "name": "...", "scale": ["0", "1", "2"], "ordinal": true, "na_allowed": true}]}

A single-label rubric is the one-dimension case, ``single_label_spec(["sound", "unsupported"])``.
The rubric hash covers the text and the spec together, so a scale change with unchanged text
still changes the hash.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

NA = "NA"


@dataclass(frozen=True)
class Dimension:
    id: str
    scale: tuple[str, ...]
    name: str = ""
    ordinal: bool = False
    na_allowed: bool = False

    def labels(self) -> list[str]:
        return list(self.scale) + ([NA] if self.na_allowed else [])

    def check(self, label: str) -> str:
        """Normalize and validate one label for this dimension."""
        s = str(label).strip()
        if s.upper() == NA:
            if not self.na_allowed:
                raise ValueError(f"{self.id}: NA is not allowed")
            return NA
        if s not in self.scale:
            raise ValueError(f"{self.id}: {s!r} is not on the scale {list(self.scale)}")
        return s


@dataclass(frozen=True)
class RubricSpec:
    dimensions: tuple[Dimension, ...]
    text: str = ""

    @property
    def ids(self) -> list[str]:
        return [d.id for d in self.dimensions]

    def dimension(self, id_: str) -> Dimension:
        for d in self.dimensions:
            if d.id == id_:
                return d
        raise KeyError(id_)

    def to_dict(self) -> dict:
        return {"dimensions": [{"id": d.id, "name": d.name, "scale": list(d.scale), "ordinal": d.ordinal,
                                "na_allowed": d.na_allowed} for d in self.dimensions]}

    @property
    def hash(self) -> str:
        return rubric_hash(self.text, self)


def spec_from_dict(d: dict, text: str = "") -> RubricSpec:
    dims = []
    for x in d["dimensions"]:
        dims.append(Dimension(id=str(x["id"]), scale=tuple(str(s) for s in x["scale"]), name=x.get("name", ""),
                              ordinal=bool(x.get("ordinal", False)), na_allowed=bool(x.get("na_allowed", False))))
    if len({x.id for x in dims}) != len(dims):
        raise ValueError("duplicate dimension ids")
    return RubricSpec(tuple(dims), text)


def single_label_spec(labels: Sequence[str], text: str = "", ordinal: bool = False) -> RubricSpec:
    return RubricSpec((Dimension(id="label", scale=tuple(str(x) for x in labels), name="label", ordinal=ordinal),), text)


def load_rubric(text_path: Path | str, spec_path: Path | str | None = None) -> RubricSpec:
    text = Path(text_path).read_text(encoding="utf-8")
    if spec_path is None:
        cand = Path(text_path).with_suffix(".json")
        spec_path = cand if cand.exists() else None
    if spec_path is None:
        raise ValueError("no rubric spec: pass spec_path or put <rubric>.json beside the text")
    return spec_from_dict(json.loads(Path(spec_path).read_text(encoding="utf-8")), text)


def rubric_hash(text: str, spec: RubricSpec | None = None) -> str:
    """12 hex chars of sha256 over the text, and over the spec when there is one.

    A single-label spec (the implicit one dimension named ``label``) hashes as the text alone, so
    v0.1 label files keep their hashes."""
    h = hashlib.sha256(text.encode("utf-8"))
    if spec is not None and spec.dimensions and spec.ids != ["label"]:
        h.update(b"\x00")
        h.update(json.dumps(spec.to_dict(), sort_keys=True).encode("utf-8"))
    return h.hexdigest()[:12]


def parse_scores(text: str, spec: RubricSpec) -> dict[str, dict]:
    """Find the JSON object in a grader's reply and validate every dimension against the spec.

    Accepts ``{"D1": {"score": 1, "rationale": "..."}, ...}`` or ``{"D1": 1, ...}``. Returns
    ``{dimension: {"label": str, "rationale": str}}`` with labels normalized to strings.
    """
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in the grader's reply")
    data = json.loads(text[start:end + 1])
    out = {}
    for d in spec.dimensions:
        if d.id not in data:
            raise ValueError(f"missing {d.id}")
        entry = data[d.id]
        raw = entry.get("score", entry.get("label")) if isinstance(entry, dict) else entry
        out[d.id] = {"label": d.check(raw), "rationale": (entry.get("rationale", "") if isinstance(entry, dict) else "")}
    return out


def score_rows(item_id: str, rater: str, scores: dict[str, dict], rubric_hash_: str, pass_: str = "blind",
               extra: dict | None = None) -> list[dict]:
    """One label row per dimension, the shape every motherlode command reads."""
    rows = []
    for dim, s in scores.items():
        row = {"item_id": str(item_id), "rater": rater, "dimension": dim, "label": s["label"],
               "rubric_hash": rubric_hash_, "pass": pass_}
        if s.get("rationale"):
            row["rationale"] = s["rationale"]
        if extra:
            row.update(extra)
        rows.append(row)
    return rows
