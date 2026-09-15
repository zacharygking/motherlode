"""Command line, in mining order.

  motherlode mine  spec_module:spec --teacher spec_module:teacher --out runs/x       generate a set
  motherlode pan   --source runs/x/paydirt.jsonl --checks spec_module:checks --out runs/y
  motherlode assay pool  --dataset <items dataset> --out <workspace>                  blind packets for a judge
  motherlode assay score --workspace <ws> --key K --rater NAME --scores '<json>'      record a grader's scores
  motherlode assay score --workspace <ws> --model claude-opus-5                       grade every unscored key
  motherlode handpick --dataset <items dataset> --out grade.html --rater NAME          the blind hand-grading tool
                      [--workspace <ws>]  hides that workspace's judgments per dimension until commit
  motherlode prospect --dataset <items dataset> --human labels.jsonl --judge <ws>/judgments.jsonl
                      [--adjudication out.jsonl]                                       validate the judge, per dimension
  motherlode paydirt --dataset <items dataset> --workspace <ws> --human labels.jsonl ... --out <graded dataset>
                                                                                      the graded dataset, hashed to its source

Single-label use still works: handpick --items items.jsonl --rubric RUBRIC.md --labels a b c, and
prospect --human --judge on files without a dimension field.
``grade`` and ``check`` remain as aliases of ``handpick`` and ``prospect``.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

from . import assay
from .dataset import read_dataset, read_jsonl, truth_rows, write_dataset, write_jsonl
from .grading import build_grading_tool
from .judge import adjudication_template, read_labels, summary_table, validate, validate_judge
from .rubric import load_rubric
from .synth import mine, pan


def _load(ref: str):
    mod, _, name = ref.partition(":")
    if not name:
        raise SystemExit(f"expected module:name, got {ref!r}")
    sys.path.insert(0, str(Path.cwd()))
    return getattr(importlib.import_module(mod), name)


def _judgment_hidden(ws: Path, dataset_hash: str) -> dict[str, dict]:
    """item id -> {judge_<dim>: 'label: rationale'} from a workspace's judgments."""
    p = ws / "judgments.jsonl"
    out: dict[str, dict] = {}
    if not p.exists():
        return out
    for r in read_jsonl(p):
        out.setdefault(str(r["item_id"]), {})[f"judge_{r.get('dimension', 'label')}"] = \
            f"{r['label']}: {r.get('rationale', '')}".strip(": ")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="motherlode", description="Prospect it, mine it, pan it, assay and handpick the rest, keep the paydirt.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("mine", help="generate a set from a spec and a teacher")
    s.add_argument("spec"); s.add_argument("--teacher", required=True); s.add_argument("--out", required=True); s.add_argument("--limit", type=int)

    s = sub.add_parser("pan", help="re-filter an existing set under checks")
    s.add_argument("--source", required=True); s.add_argument("--checks", required=True); s.add_argument("--out", required=True)

    a = sub.add_parser("assay", help="the machine judge over an items dataset")
    asub = a.add_subparsers(dest="assay_cmd", required=True)
    ap = asub.add_parser("pool"); ap.add_argument("--dataset", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--ids", nargs="*", default=None)
    asc = asub.add_parser("score"); asc.add_argument("--workspace", required=True)
    asc.add_argument("--key"); asc.add_argument("--rater"); asc.add_argument("--scores")
    asc.add_argument("--model"); asc.add_argument("--keys", nargs="*", default=None)

    for name in ("handpick", "grade"):
        s = sub.add_parser(name, help="build the local tool for labeling items by hand, blind and assisted")
        s.add_argument("--dataset"); s.add_argument("--items"); s.add_argument("--rubric"); s.add_argument("--spec")
        s.add_argument("--out", required=True); s.add_argument("--labels", nargs="+")
        s.add_argument("--context", nargs="*", default=None); s.add_argument("--hidden", nargs="*", default=[])
        s.add_argument("--workspace", help="hide this workspace's judgments per dimension until commit")
        s.add_argument("--ids", nargs="*", default=None)
        s.add_argument("--rater", default="rater"); s.add_argument("--title", default="Handpick"); s.add_argument("--seed", type=int, default=0)

    for name in ("prospect", "check"):
        s = sub.add_parser(name, help="validate the judge on a hand-labeled sample, per dimension")
        s.add_argument("--human", required=True, nargs="+"); s.add_argument("--judge", required=True)
        s.add_argument("--dataset", help="items dataset: supplies the rubric spec and ground truth")
        s.add_argument("--rubric"); s.add_argument("--spec")
        s.add_argument("--rater"); s.add_argument("--judge-rater")
        s.add_argument("--adjudication", help="write a disagreement file to fill in")
        s.add_argument("--json", action="store_true", help="print the full report as JSON")

    s = sub.add_parser("paydirt", help="assemble the graded dataset from a workspace and label files")
    s.add_argument("--dataset", required=True); s.add_argument("--workspace", required=True)
    s.add_argument("--human", nargs="*", default=[]); s.add_argument("--out", required=True)
    s.add_argument("--name"); s.add_argument("--producer", default="motherlode")

    a = p.parse_args(argv)

    if a.cmd == "mine":
        print(json.dumps(mine(_load(a.spec), _load(a.teacher), a.out, limit=a.limit), indent=2))
    elif a.cmd == "pan":
        print(json.dumps(pan(a.source, a.out, _load(a.checks)), indent=2))
    elif a.cmd == "assay":
        if a.assay_cmd == "pool":
            m = assay.pool(read_dataset(a.dataset), a.out, a.ids)
            print(f"pooled {len(m['keys'])} items into {a.out} (rubric {m['rubric_hash']})")
        elif a.model:
            n = assay.score_with_model(a.workspace, a.model, a.keys)
            print(f"scored {n} items with {a.model}")
        else:
            if not (a.key and a.rater and a.scores):
                raise SystemExit("assay score needs --key, --rater and --scores, or --model")
            rows = assay.record(a.workspace, a.key, a.rater, a.scores)
            print(f"recorded {a.key} by {a.rater}: " + " ".join(f"{r['dimension']}={r['label']}" for r in rows))
    elif a.cmd in ("handpick", "grade"):
        if a.dataset:
            ds = read_dataset(a.dataset)
            spec = ds.rubric()
            items = [it for it in ds.items() if not a.ids or str(it["id"]) in a.ids]
            context = a.context if a.context is not None else []
            hidden_prefix = None
            if a.workspace:
                hid = _judgment_hidden(Path(a.workspace), ds.hash)
                for it in items:
                    it.update(hid.get(str(it["id"]), {}))
                hidden_prefix = "judge_"
            out = build_grading_tool(items, spec, a.out, context_keys=context, hidden_keys=a.hidden,
                                     hidden_prefix=hidden_prefix, rater=a.rater, title=a.title, seed=a.seed)
        else:
            if not (a.items and a.rubric):
                raise SystemExit("handpick needs --dataset, or --items and --rubric")
            items = [it for it in read_labels(a.items) if not a.ids or str(it["id"]) in a.ids]
            if a.spec or Path(a.rubric).with_suffix(".json").exists():
                spec = load_rubric(a.rubric, a.spec)
                out = build_grading_tool(items, spec, a.out, context_keys=a.context or [], hidden_keys=a.hidden,
                                         rater=a.rater, title=a.title, seed=a.seed)
            else:
                if not a.labels:
                    raise SystemExit("handpick with a text-only rubric needs --labels")
                out = build_grading_tool(items, Path(a.rubric).read_text(encoding="utf-8"), a.out, labels=a.labels,
                                         context_keys=a.context or [], hidden_keys=a.hidden, rater=a.rater,
                                         title=a.title, seed=a.seed)
        print(f"grading tool written to {out}")
    elif a.cmd in ("prospect", "check"):
        human = [r for f in a.human for r in read_labels(f)]
        judge = read_labels(a.judge)
        spec = None
        truth: list[dict] = []
        if a.dataset:
            ds = read_dataset(a.dataset)
            spec = ds.rubric()
            truth = truth_rows(ds.items(), spec.hash)
        elif a.rubric:
            spec = load_rubric(a.rubric, a.spec)
        if spec is None and any("dimension" in r for r in (*human, *judge)):
            raise SystemExit("dimensioned label files need --dataset or --rubric/--spec")
        if spec is None:
            rep = validate_judge(human, judge, human_rater=a.rater)
            print(json.dumps(rep, indent=2))
        else:
            rep = validate(human, judge, spec, human_rater=a.rater, judge_rater=a.judge_rater, truth_rows=truth)
            print(json.dumps(rep, indent=2) if a.json else summary_table(rep))
            if not rep["rubric_consistent"]:
                print(f"WARNING: rubric hashes differ: {rep['rubric_hashes_seen']} vs spec {rep['rubric_hash']}", file=sys.stderr)
        if a.adjudication:
            rows = adjudication_template(human, judge, human_rater=a.rater, judge_rater=a.judge_rater)
            write_jsonl(rows, a.adjudication)
            print(f"{len(rows)} disagreements written to {a.adjudication}", file=sys.stderr)
    elif a.cmd == "paydirt":
        ds = read_dataset(a.dataset)
        ws = Path(a.workspace)
        spec = ds.rubric()
        judge = read_jsonl(ws / "judgments.jsonl") if (ws / "judgments.jsonl").exists() else []
        human = [r for f in a.human for r in read_labels(f)]
        truth = truth_rows(ds.items(), spec.hash)
        files: dict = {"judgments.jsonl": "".join(json.dumps(r, sort_keys=True) + "\n" for r in judge),
                       "truth.jsonl": "".join(json.dumps(r, sort_keys=True) + "\n" for r in truth),
                       "rubric.md": spec.text, "rubric.json": json.dumps(spec.to_dict(), indent=1)}
        for f in a.human:
            files[f"labels/{Path(f).name}"] = Path(f)
        report = validate(human, judge, spec, truth_rows=truth) if human and judge else None
        if report:
            files["validation.json"] = json.dumps(report, indent=1)
        out = write_dataset(a.out, a.name or f"{ds.name}-graded", "graded-v1", files=files,
                            sources=[ds.ref()], producer=a.producer,
                            meta={"rubric_hash": spec.hash, "judges": sorted({r['rater'] for r in judge}),
                                  "humans": sorted({r['rater'] for r in human})})
        print(f"graded dataset {out.name} ({out.hash}) written to {out.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
