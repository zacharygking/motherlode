"""Motherlode: prospect it, mine it, pan it, assay and handpick the rest, keep the paydirt.

Two halves in one library, both domain-free.

The gate: ``rubric`` (a rubric's text plus the spec of its dimensions), ``assay`` (the machine
judge over an items dataset, blind), ``grading`` (``handpick``, the local tool a person uses to
label items blind, every dimension on one page), ``judge`` (``prospect``: kappa per dimension
with intervals, weighted for ordinal scales, ground truth as a rater, adjudication), and
``stats``. The gate is what makes any judge's numbers reportable.

The engine: ``synth`` (``mine`` a set from a teacher, ``pan`` it through checkers) and ``claims``.
The engine uses the gate before it calls anything paydirt.

Projects talk to motherlode through datasets (``dataset``): a directory with a manifest and
hashes, written by a producer and read by a consumer. Nothing here imports a project.
"""

from .claims import Claim, Checker, Verdict, check_claims, faithfulness_report
from .dataset import Dataset, read_dataset, read_jsonl, truth_rows, verify_dataset, write_dataset, write_jsonl
from .grading import build_grading_tool
from .judge import adjudication_template, compare, read_labels, summary_table, validate, validate_judge
from .rubric import Dimension, RubricSpec, load_rubric, parse_scores, rubric_hash, score_rows, single_label_spec, spec_from_dict
from .stats import agreement_report, bootstrap, cohen_kappa, krippendorff_alpha, prevalence, weighted_kappa
from .synth import MineSpec, ScriptedTeacher, mine, pan

__version__ = "0.2.0"

__all__ = [
    "Claim", "Checker", "Verdict", "check_claims", "faithfulness_report",
    "Dataset", "read_dataset", "read_jsonl", "truth_rows", "verify_dataset", "write_dataset", "write_jsonl",
    "build_grading_tool",
    "adjudication_template", "compare", "read_labels", "summary_table", "validate", "validate_judge",
    "Dimension", "RubricSpec", "load_rubric", "parse_scores", "rubric_hash", "score_rows", "single_label_spec", "spec_from_dict",
    "agreement_report", "bootstrap", "cohen_kappa", "krippendorff_alpha", "prevalence", "weighted_kappa",
    "MineSpec", "ScriptedTeacher", "mine", "pan",
]
