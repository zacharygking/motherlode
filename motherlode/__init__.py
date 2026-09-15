"""motherlode: mine it, prove it, pan it, keep the paydirt.

A synthesis engine for ML projects. ``mine`` generates a set from a teacher or a source,
``prove`` makes a sample prove itself against ground truth and validates any judge against human labels,
``pan`` keeps what passed. The output is the paydirt; the rejects are the tailings, kept with
their reasons. Everything here is domain-agnostic: checkers, prompts and data live with the
project that mines them.
"""

from .claims import Claim, Checker, Verdict, check_claims, faithfulness_report
from .judge import validate_judge
from .stats import agreement_report, bootstrap, cohen_kappa, krippendorff_alpha, prevalence
from .synth import MineSpec, ScriptedTeacher, mine, pan

__version__ = "0.1.0"

__all__ = [
    "Claim", "Checker", "Verdict", "check_claims", "faithfulness_report",
    "validate_judge",
    "agreement_report", "bootstrap", "cohen_kappa", "krippendorff_alpha", "prevalence",
    "MineSpec", "ScriptedTeacher", "mine", "pan",
]
