# Changelog

## v0.2.0

The gate becomes a first-class half of the library, and projects talk to motherlode through
datasets rather than by driving its commands.

- `dataset`: directories with a manifest, per-file and whole-dataset hashes, verification on
  read. Schemas `items-v1` (id, text, optional truth per dimension, any context fields) and
  `graded-v1` (judgments, human labels, truth, validation report, hashed to the items they grade).
- `rubric`: a rubric is text plus a spec of dimensions, each with a scale, ordinality and whether
  NA is allowed. The hash covers both. A single-label rubric is the one-dimension case and keeps
  its v0.1 hash.
- `assay`: the machine judge. `pool` blinds an items dataset under opaque, deterministic keys;
  `score` records a grader's JSON or asks an API model, and appends dimensioned label rows.
- `handpick`: one tool renders every dimension on the item's page; the judge's score per dimension
  hides until the blind labels are committed. Browser storage is keyed per tool, so two tools
  over the same items cannot share state. The glossary heading is a parameter.
- `prospect`: per dimension. Weighted kappa (linear and quadratic) for ordinal scales beside the
  unweighted one, NA excluded pairwise and counted, ground truth as a rater, the human-human
  ceiling at the interval level for ordinal dimensions, and a one-table summary. The adjudication
  template carries the dimension, the judge's rationale, and whether the disagreement is about
  the label or about applicability.
- `paydirt`: assembles the graded dataset from an items dataset, an assay workspace and label
  files, with the validation report and a source reference to the items dataset.
- Label rows gain an optional `dimension` field; files without it are read as single-label.
- One version source (`motherlode.__version__`), an `api` extra for the Anthropic client.

## v0.1.0

First release: `mine`, `pan`, `prospect`, `handpick`, claims and stats.
