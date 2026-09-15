# Motherlode

[![tests](https://github.com/zacharygking/motherlode/actions/workflows/tests.yml/badge.svg)](https://github.com/zacharygking/motherlode/actions/workflows/tests.yml)

Prospect it, mine it, pan it, assay and handpick the rest, keep the paydirt.

A data library for ML projects, in two halves, both domain-free.

**The gate** makes a judge's numbers reportable. A rubric is text plus a spec of its dimensions.
`assay` is the machine judge over a dataset of items, blind. `handpick` is the tool a person uses
to label a sample by hand, blind and assisted, every dimension on one page. `prospect` is the
validation: chance-corrected agreement between the person and the judge per dimension, with
intervals, weighted for ordinal scales, ground truth as just another rater, and a template for
adjudicating the disagreements. `paydirt` assembles the graded dataset, hashed to the items it
grades.

**The engine** makes data. `mine` generates a set from a teacher, `pan` runs every sample through
the checkers and keeps what passed. The output is the paydirt; the rejects are the tailings,
kept with their reasons. The engine uses the gate before it calls anything paydirt.

Projects talk to motherlode through datasets: a directory with a manifest, per-file hashes and a
whole-dataset hash, written by a producer and read by a consumer. Motherlode never imports a
project, and a project need not import motherlode; it can write a dataset, run the commands, and
read the graded dataset back. A shared library that knows what a tyre compound or a cap sheet is
has failed at its one job.

## The gate, end to end

```
# 1. a project writes an items dataset: items.jsonl (id, text, optional truth per dimension,
#    any context fields), rubric.md, rubric.json, manifest.json
# 2. blind packets for the judge
motherlode assay pool --dataset datasets/trajectories-v6 --out work/assay
# 3. score: a grader's JSON per key (a subagent, a person), or an API model over every key
motherlode assay score --workspace work/assay --key 3f2a9c1e --rater claude-code:opus --scores '{"D1": {"score": 1, "rationale": "..."}, ...}'
motherlode assay score --workspace work/assay --model claude-opus-5
# 4. the hand-grading tool: every dimension on one page, the judge's score hidden until commit
motherlode handpick --dataset datasets/trajectories-v6 --workspace work/assay --context packet --rater zachary --out work/grade.html
# 5. validate, per dimension, with ground truth from the dataset as a third rater
motherlode prospect --dataset datasets/trajectories-v6 --human work/labels-zachary.jsonl --judge work/assay/judgments.jsonl --adjudication work/adjudicate.jsonl
# 6. the graded dataset, hashed to its source
motherlode paydirt --dataset datasets/trajectories-v6 --workspace work/assay --human work/labels-zachary.jsonl --out datasets/trajectories-v6-graded
```

`prospect` prints one line per dimension: n, items excluded as NA, kappa with its interval,
linear weighted kappa for ordinal scales, and agreement with ground truth where it exists. The
headline is always the blind pass; a revised pass after seeing the judge is reported beside it.

## Formats

**Rubric spec** (`rubric.json`): `{"dimensions": [{"id": "D1", "name": "...", "scale": ["0", "1"], "ordinal": true, "na_allowed": false}, ...]}`.
The rubric hash covers the text and the spec. A single-label rubric is the one-dimension case and
`--labels a b c` on the command line is sugar for it.

**Label row**, one per item, rater, dimension and pass:
`{"item_id": "...", "rater": "zachary", "dimension": "D4", "label": "2", "rubric_hash": "...", "pass": "blind"}`.
A row without `dimension` is the single dimension `label`. A rater named `ground_truth` is a
rater like any other. NA is never a label in the statistics: the item is dropped from that
dimension and the count reported.

**Dataset** (`manifest.json` beside the files): name, schema (`items-v1` or `graded-v1`),
version, producer, sources, per-file sha256, whole-dataset sha256. `read_dataset` verifies on
read.

## What is in it

| Module | What it does |
|---|---|
| `motherlode.dataset` | Write and read dataset directories with manifests and hashes; JSONL helpers; ground truth as label rows. |
| `motherlode.rubric` | `RubricSpec`, `rubric_hash`, `parse_scores` with per-dimension NA rules, `score_rows`. |
| `motherlode.assay` | `pool` and `score`: the machine judge over an items dataset, blind, deterministic keys, workspace refuses a changed dataset or rubric. |
| `motherlode.grading` | `build_grading_tool`: one HTML file, no server, every dimension per item, hidden fields revealed after commit, revised labels stored separately, per-tool browser storage, JSONL export. |
| `motherlode.judge` | `validate` per dimension, `summary_table`, `adjudication_template`; `validate_judge` keeps the v0.1 single-label shape. |
| `motherlode.stats` | Cohen's kappa, weighted kappa, Krippendorff's alpha with missing values, a paired bootstrap, prevalence, and an agreement report whose raw-agreement field is named so nobody reports it. |
| `motherlode.synth` | `MineSpec` and `mine`; `pan` re-filters any set under new checks. Resumable, with the spec hash, counts, usage and cost in `mine.json`. |
| `motherlode.claims` | `Claim`, `Verdict`, the `Checker` protocol, `check_claims`, `faithfulness_report`. |

## Quick start

```
uv venv --python 3.12 .venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

The `api` extra adds the Anthropic client for `assay score --model`.

## Consumers

| Project | Uses |
|---|---|
| [nba-trade-desk](https://github.com/zacharygking/nba-trade-desk) | The gate: publishes a trajectories dataset, reads the graded one back. |
| pit-wall | Planned: the engine for commentary synthesis, the gate before publishing. |

## Conventions

Semantic versions on git tags, with `CHANGELOG.md`. Consumers pin a tag. Paydirt and labels live
with the project that produced or asked for them, never here. Code moves into this repo when a
second project calls it, not before.
