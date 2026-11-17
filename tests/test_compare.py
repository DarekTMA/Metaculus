import asyncio
import json

from prognozy.compare import (
    exclude_tournament_questions,
    expected_baseline_score,
    run_comparison,
    save_rows,
    summarize,
)
from tests.conftest import binary_question, mc_question
from tests.test_publish_flow import FakeBot, _researcher


def test_score_is_best_when_matching_community():
    cp = 0.3
    best = expected_baseline_score(cp, cp)
    assert best > expected_baseline_score(0.5, cp) > expected_baseline_score(0.95, cp)
    assert abs(expected_baseline_score(0.5, 0.5)) < 1e-9


def test_exclusion_of_tournament_and_non_binary_questions():
    ok = binary_question(1, community_prediction_at_access_time=0.4, tournament_slugs=["acx"])
    aib = binary_question(2, community_prediction_at_access_time=0.4, tournament_slugs=["minibench"])
    no_cp = binary_question(3)
    kept = exclude_tournament_questions([ok, aib, no_cp, mc_question()], ["minibench", 33121])
    assert kept == [ok]


def test_comparison_end_to_end_with_fake_bots(tmp_path):
    qs = [binary_question(i, community_prediction_at_access_time=0.3) for i in (1, 2)]
    rows = asyncio.run(run_comparison(qs, {
        "dobry": FakeBot(_researcher(), value=0.3),
        "zly": FakeBot(_researcher(), value=0.9),
    }))
    assert len(rows) == 4
    table = summarize(rows)
    assert "dobry | 2" in table and "zly | 2" in table
    good = [r.score for r in rows if r.variant == "dobry"]
    bad = [r.score for r in rows if r.variant == "zly"]
    assert min(good) > max(bad)
    path = save_rows(rows, tmp_path)
    assert len([json.loads(x) for x in path.read_text().splitlines()]) == 4
