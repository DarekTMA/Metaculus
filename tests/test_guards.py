import pytest
from forecasting_tools import NumericDistribution, Percentile, PredictedOption, PredictedOptionList

from prognozy import guards
from tests.conftest import binary_question, mc_question, numeric_question

GOOD_COMMENT = "Uzasadnienie " * 20


def test_binary_without_comment_rejected():
    with pytest.raises(guards.GuardError):
        guards.check_report(binary_question(), 0.4, "")
    with pytest.raises(guards.GuardError):
        guards.check_report(binary_question(), 0.4, None)


@pytest.mark.parametrize("value", [0.0, 0.005, 0.995, 1.0, float("nan")])
def test_binary_out_of_range_rejected(value):
    with pytest.raises(guards.GuardError):
        guards.check_report(binary_question(), value, GOOD_COMMENT)


@pytest.mark.parametrize("value", [0.01, 0.5, 0.99])
def test_binary_in_range_ok(value):
    guards.check_report(binary_question(), value, GOOD_COMMENT)


def _mc(probs):
    return PredictedOptionList(
        predicted_options=[PredictedOption(option_name=n, probability=p) for n, p in probs]
    )


def test_mc_ok_and_wrong_options():
    q = mc_question()
    guards.check_report(q, _mc([("A", 0.5), ("B", 0.3), ("C", 0.2)]), GOOD_COMMENT)
    with pytest.raises(guards.GuardError):
        guards.check_report(q, _mc([("A", 0.5), ("B", 0.3), ("X", 0.2)]), GOOD_COMMENT)
    with pytest.raises(guards.GuardError):  # brakująca opcja
        guards.check_report(q, _mc([("A", 0.6), ("B", 0.4)]), GOOD_COMMENT)
    # Skrajne 0/1 biblioteka sama zamienia na 0,1% / 99,8%, więc to przechodzi.
    guards.check_report(q, _mc([("A", 1.0), ("B", 0.0), ("C", 0.0)]), GOOD_COMMENT)


def _dist(question, values):
    pcts = [Percentile(percentile=p, value=v) for p, v in zip([0.1, 0.2, 0.4, 0.6, 0.8, 0.9], values)]
    return NumericDistribution.from_question(pcts, question)


@pytest.mark.parametrize("open_lower,open_upper", [(False, True), (True, False), (True, True), (False, False)])
def test_numeric_distribution_valid_and_monotonic(open_lower, open_upper):
    q = numeric_question(open_lower=open_lower, open_upper=open_upper)
    dist = _dist(q, [10, 20, 35, 50, 70, 85])
    guards.check_report(q, dist, GOOD_COMMENT)
    cdf = [p.percentile for p in dist.get_cdf()]
    assert len(cdf) == 201
    assert all(b > a for a, b in zip(cdf, cdf[1:]))


def test_cdf_checks_catch_bad_shapes():
    good = [i / 200 for i in range(201)]
    guards.check_cdf(good, expected_size=201, open_lower_bound=False, open_upper_bound=False)
    with pytest.raises(guards.GuardError):  # zła długość
        guards.check_cdf(good[:-1], expected_size=201, open_lower_bound=False, open_upper_bound=False)
    flat = list(good)
    flat[100] = flat[99]
    with pytest.raises(guards.GuardError):  # niemonotoniczna
        guards.check_cdf(flat, expected_size=201, open_lower_bound=False, open_upper_bound=False)
    with pytest.raises(guards.GuardError):  # otwarta granica, a CDF[0] = 0
        guards.check_cdf(good, expected_size=201, open_lower_bound=True, open_upper_bound=False)


def test_numeric_wrong_prediction_type_rejected():
    with pytest.raises(guards.GuardError):
        guards.check_report(numeric_question(), 0.5, GOOD_COMMENT)
