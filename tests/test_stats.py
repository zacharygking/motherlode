import math

import pytest

from motherlode.stats import agreement_report, bootstrap, cohen_kappa, krippendorff_alpha, prevalence


def test_kappa_perfect_and_chance():
    a = ["x", "y", "x", "y", "z", "z"]
    assert cohen_kappa(a, a) == pytest.approx(1.0)
    # every label the same on both sides: kappa is undefined, and the report shows it as NaN
    assert math.isnan(cohen_kappa(["x"] * 10, ["x"] * 10))


def test_kappa_known_value():
    # classic 2x2 example: 20 agree yes, 15 agree no, 5 and 10 disagree -> kappa 0.4
    a = ["yes"] * 20 + ["no"] * 15 + ["yes"] * 5 + ["no"] * 10
    b = ["yes"] * 20 + ["no"] * 15 + ["no"] * 5 + ["yes"] * 10
    assert cohen_kappa(a, b) == pytest.approx(0.4, abs=1e-9)


def test_kappa_is_below_raw_agreement_when_one_label_dominates():
    a = ["ok"] * 95 + ["bad"] * 5
    b = ["ok"] * 97 + ["bad"] * 3
    raw = sum(x == y for x, y in zip(a, b)) / 100
    assert raw > 0.95
    assert cohen_kappa(a, b) < raw - 0.2


def test_alpha_matches_kappa_for_two_full_raters_roughly():
    a = ["yes"] * 20 + ["no"] * 15 + ["yes"] * 5 + ["no"] * 10
    b = ["yes"] * 20 + ["no"] * 15 + ["no"] * 5 + ["yes"] * 10
    alpha = krippendorff_alpha([a, b], "nominal")
    assert 0.3 < alpha < 0.5


def test_alpha_handles_missing_and_perfect():
    data = [["a", "b", None, "c"], ["a", "b", "c", "c"], [None, "b", "c", None]]
    assert krippendorff_alpha(data) == pytest.approx(1.0)
    assert math.isnan(krippendorff_alpha([["a"], [None]]))


def test_bootstrap_interval_contains_estimate_and_is_reproducible():
    a = ["yes"] * 30 + ["no"] * 30
    b = ["yes"] * 25 + ["no"] * 5 + ["no"] * 26 + ["yes"] * 4
    est, lo, hi = bootstrap(cohen_kappa, a, b, n=500, seed=1)
    assert lo <= est <= hi
    assert bootstrap(cohen_kappa, a, b, n=500, seed=1) == (est, lo, hi)


def test_agreement_report_labels_raw_as_not_for_reporting():
    r = agreement_report(["a", "b", "a"], ["a", "b", "b"], n_boot=50)
    assert set(r) >= {"kappa", "kappa_ci95", "raw_agreement_do_not_report", "prevalence_human", "prevalence_judge", "n"}
    assert prevalence(["a", "a", "b"]) == {"a": 2 / 3, "b": 1 / 3}
