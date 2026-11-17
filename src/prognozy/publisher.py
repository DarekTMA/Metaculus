"""Wysyłanie gotowych prognoz na Metaculus z bezpiecznikami i bez dubli."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from prognozy import guards
from prognozy.ledger import DONE, PREDICTION_POSTED, Ledger

logger = logging.getLogger(__name__)


class _TrackingClient:
    """Przepuszcza wywołania do prawdziwego klienta Metaculus.

    Zapisuje w rejestrze moment, w którym prognoza została już wysłana,
    a komentarz jeszcze nie. Biblioteka wysyła najpierw prognozę, potem
    komentarz, więc wywołanie ``post_question_comment`` oznacza, że prognoza
    jest już na serwerze.
    """

    def __init__(self, client: Any, ledger: Ledger, question_id: int, post_id: int):
        self._client = client
        self._ledger = ledger
        self._question_id = question_id
        self._post_id = post_id

    def post_question_comment(self, post_id: int, comment_text: str, *a, **kw):
        self._ledger.mark(self._question_id, self._post_id, PREDICTION_POSTED, comment_text)
        result = self._client.post_question_comment(post_id, comment_text, *a, **kw)
        self._ledger.mark(self._question_id, self._post_id, DONE, comment_text)
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


@dataclass
class PublishSummary:
    published: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    skipped_duplicates: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    comments_repaired: list[int] = field(default_factory=list)
    fetch_failed: bool = False
    budget_stopped: bool = False

    def one_line(self) -> str:
        text = (
            f"wysłane={len(self.published)}, odrzucone={len(self.rejected)}, "
            f"duble={len(self.skipped_duplicates)}, błędy={len(self.failed)}, "
            f"dosłane komentarze={len(self.comments_repaired)}"
        )
        if self.budget_stopped:
            text += ", ZATRZYMANE PRZEZ LIMIT WYDATKÓW"
        return text

    def report(self) -> str:
        lines = [self.one_line()]
        for title, items in (("Odrzucone", self.rejected), ("Błędy", self.failed)):
            lines += [f"{title}:"] + [f"  {i}" for i in items] if items else []
        return "\n".join(lines)


class Publisher:
    def __init__(self, client: Any, ledger: Ledger, *, dry_run: bool) -> None:
        self._client = client
        self._ledger = ledger
        self._dry_run = dry_run

    def repair_missing_comments(self, summary: PublishSummary) -> None:
        """Dosyła komentarze do prognoz, które poszły bez komentarza."""
        for entry in self._ledger.pending_comments():
            if self._dry_run:
                logger.info("[próba] dosłałbym komentarz do pytania %s", entry.question_id)
                continue
            try:
                self._client.post_question_comment(entry.post_id, entry.comment)
                self._ledger.mark(entry.question_id, entry.post_id, DONE, entry.comment)
                summary.comments_repaired.append(entry.question_id)
                logger.info("Dosłano brakujący komentarz do pytania %s", entry.question_id)
            except Exception as exc:  # noqa: BLE001
                logger.error("Nie udało się dosłać komentarza (%s): %s", entry.question_id, exc)

    async def publish(self, report: Any, summary: PublishSummary) -> None:
        question = report.question
        qid = question.id_of_question
        url = question.page_url
        if qid is None or question.id_of_post is None:
            summary.failed.append(f"{url}: brak ID pytania/posta")
            return

        if self._ledger.has_any(qid):
            logger.info("Pomijam %s: już w rejestrze wysłanych.", url)
            summary.skipped_duplicates.append(url)
            return

        try:
            guards.check_report(question, report.prediction, report.explanation)
        except guards.GuardError as exc:
            logger.warning("Odrzucono prognozę dla %s: %s", url, exc)
            summary.rejected.append(f"{url}: {exc}")
            return

        if self._dry_run:
            logger.info("[próba] wysłałbym prognozę dla %s", url)
            summary.published.append(url)
            return

        tracking = _TrackingClient(self._client, self._ledger, qid, question.id_of_post)
        try:
            await report.publish_report_to_metaculus(metaculus_client=tracking)
        except Exception as exc:  # noqa: BLE001
            logger.error("Błąd wysyłania dla %s: %s", url, exc)
            summary.failed.append(f"{url}: {exc}")
            return
        summary.published.append(url)
        logger.info("Wysłano prognozę: %s", url)
