import asyncio
import json

from prognozy.markets import MarketSearch, keyword_query, parse_manifold, parse_polymarket
from prognozy.research import Researcher, ResearchUnavailable, Source
from tests.conftest import binary_question

POLY = {
    "events": [
        {
            "title": "How many Tesla deliveries in Q4 2026?",
            "slug": "tesla-q4",
            "closed": False,
            "volume": "24482.9",
            "markets": [
                {"groupItemTitle": "<400k", "outcomes": '["Yes", "No"]',
                 "outcomePrices": '["0.045", "0.955"]', "closed": False},
                {"groupItemTitle": "400k-425k", "outcomes": '["Yes", "No"]',
                 "outcomePrices": '["0.12", "0.88"]', "closed": False},
            ],
        },
        {"title": "Old", "slug": "old", "closed": True, "markets": []},
        {
            "title": "Will X happen?", "slug": "x", "closed": False, "volume": 10,
            "markets": [{"question": "Will X happen?", "outcomes": '["Yes", "No"]',
                         "outcomePrices": '["0.3", "0.7"]', "closed": False}],
        },
    ]
}

MANI = [
    {"question": "Will Tesla increase deliveries in 2026?", "outcomeType": "BINARY",
     "probability": 0.95, "isResolved": False, "volume": 5687, "uniqueBettorCount": 40,
     "url": "https://manifold.markets/a/b"},
    {"question": "Resolved", "outcomeType": "BINARY", "probability": 1, "isResolved": True,
     "uniqueBettorCount": 99, "url": "u1"},
    {"question": "Tiny", "outcomeType": "BINARY", "probability": 0.5, "isResolved": False,
     "uniqueBettorCount": 2, "url": "u2"},
    {"question": "MC", "outcomeType": "MULTIPLE_CHOICE", "isResolved": False,
     "uniqueBettorCount": 99, "url": "u3"},
]


def test_parse_polymarket_groups_brackets_and_skips_closed():
    markets = parse_polymarket(POLY)
    assert [m.title for m in markets] == ["How many Tesla deliveries in Q4 2026?", "Will X happen?"]
    assert "<400k: 4%" in markets[0].line() and "400k-425k: 12%" in markets[0].line()
    assert markets[1].probability == 0.3


def test_parse_manifold_keeps_only_open_binary_with_bettors():
    markets = parse_manifold(MANI)
    assert len(markets) == 1 and markets[0].probability == 0.95


def test_parse_tolerates_garbage():
    assert parse_polymarket(None) == [] and parse_manifold(None) == []
    assert parse_polymarket({"events": [{"markets": [{"outcomes": "xx"}]}]}) == []


def test_keyword_query():
    assert keyword_query("Will Tesla deliver more than 450,000 vehicles in Q4 2026?") == (
        "Tesla deliver 450,000 vehicles Q4 2026"
    )


def test_market_search_combines_sites_and_survives_errors():
    calls = []

    def fake_get(url, params):
        calls.append(url)
        if "polymarket" in url:
            return POLY
        raise ConnectionError("manifold leży")

    text = asyncio.run(MarketSearch(http_get=fake_get).fetch(binary_question()))
    assert "possibly related" in text and "Polymarket" in text
    assert len(calls) == 2


def test_market_search_with_llm_queries_dedupes():
    async def queries(q):
        return ["a", "b"]

    text = asyncio.run(
        MarketSearch(query_maker=queries, http_get=lambda u, p: POLY if "poly" in u else MANI)
        .fetch(binary_question())
    )
    assert text.count("How many Tesla deliveries") == 1


def _src(name, text, supplementary=False):
    async def fetch(q):
        return text

    return Source(name, fetch, supplementary=supplementary)


def test_markets_alone_are_not_enough_to_forecast():
    r = Researcher([_src("news", "", False), _src("markets", "- market 40%", True)])
    try:
        asyncio.run(r.run(binary_question()))
        raise AssertionError("powinno rzucić")
    except ResearchUnavailable:
        pass


def test_markets_are_appended_to_primary_research():
    r = Researcher([_src("news", "fact " * 100), _src("markets", "- market 40%", True)])
    text = asyncio.run(r.run(binary_question()))
    assert "Source: markets" in text and "Source: news" in text


def test_research_cache_calls_sources_once():
    n = {"calls": 0}

    async def fetch(q):
        n["calls"] += 1
        return "fact " * 100

    r = Researcher([Source("news", fetch)], cache=True)
    asyncio.run(r.run(binary_question()))
    asyncio.run(r.run(binary_question()))
    assert n["calls"] == 1


def test_fixture_is_valid_json():
    json.dumps(POLY)
