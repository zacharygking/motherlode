"""motherlode: prospect it, mine it, pan it, handpick the rest, keep the paydirt.

A synthesis engine for ML projects, in mining order. ``prospect`` validates the judge and the
checkers on a hand-labeled sample before anything is generated at scale, ``mine`` generates a set
from a teacher or a source, ``pan`` runs every sample through the checkers and keeps what passed, and ``handpick`` builds the
tool a person uses to label samples by hand, blind and assisted. The output is the paydirt; the rejects are the tailings, kept with
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
