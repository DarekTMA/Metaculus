"""Notowania rynków prognoz (Polymarket, Manifold) jako źródło informacji.

Rynki szukamy po słowach kluczowych. Wyniki mogą dotyczyć innego pytania niż
nasze, więc w raporcie są opisane jako "possibly related": model sam ocenia,
czy rynek pasuje do warunków rozstrzygnięcia.

Oba API są publiczne i nie wymagają kluczy.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import requests
from forecasting_tools import MetaculusQuestion

from prognozy.throttle import ThrottledLlm

logger = logging.getLogger(__name__)

POLYMARKET_URL = "https://gamma-api.polymarket.com/public-search"
MANIFOLD_URL = "https://api.manifold.markets/v0/search-markets"
TIMEOUT = 20
MAX_MARKETS_PER_SITE = 5
MIN_MANIFOLD_BETTORS = 10  # rynki z garstką graczy niewiele mówią

HttpGet = Callable[[str, dict], Any]  # zwraca zdekodowany JSON
QueryMaker = Callable[[MetaculusQuestion], Awaitable[list[str]]]

_STOPWORDS = {
    "will", "the", "a", "an", "of", "in", "on", "by", "for", "to", "be", "is",
    "are", "before", "after", "than", "more", "less", "at", "least", "what",
    "which", "who", "how", "many", "much", "when", "and", "or", "there", "any",
    "does", "do", "its", "it", "with", "from", "this", "that", "as", "between",
}


@dataclass(frozen=True)
class Market:
    site: str
    title: str
    probability: float | None
    volume: float | None
    url: str
    detail: str = ""

    def line(self) -> str:
        prob = f"{self.probability:.0%}" if self.probability is not None else "n/a"
        vol = f", volume {self.volume:,.0f}" if self.volume else ""
        extra = f" {self.detail}" if self.detail else ""
        return f"- [{self.site}] {self.title}: {prob}{vol}{extra} ({self.url})"


def _http_get(url: str, params: dict) -> Any:
    response = requests.get(url, params=params, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def keyword_query(text: str, max_words: int = 6) -> str:
    """Prosta heurystyka: słowa bez wypełniaczy i interpunkcji."""
    words = [w.strip(".,'") for w in re.findall(r"[A-Za-z0-9$€%.,\-']+", text)]
    kept = [w for w in words if w and w.lower() not in _STOPWORDS]
    return " ".join(kept[:max_words])


def llm_query_maker(model: str) -> QueryMaker:
    """Tani model układa 2 krótkie zapytania; przy błędzie zostaje heurystyka."""

    async def make(question: MetaculusQuestion) -> list[str]:
        prompt = (
            "Write 2 short search queries (2-5 words each) to find prediction "
            "markets about this question on Polymarket or Manifold. Return only a "
            'JSON list of strings, e.g. ["tesla deliveries q4", "tesla sales 2026"].\n\n'
            f"Question: {question.question_text}"
        )
        try:
            text = await ThrottledLlm(model=model, temperature=0.0, timeout=60).invoke(prompt)
            match = re.search(r"\[.*\]", text, re.S)
            queries = json.loads(match.group(0)) if match else []
            queries = [q.strip() for q in queries if isinstance(q, str) and q.strip()]
            if queries:
                return queries[:2]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Model nie ułożył zapytań o rynki: %s", exc)
        return [keyword_query(question.question_text)]

    return make


async def _heuristic_queries(question: MetaculusQuestion) -> list[str]:
    return [keyword_query(question.question_text)]


def parse_polymarket(data: Any) -> list[Market]:
    markets: list[Market] = []
    for event in (data or {}).get("events", []) or []:
        if event.get("closed"):
            continue
        slug = event.get("slug", "")
        url = f"https://polymarket.com/event/{slug}"
        sub = [m for m in event.get("markets", []) or [] if not m.get("closed")]
        parts = []
        for m in sub[:8]:
            try:
                outcomes = json.loads(m.get("outcomes") or "[]")
                prices = [float(p) for p in json.loads(m.get("outcomePrices") or "[]")]
            except (ValueError, TypeError):
                continue
            if "Yes" in outcomes and len(prices) == len(outcomes):
                label = m.get("groupItemTitle") or m.get("question") or ""
                parts.append((label, prices[outcomes.index("Yes")]))
        if not parts:
            continue
        volume = _float(event.get("volume"))
        if len(parts) == 1:
            markets.append(Market("Polymarket", event.get("title", ""), parts[0][1], volume, url))
        else:
            detail = "; ".join(f"{label}: {p:.0%}" for label, p in parts)
            markets.append(
                Market("Polymarket", event.get("title", ""), None, volume, url, f"[{detail}]")
            )
    return markets[:MAX_MARKETS_PER_SITE]


def parse_manifold(data: Any) -> list[Market]:
    markets: list[Market] = []
    for m in data or []:
        if m.get("isResolved") or m.get("outcomeType") != "BINARY":
            continue
        if (m.get("uniqueBettorCount") or 0) < MIN_MANIFOLD_BETTORS:
            continue
        prob = _float(m.get("probability"))
        markets.append(
            Market("Manifold", m.get("question", ""), prob, _float(m.get("volume")), m.get("url", ""))
        )
    return markets[:MAX_MARKETS_PER_SITE]


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class MarketSearch:
    """Źródło dla Researchera: szuka rynków i opisuje ich notowania."""

    def __init__(
        self,
        query_maker: QueryMaker | None = None,
        http_get: HttpGet = _http_get,
    ) -> None:
        self._query_maker = query_maker or _heuristic_queries
        self._http_get = http_get

    async def _search(self, query: str) -> list[Market]:
        found: list[Market] = []
        calls = [
            (POLYMARKET_URL, {"q": query, "limit_per_type": 5, "events_status": "active"}, parse_polymarket),
            (MANIFOLD_URL, {"term": query, "limit": 10}, parse_manifold),
        ]
        for url, params, parse in calls:
            try:
                data = await asyncio.to_thread(self._http_get, url, params)
                found.extend(parse(data))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Wyszukiwanie rynków (%s) nie zadziałało: %s", url, exc)
        return found

    async def fetch(self, question: MetaculusQuestion) -> str:
        queries = await self._query_maker(question)
        seen: set[str] = set()
        markets: list[Market] = []
        for query in queries:
            for market in await self._search(query):
                if market.url not in seen:
                    seen.add(market.url)
                    markets.append(market)
        if not markets:
            return ""
        lines = "\n".join(m.line() for m in markets)
        return (
            "Prediction markets found by keyword search (possibly related; check "
            "whether each one matches this question's resolution criteria and dates "
            "before using it):\n" + lines
        )
