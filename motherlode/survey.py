"""Mask and survey: the machine judge over an items dataset.

``mask`` writes every item's text under an opaque key with the rubric and grading instructions,
so a grader, a person or a model, cannot tell where an item came from. ``survey`` records one
grader's scores for a key, or asks an API model for them, and appends dimensioned label rows to
``judgments.jsonl`` in the masked directory. Nothing here knows what the items are about.

    motherlode mask   --dataset datasets/trajectories --out work/masked
    motherlode survey --masked work/masked --key 3f2a9c1e --rater claude-code:opus --scores '<json>'
    motherlode survey --masked work/masked --model claude-opus-5          # every unscored key
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from .dataset import Dataset, append_jsonl, read_dataset, read_jsonl
from .rubric import RubricSpec, parse_scores, score_rows

INSTRUCTIONS = """You are grading one item against the rubric below. Read the item, then score every
dimension exactly as the rubric defines it. Grade only what is in the item. Use "NA" only on a
dimension whose spec allows it, and only where the rubric says it applies.

Answer with one JSON object and nothing else, one entry per dimension:
{"<dimension id>": {"score": <a value on that dimension's scale, or "NA">, "rationale": "one or two sentences"}, ...}"""


def item_key(dataset_hash: str, item_id: str) -> str:
    """Opaque, deterministic: the same item in the same dataset always gets the same key."""
    return hashlib.sha256(f"{dataset_hash}|{item_id}".encode()).hexdigest()[:8]


def mask(dataset: Dataset, out_dir: Path | str, ids: list[str] | None = None) -> dict:
    spec = dataset.rubric()
    out = Path(out_dir)
    (out / "items").mkdir(parents=True, exist_ok=True)
    (out / "RUBRIC.md").write_text(spec.text, encoding="utf-8")
    (out / "INSTRUCTIONS.md").write_text(INSTRUCTIONS + "\n\nDimensions and scales:\n" + "\n".join(
        f"- {d.id} {d.name}: {list(d.scale)}{' or NA' if d.na_allowed else ''}" for d in spec.dimensions) + "\n",
        encoding="utf-8")
    manifest = {"dataset": dataset.ref(), "rubric_hash": spec.hash, "keys": {}}
    for it in dataset.items():
        if ids and str(it["id"]) not in ids:
            continue
        key = item_key(dataset.hash, str(it["id"]))
        (out / "items" / f"{key}.md").write_text(it["text"], encoding="utf-8")
        manifest["keys"][key] = str(it["id"])
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return manifest


def _workspace(ws: Path | str) -> tuple[Path, dict, Dataset, RubricSpec]:
    w = Path(ws)
    manifest = json.loads((w / "manifest.json").read_text(encoding="utf-8"))
    ds = read_dataset(manifest["dataset"]["path"])
    if ds.hash != manifest["dataset"]["dataset_sha256"]:
        raise ValueError("the items dataset changed since it was masked")
    spec = ds.rubric()
    if spec.hash != manifest["rubric_hash"]:
        raise ValueError("the rubric changed since the dataset was masked")
    return w, manifest, ds, spec


def record(ws: Path | str, key: str, rater: str, scores_text: str) -> list[dict]:
    w, manifest, ds, spec = _workspace(ws)
    if key not in manifest["keys"]:
        raise KeyError(f"unknown key {key}")
    scores = parse_scores(scores_text, spec)
    rows = score_rows(manifest["keys"][key], rater, scores, spec.hash, extra={"key": key})
    append_jsonl(rows, w / "judgments.jsonl")
    return rows


def scored_keys(ws: Path | str) -> set[str]:
    p = Path(ws) / "judgments.jsonl"
    return {r.get("key") for r in read_jsonl(p)} if p.exists() else set()


def score_with_model(ws: Path | str, model: str, keys: list[str] | None = None, max_tokens: int = 4000) -> int:
    """Grade every unscored key (or the given ones) with an API model. Same instructions as a person."""
    import anthropic
    w, manifest, ds, spec = _workspace(ws)
    client = anthropic.Anthropic()
    done = scored_keys(w)
    todo = [k for k in (keys or manifest["keys"]) if k not in done]
    instructions = (w / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    n = 0
    for key in todo:
        text = (w / "items" / f"{key}.md").read_text(encoding="utf-8")
        prompt = f"{instructions}\n\n## Rubric\n{spec.text}\n\n## Item\n{text}"
        resp = client.messages.create(model=model, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}])
        reply = "".join(b.text for b in resp.content if b.type == "text")
        record(w, key, model, reply)
        n += 1
        print(f"scored {key} with {model}", file=sys.stderr)
    return n
