"""Przebieg całego przejścia bota z atrapami: Metaculus, źródła i model."""

import asyncio

from forecasting_tools import ReasonedPrediction

from prognozy.bot import PrognozyBot
from prognozy.ledger import DONE, PREDICTION_POSTED, Ledger
from prognozy.research import Researcher, Source
from prognozy.runner import run_once
from tests.conftest import FakeMetaculusClient, binary_question, mc_question

REASONING = "Status quo favours No. " * 20


def _researcher(fail=False):
    async def fetch(q):
        if fail:
            raise ConnectionError("źródło nie działa")
        return "news " * 100

    return Researcher([Source("atrapa", fetch)])


class FakeBot(PrognozyBot):
    """Bot z atrapą modelu: zawsze 30%."""

    def __init__(self, researcher, value=0.3):
        super().__init__(
            researcher=researcher,
            predictions_per_research_report=3,
            publish_reports_to_metaculus=False,
            enable_summarize_research=False,
            llms={"default": "fake/model", "parser": "fake/model",
                  "summarizer": "fake/model", "researcher": None},
            metaculus_client=FakeMetaculusClient(),
        )
        self.value = value

    async def _run_forecast_on_binary(self, question, research):
        assert "news" in research
        return ReasonedPrediction(prediction_value=self.value, reasoning=REASONING)


def _run(bot, client, ledger, tournaments=("t",), dry_run=False):
    return asyncio.run(run_once(bot=bot, client=client, ledger=ledger,
                                tournaments=list(tournaments), dry_run=dry_run))


def test_publishes_with_comment_and_no_duplicates_on_rerun(tmp_path):
    client = FakeMetaculusClient({"t": [binary_question(1), binary_question(2)]})
    ledger = Ledger(tmp_path / "r.sqlite")
    bot = FakeBot(_researcher())

    summary = _run(bot, client, ledger)
    assert len(summary.published) == 2
    assert [p[1] for p in client.predictions] == [1, 2]
    assert all(v == 0.3 for _, _, v in client.predictions)
    assert len(client.comments) == 2 and all(len(c) > 100 for _, c in client.comments)
    assert ledger.get(1).status == DONE

    # Ponowne uruchomienie (Metaculus jeszcze nie pokazuje prognozy): zero dubli.
    summary2 = _run(bot, client, ledger)
    assert summary2.published == []
    assert len(client.predictions) == 2


def test_source_failure_skips_question_without_posting(tmp_path):
    client = FakeMetaculusClient({"t": [binary_question(1)]})
    ledger = Ledger(tmp_path / "r.sqlite")
    summary = _run(FakeBot(_researcher(fail=True)), client, ledger)
    assert client.predictions == [] and client.comments == []
    assert summary.failed and not ledger.has_any(1)


def test_already_forecasted_and_unsupported_are_skipped(tmp_path):
    from forecasting_tools import ConditionalQuestion  # noqa: F401  (tylko sprawdzamy import)

    client = FakeMetaculusClient({"t": [binary_question(1, already_forecasted=True)]})
    ledger = Ledger(tmp_path / "r.sqlite")
    summary = _run(FakeBot(_researcher()), client, ledger)
    assert client.predictions == [] and summary.published == []


def test_missing_comment_is_repaired_next_run(tmp_path):
    client = FakeMetaculusClient({"t": [binary_question(1)]}, fail_comments=1)
    ledger = Ledger(tmp_path / "r.sqlite")
    bot = FakeBot(_researcher())

    summary = _run(bot, client, ledger)
    assert summary.failed and len(client.predictions) == 1 and client.comments == []
    assert ledger.get(1).status == PREDICTION_POSTED

    summary2 = _run(bot, client, ledger)
    assert summary2.comments_repaired == [1]
    assert len(client.predictions) == 1  # prognoza nie poszła drugi raz
    assert len(client.comments) == 1 and ledger.get(1).status == DONE


def test_dry_run_sends_nothing(tmp_path):
    client = FakeMetaculusClient({"t": [binary_question(1)]})
    ledger = Ledger(tmp_path / "r.sqlite")
    summary = _run(FakeBot(_researcher()), client, ledger, dry_run=True)
    assert summary.published and client.predictions == [] and not ledger.has_any(1)


def test_guard_blocks_bad_prediction(tmp_path):
    client = FakeMetaculusClient({"t": [binary_question(1)]})
    ledger = Ledger(tmp_path / "r.sqlite")

    class BadBot(FakeBot):
        async def _run_forecast_on_binary(self, question, research):
            return ReasonedPrediction(prediction_value=0.999, reasoning=REASONING)

    summary = _run(BadBot(_researcher()), client, ledger)
    assert summary.rejected and client.predictions == []


def test_unsupported_mc_question_type_still_selected(tmp_path):
    # Wielokrotny wybór jest obsługiwany: trafia do bota (tu atrapa nie ma MC -> błąd, pominięte).
    client = FakeMetaculusClient({"t": [mc_question(5)]})
    ledger = Ledger(tmp_path / "r.sqlite")
    summary = _run(FakeBot(_researcher()), client, ledger)
    assert client.predictions == [] and summary.failed
