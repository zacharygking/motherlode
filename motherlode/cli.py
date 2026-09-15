"""Command line.

  motherlode mine  spec_module:spec --teacher spec_module:teacher --out runs/x    generate a set
  motherlode prospect --human labels.jsonl --judge judge.jsonl [--rater NAME]     validate the judge on a labeled sample
  motherlode pan   --source runs/x/paydirt.jsonl --checks spec_module:checks --out runs/y
  motherlode grade --items items.jsonl --rubric RUBRIC.md --out grade.html --labels a b c ...

``check`` is accepted as an alias of ``prospect``.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

from .grading import build_grading_tool
from .judge import adjudication_template, read_labels, validate_judge, write_jsonl
from .synth import mine, pan


def _load(ref: str):
    mod, _, name = ref.partition(":")
    if not name:
        raise SystemExit(f"expected module:name, got {ref!r}")
    sys.path.insert(0, str(Path.cwd()))
    return getattr(importlib.import_module(mod), name)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="motherlode", description="Prospect it, mine it, pan it, keep the paydirt.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("mine", help="generate a set from a spec and a teacher")
    s.add_argument("spec"); s.add_argument("--teacher", required=True); s.add_argument("--out", required=True); s.add_argument("--limit", type=int)

    for name in ("prospect", "check"):
        s = sub.add_parser(name, help="validate the judge and checkers on a hand-labeled sample before mining at scale")
        s.add_argument("--human", required=True); s.add_argument("--judge", required=True); s.add_argument("--rater")
        s.add_argument("--adjudication", help="write a disagreement file to fill in")

    s = sub.add_parser("pan", help="re-filter an existing set under checks")
    s.add_argument("--source", required=True); s.add_argument("--checks", required=True); s.add_argument("--out", required=True)

    s = sub.add_parser("grade", help="build a local grading tool")
    s.add_argument("--items", required=True); s.add_argument("--rubric", required=True); s.add_argument("--out", required=True)
    s.add_argument("--labels", nargs="+", required=True); s.add_argument("--context", nargs="*", default=[])
    s.add_argument("--hidden", nargs="*", default=[]); s.add_argument("--rater", default="rater"); s.add_argument("--title", default="Grading")
    s.add_argument("--seed", type=int, default=0)

    a = p.parse_args(argv)
    if a.cmd == "mine":
        record = mine(_load(a.spec), _load(a.teacher), a.out, limit=a.limit)
        print(json.dumps(record, indent=2))
    elif a.cmd in ("prospect", "check"):
        human, judge = read_labels(a.human), read_labels(a.judge)
        print(json.dumps(validate_judge(human, judge, human_rater=a.rater), indent=2))
        if a.adjudication:
            rows = adjudication_template(human, judge, human_rater=a.rater)
            write_jsonl(rows, a.adjudication)
            print(f"{len(rows)} disagreements written to {a.adjudication}", file=sys.stderr)
    elif a.cmd == "pan":
        print(json.dumps(pan(a.source, a.out, _load(a.checks)), indent=2))
    elif a.cmd == "grade":
        items = read_labels(a.items)
        out = build_grading_tool(items, Path(a.rubric).read_text(encoding="utf-8"), a.out, labels=a.labels,
                                 context_keys=a.context, hidden_keys=a.hidden, rater=a.rater, title=a.title, seed=a.seed)
        print(f"grading tool written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
