"""Jedno przejście bota: pobierz pytania, prognozuj, sprawdź, wyślij."""

from __future__ import annotations

import logging
from typing import Any, Iterable

from forecasting_tools import ApiFilter, ForecastBot, MetaculusClient, MetaculusQuestion

from prognozy import guards
from prognozy.ledger import Ledger
from prognozy.publisher import Publisher, PublishSummary

logger = logging.getLogger(__name__)


def select_questions(
    questions: Iterable[MetaculusQuestion], ledger: Ledger, *, skip_forecasted: bool = True
) -> list[MetaculusQuestion]:
    """Zostawia tylko pytania, na które jeszcze nie prognozowaliśmy."""
    selected = []
    for q in questions:
        if not guards.is_supported(q):
            logger.info("Pomijam %s: typ %s nieobsługiwany.", q.page_url, type(q).__name__)
            continue
        if skip_forecasted and q.already_forecasted:
            continue
        if q.id_of_question is not None and ledger.has_any(q.id_of_question):
            continue
        selected.append(q)
    return selected


async def fetch_open_questions(client: Any, tournament_id: int | str) -> list[MetaculusQuestion]:
    api_filter = ApiFilter(
        allowed_tournaments=[tournament_id],
        allowed_statuses=["open"],
        group_question_mode="unpack_subquestions",
    )
    return await client.get_questions_matching_filter(api_filter)


async def run_once(
    *,
    bot: ForecastBot,
    client: MetaculusClient | Any,
    ledger: Ledger,
    tournaments: list[int | str],
    dry_run: bool,
    skip_forecasted: bool = True,
) -> PublishSummary:
    summary = PublishSummary()
    publisher = Publisher(client, ledger, dry_run=dry_run)
    publisher.repair_missing_comments(summary)

    for tournament in tournaments:
        try:
            questions = await fetch_open_questions(client, tournament)
        except Exception as exc:  # noqa: BLE001
            logger.error("Nie udało się pobrać pytań z %s: %s", tournament, exc)
            summary.failed.append(f"{tournament}: pobieranie pytań: {exc}")
            continue
        todo = select_questions(questions, ledger, skip_forecasted=skip_forecasted)
        logger.info("%s: %d otwartych, %d do prognozy.", tournament, len(questions), len(todo))
        if not todo:
            continue

        results = await bot.forecast_questions(todo, return_exceptions=True)
        for question, result in zip(todo, results):
            if isinstance(result, BaseException):
                # Np. brak informacji ze źródeł: pytanie pomijamy, spróbujemy przy następnym uruchomieniu.
                logger.warning("Pominięto %s: %s", question.page_url, result)
                summary.failed.append(f"{question.page_url}: {type(result).__name__}")
                continue
            await publisher.publish(result, summary)

    logger.info(
        "Podsumowanie: wysłane=%d, odrzucone=%d, duble=%d, błędy=%d, dosłane komentarze=%d",
        len(summary.published),
        len(summary.rejected),
        len(summary.skipped_duplicates),
        len(summary.failed),
        len(summary.comments_repaired),
    )
    return summary
