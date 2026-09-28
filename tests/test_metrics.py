import math

from costci import metrics
from costci.estimators import _two_point


def test_direction_thresholds():
    assert metrics.direction(0.05) == "immaterial"
    assert metrics.direction(0.10) == "increase"
    assert metrics.direction(-0.2) == "decrease"
    assert metrics.direction(math.inf) == "increase"


def test_buckets_cover_the_line():
    for x in (-5, -0.7, -0.3, -0.15, 0, 0.15, 0.3, 0.7, 5, math.inf):
        assert metrics.bucket(x) is not None


def test_spearman_perfect_and_inverse():
    assert math.isclose(metrics.spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)
    assert math.isclose(metrics.spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)


def test_two_point_extrapolation_recovers_power_law():
    # d = n^1.5 sampled at 1% and 10% -> full scale (n=1) should give 1.0
    d = lambda f: f ** 1.5
    assert math.isclose(_two_point(d(0.01), d(0.1), 0.01, 0.1), 1.0, rel_tol=1e-9)


def test_score_counts_false_warnings_on_immaterial_truth():
    rows = [{"truth_rel": 0.0, "truth_delta": 0.0, "x_rel": 0.3, "x_delta": 3.0},
            {"truth_rel": 0.0, "truth_delta": 0.0, "x_rel": 0.01, "x_delta": 0.1}]
    s = metrics.score(rows, "x")
    assert s["false_warning_rate"] == 0.5
