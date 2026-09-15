"""Mine a set from a teacher, check it, pan it.

A ``MineSpec`` says what to generate: the items, a prompt template, the languages, how to parse
the teacher's text, and the checks a sample must pass. ``mine`` runs it against a ``Teacher``, a
callable that returns text and a usage record, and writes three things next to each other:

    paydirt.jsonl   samples that passed every check
    tailings.jsonl  samples that failed, with the reason
    mine.json       the spec hash, the teacher's name, counts, cost and timing

It resumes: items already in the paydirt or tailings are skipped, so a run can be interrupted.
The teacher adapters for hosted models live with the project or in a later release; the
``ScriptedTeacher`` here exists for tests and dry runs.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

Usage = dict  # {"input_tokens": int, "output_tokens": int, "cost_usd": float}
Check = Callable[[dict], tuple[bool, str]]  # sample -> (passed, reason)


class Teacher(Protocol):
    name: str

    def __call__(self, prompt: str) -> tuple[str, Usage]: ...


@dataclass
class ScriptedTeacher:
    """Returns canned text by prompt, or a default. For tests and dry runs."""

    responses: Mapping[str, str] = field(default_factory=dict)
    default: str = ""
    name: str = "scripted"
    calls: int = 0

    def __call__(self, prompt: str) -> tuple[str, Usage]:
        self.calls += 1
        text = self.responses.get(prompt, self.default)
        return text, {"input_tokens": len(prompt.split()), "output_tokens": len(text.split()), "cost_usd": 0.0}


@dataclass
class MineSpec:
    name: str
    items: Sequence[Mapping[str, Any]]           # each needs an "id"
    prompt: str                                  # str.format template over item fields + language
    parse: Callable[[str], dict]                 # teacher text -> sample fields
    checks: Sequence[tuple[str, Check]] = ()     # (name, check) run in order; first failure is the reason
    languages: Sequence[str] = ("en",)
    version: str = "1"

    def spec_hash(self) -> str:
        h = hashlib.sha256()
        h.update(self.name.encode())
        h.update(self.version.encode())
        h.update(self.prompt.encode())
        h.update(",".join(self.languages).encode())
        h.update(",".join(n for n, _ in self.checks).encode())
        return h.hexdigest()[:16]


def _read_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as fh:
        return {json.loads(line)["sample_id"] for line in fh if line.strip()}


def run_checks(sample: dict, checks: Sequence[tuple[str, Check]]) -> tuple[bool, str]:
    for name, check in checks:
        ok, reason = check(sample)
        if not ok:
            return False, f"{name}: {reason}"
    return True, ""


def mine(spec: MineSpec, teacher: Teacher, out_dir: Path | str, limit: int | None = None) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pay, tail, meta = out / "paydirt.jsonl", out / "tailings.jsonl", out / "mine.json"
    done = _read_ids(pay) | _read_ids(tail)
    counts = {"paydirt": 0, "tailings": 0, "skipped": 0}
    cost = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    t0 = time.time()
    n_run = 0
    with pay.open("a", encoding="utf-8") as fp, tail.open("a", encoding="utf-8") as ft:
        for item in spec.items:
            for lang in spec.languages:
                sample_id = f"{item['id']}:{lang}"
                if sample_id in done:
                    counts["skipped"] += 1
                    continue
                if limit is not None and n_run >= limit:
                    break
                prompt = spec.prompt.format(**item, language=lang)
                text, usage = teacher(prompt)
                for k in cost:
                    cost[k] += usage.get(k, 0)
                try:
                    fields = spec.parse(text)
                    parse_error = ""
                except Exception as exc:  # noqa: BLE001 - a parse failure is a tailing, not a crash
                    fields, parse_error = {}, f"parse: {exc}"
                sample = {
                    "sample_id": sample_id,
                    "item_id": item["id"],
                    "language": lang,
                    "spec_hash": spec.spec_hash(),
                    "teacher": teacher.name,
                    "raw": text,
                    **fields,
                }
                if parse_error:
                    ok, reason = False, parse_error
                else:
                    ok, reason = run_checks(sample, spec.checks)
                if ok:
                    fp.write(json.dumps(sample, ensure_ascii=False, sort_keys=True) + "\n")
                    counts["paydirt"] += 1
                else:
                    ft.write(json.dumps({**sample, "reason": reason}, ensure_ascii=False, sort_keys=True) + "\n")
                    counts["tailings"] += 1
                n_run += 1
    record = {
        "spec": spec.name,
        "spec_version": spec.version,
        "spec_hash": spec.spec_hash(),
        "teacher": teacher.name,
        "languages": list(spec.languages),
        "checks": [n for n, _ in spec.checks],
        "counts": counts,
        "usage": cost,
        "seconds": round(time.time() - t0, 1),
    }
    previous = json.loads(meta.read_text()) if meta.exists() else {}
    if previous.get("spec_hash") not in (None, record["spec_hash"]):
        record["warning"] = "spec changed since the previous run; earlier samples came from a different spec"
    meta.write_text(json.dumps(record, indent=2))
    return record


def pan(source: Path | str, out_dir: Path | str, checks: Sequence[tuple[str, Check]]) -> dict:
    """Re-filter an existing set under new checks. Reads any JSONL of samples."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    counts = {"paydirt": 0, "tailings": 0}
    with Path(source).open(encoding="utf-8") as fh, (out / "paydirt.jsonl").open("w", encoding="utf-8") as fp, (
        out / "tailings.jsonl"
    ).open("w", encoding="utf-8") as ft:
        for line in fh:
            if not line.strip():
                continue
            sample = json.loads(line)
            sample.pop("reason", None)
            ok, reason = run_checks(sample, checks)
            if ok:
                fp.write(json.dumps(sample, ensure_ascii=False, sort_keys=True) + "\n")
                counts["paydirt"] += 1
            else:
                ft.write(json.dumps({**sample, "reason": reason}, ensure_ascii=False, sort_keys=True) + "\n")
                counts["tailings"] += 1
    (out / "pan.json").write_text(json.dumps({"source": str(source), "checks": [n for n, _ in checks], "counts": counts}, indent=2))
    return counts
