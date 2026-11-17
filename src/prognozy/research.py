"""Zbieranie informacji do pytania z kilku źródeł naraz.

Źródła działają równolegle. Wynik to połączone raporty tych źródeł, które
odpowiedziały. Jeśli żadne nie dało sensownej odpowiedzi, rzucamy
``ResearchUnavailable``: pytanie zostanie pominięte, zamiast prognozować
na ślepo.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Awaitable, Callable

from forecasting_tools import AskNewsSearcher, MetaculusQuestion, clean_indents

from prognozy.throttle import ThrottledLlm

logger = logging.getLogger(__name__)

SourceFn = Callable[[MetaculusQuestion], Awaitable[str]]


class ResearchUnavailable(RuntimeError):
    """Żadne źródło informacji nie zadziałało. Pytanie pomijamy."""


@dataclass(frozen=True)
class Source:
    name: str
    fetch: SourceFn
    # Źródło dodatkowe (np. notowania rynków): dołączane, jeśli coś zwróci,
    # ale samo nie wystarcza, żeby uznać research za udany.
    supplementary: bool = False


def research_prompt(question: MetaculusQuestion) -> str:
    return clean_indents(
        f"""
        You are a research assistant to a superforecaster. Collect the most
        relevant, up-to-date facts needed to forecast the question below.
        Give dates and sources. Cover: the current status quo, recent trends,
        scheduled events before the resolution date, prices on prediction
        markets (Polymarket, Kalshi, Manifold) and similar forecasting questions
        if they exist. State whether the question would resolve Yes or No based
        on current information. Do not give a forecast yourself.

        Question:
        {question.question_text}

        Resolution criteria:
        {question.resolution_criteria}

        Fine print:
        {question.fine_print}
        """
    )


def _asknews_source() -> Source:
    async def fetch(question: MetaculusQuestion) -> str:
        return await AskNewsSearcher().call_preconfigured_version(
            "asknews/news-summaries", question.question_text
        )

    return Source("AskNews", fetch)


def _llm_search_source(model: str) -> Source:
    async def fetch(question: MetaculusQuestion) -> str:
        llm = ThrottledLlm(model=model, temperature=0.1, timeout=180, allowed_tries=3)
        return await llm.invoke(research_prompt(question))

    return Source(model, fetch)


def market_source(query_model: str | None = None) -> Source:
    from prognozy.markets import MarketSearch, llm_query_maker

    search = MarketSearch(llm_query_maker(query_model) if query_model else None)
    return Source("prediction-markets", search.fetch, supplementary=True)


def default_sources(
    search_models: tuple[str, ...] = (),
    *,
    markets: bool = False,
    market_query_model: str | None = None,
) -> list[Source]:
    """Dobiera źródła do kluczy, które są w środowisku."""
    sources: list[Source] = []
    if (os.getenv("ASKNEWS_CLIENT_ID") and os.getenv("ASKNEWS_SECRET")) or os.getenv(
        "ASKNEWS_API_KEY"
    ):
        sources.append(_asknews_source())
    models = list(search_models)
    if not models:
        if os.getenv("PERPLEXITY_API_KEY"):
            models = ["perplexity/sonar-pro"]
        elif os.getenv("OPENROUTER_API_KEY"):
            models = ["openrouter/perplexity/sonar-pro"]
    sources.extend(_llm_search_source(m) for m in models)
    if markets:
        sources.append(market_source(market_query_model))
    return sources


class Researcher:
    def __init__(self, sources: list[Source], min_chars: int = 200, cache: bool = False) -> None:
        self._sources = sources
        self._min_chars = min_chars
        # Pamięć podręczna na czas jednego procesu: przy porównaniu modeli
        # każdy wariant dostaje ten sam research i nie płacimy za niego kilka razy.
        self._cache: dict[int | str, str] | None = {} if cache else None

    @property
    def source_names(self) -> list[str]:
        return [s.name for s in self._sources]

    @property
    def has_primary_source(self) -> bool:
        return any(not s.supplementary for s in self._sources)

    async def run(self, question: MetaculusQuestion) -> str:
        key = question.id_of_question or question.question_text
        if self._cache is not None and key in self._cache:
            return self._cache[key]
        if not self.has_primary_source:
            raise ResearchUnavailable("Nie skonfigurowano żadnego głównego źródła informacji.")

        results = await asyncio.gather(
            *(s.fetch(question) for s in self._sources), return_exceptions=True
        )
        sections: list[str] = []
        primary_ok = False
        for source, result in zip(self._sources, results):
            if isinstance(result, BaseException):
                logger.warning("Źródło %s nie zadziałało: %s", source.name, result)
                continue
            text = (result or "").strip()
            if source.supplementary:
                if text:
                    sections.append(f"## Source: {source.name}\n{text}")
                continue
            if len(text) < self._min_chars:
                logger.warning("Źródło %s zwróciło za mało treści.", source.name)
                continue
            primary_ok = True
            sections.append(f"## Source: {source.name}\n{text}")

        if not primary_ok:
            raise ResearchUnavailable(
                f"Żadne główne źródło nie dało informacji dla {question.page_url}."
            )
        research = "\n\n".join(sections)
        if self._cache is not None:
            self._cache[key] = research
        return research
