import asyncio
import logging

from forecasting_tools import GeneralLlm, ReasonedPrediction

from prognozy import throttle
from prognozy.bot import PrognozyBot
from prognozy.logs import MAX_MESSAGE_CHARS, SecretRedactingFilter
from prognozy.throttle import RpmLimiter, ThrottledLlm, throttled
from tests.conftest import FakeMetaculusClient, binary_question
from tests.test_publish_flow import REASONING, FakeBot, _researcher


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def time(self):
        return self.now

    async def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def test_limiter_allows_rpm_then_waits_for_window():
    clock = FakeClock()
    lim = RpmLimiter(3, clock=clock.time, sleep=clock.sleep)

    async def go():
        for _ in range(7):
            await lim.acquire()

    asyncio.run(go())
    # 7 startów przy limicie 3/min: dwa razy trzeba było czekać na nowe okno.
    assert len(clock.sleeps) == 2
    assert 120 <= clock.now < 122


def test_throttled_keeps_settings_and_skips_special_models():
    base = GeneralLlm(model="openrouter/anthropic/claude-opus-5.5", temperature=0.3, timeout=160)
    t = throttled(base)
    assert isinstance(t, ThrottledLlm) and t.model == base.model
    assert t.litellm_kwargs["temperature"] == 0.3 and t.litellm_kwargs["timeout"] == 160
    assert throttled("asknews/news-summaries") == "asknews/news-summaries"
    assert throttled(None) is None
    assert throttled(t) is t


def test_build_llms_throttles_every_model():
    llms = PrognozyBot.build_llms(None, None, None)
    for purpose in ("default", "parser", "summarizer"):
        assert isinstance(llms[purpose], ThrottledLlm), purpose


def test_throttled_llm_waits_before_each_attempt(monkeypatch):
    calls = []

    class Recorder:
        async def acquire(self):
            calls.append("acquire")

    async def fake_direct(self, prompt):
        calls.append("call")
        return "ok"

    monkeypatch.setattr(throttle, "limiter_for", lambda model: Recorder())
    monkeypatch.setattr(GeneralLlm, "_mockable_direct_call_to_model", fake_direct)
    llm = ThrottledLlm(model="openrouter/x")
    assert asyncio.run(llm._mockable_direct_call_to_model("p")) == "ok"
    assert calls == ["acquire", "call"]


def test_one_question_at_a_time(tmp_path):
    state = {"now": 0, "max": 0}

    class SlowBot(FakeBot):
        async def _run_forecast_on_binary(self, question, research):
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
            await asyncio.sleep(0.01)
            state["now"] -= 1
            return ReasonedPrediction(prediction_value=0.3, reasoning=REASONING)

    bot = SlowBot(_researcher())  # parallel_questions domyślnie 1
    asyncio.run(bot.forecast_questions([binary_question(i) for i in range(1, 4)],
                                       return_exceptions=True))
    # 3 prognozy jednego pytania idą równolegle, ale nigdy z dwóch pytań naraz.
    assert state["max"] <= bot.predictions_per_research_report


def test_long_log_messages_are_truncated(caplog):
    logger = logging.getLogger("test.long")
    caplog.handler.addFilter(SecretRedactingFilter())
    with caplog.at_level(logging.INFO):
        logger.warning("x" * (MAX_MESSAGE_CHARS * 5))
    assert len(caplog.records[-1].getMessage()) < MAX_MESSAGE_CHARS + 100
    assert "ucięto" in caplog.text


def test_fake_client_import_guard():
    assert FakeMetaculusClient
