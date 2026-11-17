"""Wspólne atrapy. Testy nie mają dostępu do sieci ani do plików hosta."""

from __future__ import annotations

import socket
from typing import Any

import pytest
from forecasting_tools import (
    BinaryQuestion,
    MultipleChoiceQuestion,
    NumericQuestion,
)

from prognozy.config import SECRET_ENV_VARS


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def guard(*args, **kwargs):
        raise RuntimeError("Test próbował połączyć się z siecią.")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for name in SECRET_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    for name in ("PROGNOZY_PUBLISH", "PROGNOZY_SEARCH_MODELS", "PROGNOZY_TOURNAMENT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PROGNOZY_STATE_DIR", str(tmp_path / "stan"))


def binary_question(qid: int = 1, **kw: Any) -> BinaryQuestion:
    fields = dict(
        question_text=f"Will thing {qid} happen?",
        id_of_question=qid,
        id_of_post=1000 + qid,
        page_url=f"https://www.metaculus.com/questions/{1000 + qid}",
        resolution_criteria="Resolves Yes if thing happens.",
        fine_print="",
        background_info="",
    )
    fields.update(kw)
    return BinaryQuestion(**fields)


def mc_question(qid: int = 2) -> MultipleChoiceQuestion:
    return MultipleChoiceQuestion(
        question_text="Which?",
        id_of_question=qid,
        id_of_post=1000 + qid,
        page_url=f"https://www.metaculus.com/questions/{1000 + qid}",
        options=["A", "B", "C"],
    )


def numeric_question(qid: int = 3, open_lower=False, open_upper=True) -> NumericQuestion:
    return NumericQuestion(
        question_text="How many?",
        id_of_question=qid,
        id_of_post=1000 + qid,
        page_url=f"https://www.metaculus.com/questions/{1000 + qid}",
        lower_bound=0,
        upper_bound=100,
        open_lower_bound=open_lower,
        open_upper_bound=open_upper,
        unit_of_measure="units",
    )


class FakeMetaculusClient:
    """Atrapa klienta Metaculus: zapisuje wywołania zamiast wysyłać."""

    def __init__(self, questions_by_tournament=None, fail_comments: int = 0):
        self.questions_by_tournament = questions_by_tournament or {}
        self.predictions: list[tuple[str, int, Any]] = []
        self.comments: list[tuple[int, str]] = []
        self._fail_comments = fail_comments

    async def get_questions_matching_filter(self, api_filter):
        (tournament,) = api_filter.allowed_tournaments
        return list(self.questions_by_tournament.get(tournament, []))

    def post_binary_question_prediction(self, question_id, value):
        self.predictions.append(("binary", question_id, value))

    def post_multiple_choice_question_prediction(self, question_id, value):
        self.predictions.append(("mc", question_id, value))

    def post_numeric_question_prediction(self, question_id, value):
        self.predictions.append(("numeric", question_id, value))

    def post_question_comment(self, post_id, comment_text, *a, **kw):
        if self._fail_comments > 0:
            self._fail_comments -= 1
            raise ConnectionError("komentarz nie przeszedł")
        self.comments.append((post_id, comment_text))
