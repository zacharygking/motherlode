# Motherlode

[![tests](https://github.com/zacharygking/motherlode/actions/workflows/tests.yml/badge.svg)](https://github.com/zacharygking/motherlode/actions/workflows/tests.yml)

Prospect it, mine it, pan it, handpick the rest, keep the paydirt.

A synthetic data engine for ML projects, in mining order. `prospect` validates the judge and the
checkers on a hand-labeled sample, so you know the quality gate works before generating at scale.
`mine` generates a set from a teacher or a source. `pan` runs every sample through the checkers
and keeps what passed. `handpick` builds the tool a person uses to label samples by hand, blind
and assisted, which is where the labels that prospect needs come from. The output is the
**paydirt**; the rejects are the **tailings**, kept with their reasons.

Everything here is domain-agnostic. The checkers, prompts, rubrics and data live with the project
that mines them. A shared library that knows what a tyre compound is has failed at its one job.

## What is in it

| Module | What it does |
|---|---|
| `motherlode.synth` | `MineSpec` and `mine`: items times languages through a prompt template to a teacher, parsed, checked, written as `paydirt.jsonl`, `tailings.jsonl` and `mine.json` with the spec hash, counts, usage and cost. Resumable. `pan` re-filters any set under new checks. |
| `motherlode.claims` | `Claim`, `Verdict`, the `Checker` protocol, `check_claims` dispatch by claim kind, and `faithfulness_report`: share verified with a bootstrap interval over items, per group if asked. Unknown kinds stay unresolved and are reported, never hidden. |
| `motherlode.judge` | `validate_judge`: kappa between a human's blind pass and a judge, with the interval, prevalence for both, a rubric-hash consistency check, the post-reveal shift if a revealed pass exists, and Krippendorff's alpha across humans as the ceiling. `adjudication_template` writes the disagreements to fill in. |
| `motherlode.grading` | `build_grading_tool`: one local HTML file, no server. Rubric frozen and hashed into every label, order shuffled with a recorded seed, context fields shown before labeling, hidden fields such as a judge's verdict encoded and rendered only after the blind label is committed, a revised label stored separately, JSONL export the judge module reads directly. |
| `motherlode.stats` | Cohen's kappa, Krippendorff's alpha with missing values, a paired bootstrap, prevalence, and an agreement report whose raw-agreement field is named so nobody reports it. |

## Quick start

```
uv venv --python 3.12 .venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest -q

# prospect: validate a judge against a human's labels; write the disagreements to adjudicate
motherlode prospect --human labels-zachary.jsonl --judge labels-judge.jsonl --adjudication adjudicate.jsonl

# handpick: build the tool for labeling samples by hand
motherlode handpick --items reasons.jsonl --rubric RUBRIC.md --out grade.html \
  --labels sound unsupported "wrong facts" vacuous --context fact_sheet brief --hidden judge_label judge_rationale --rater zachary

# mine a set: a spec and a teacher are Python objects in your project
motherlode mine specs.commentary:spec --teacher specs.commentary:teacher --out runs/commentary
```

`check` is accepted as an alias of `prospect`, and `grade` of `handpick`.

## Label files

One JSONL row per label. The judge's file has the same shape with its own `rater`.

```
{"item_id": "r17", "rater": "zachary", "label": "sound", "rubric_hash": "3f9a1c0b2e77", "pass": "blind", "ts": "..."}
{"item_id": "r17", "rater": "zachary", "label": "unsupported", "rubric_hash": "3f9a1c0b2e77", "pass": "revealed", "ts": "..."}
```

The headline number is always the blind pass. If a revealed pass exists, the share of labels that
moved, and how many moved toward the judge, is reported beside it, because anchoring is a finding.

## Number discipline

Agreement is chance-corrected, with a bootstrap interval and the prevalence beside it. Raw
agreement is computed and labelled `raw_agreement_do_not_report`. Faithfulness is the share of
claims verified by code, bootstrapped over items, with refuted and unresolved shares beside it.
Counts are counts.

## Consumers

| Project | Uses |
|---|---|
| [pit-wall](https://github.com/zacharygking/pit-wall) | the grading tool and judge validation for the agent's reasons; `mine` for the strategist's training plans |

Planned: an F1 commentator trained on mined lines, NFL recaps with claim checks, a localization
linter graded against human fixes. Each keeps its paydirt in its own repo.

## Conventions

Semantic versions on git tags with a changelog. Consumers pin a tag and install from GitHub:

```
uv pip install "motherlode @ git+https://github.com/zacharygking/motherlode@v0.1.0"
```

Code moves into this repo when a second project calls it, not before. Teacher adapters for hosted
models arrive with the first project that mines against one; `ScriptedTeacher` covers tests and
dry runs until then.
