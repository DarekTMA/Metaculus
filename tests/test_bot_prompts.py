"""Prompty i parsowanie z atrapą modelu (bez sieci)."""

import asyncio

from forecasting_tools import BinaryPrediction, Percentile

from prognozy import bot as bot_module
from prognozy import guards
from prognozy.bot import PrognozyBot
from prognozy.research import Researcher
from tests.conftest import FakeMetaculusClient, binary_question, numeric_question


class FakeLlm:
    def __init__(self):
        self.prompts = []

    async def invoke(self, prompt):
        self.prompts.append(prompt)
        return "Reasoning... Probability: 140%"


def _bot(llm):
    b = PrognozyBot(
        researcher=Researcher([]),
        llms={"default": "fake/m", "parser": "fake/m", "summarizer": "fake/m", "researcher": None},
        metaculus_client=FakeMetaculusClient(),
    )
    b.get_llm = lambda purpose, kind=None: llm  # type: ignore[method-assign]
    return b


def test_binary_prompt_has_full_context_and_clamps(monkeypatch):
    llm = FakeLlm()

    async def fake_structure(text, output_type, **kw):
        return BinaryPrediction(prediction_in_decimal=1.0)

    monkeypatch.setattr(bot_module, "structure_output", fake_structure)
    q = binary_question(fine_print="Only official data counts.", background_info="Some background.")
    result = asyncio.run(_bot(llm)._run_forecast_on_binary(q, "RESEARCH-TEXT"))
    prompt = llm.prompts[0]
    for part in ("Will thing 1 happen?", "Resolves Yes if thing happens.",
                 "Only official data counts.", "Some background.", "RESEARCH-TEXT"):
        assert part in prompt
    assert result.prediction_value == guards.BINARY_MAX


def test_numeric_path_builds_valid_cdf(monkeypatch):
    llm = FakeLlm()

    async def fake_structure(text, output_type, **kw):
        return [Percentile(percentile=p, value=v)
                for p, v in zip([0.1, 0.2, 0.4, 0.6, 0.8, 0.9], [5, 15, 30, 45, 60, 80])]

    monkeypatch.setattr(bot_module, "structure_output", fake_structure)
    q = numeric_question()
    result = asyncio.run(_bot(llm)._run_forecast_on_numeric(q, "research"))
    assert "The value cannot be lower than 0" in llm.prompts[0]
    assert "likely not higher than 100" in llm.prompts[0]
    guards.check_report(q, result.prediction_value, "x" * 200)


def test_build_llms_overrides_and_disables_library_researcher():
    llms = PrognozyBot.build_llms("openrouter/openai/gpt-5.4", None, None)
    assert llms["default"].model == "openrouter/openai/gpt-5.4"
    assert llms["researcher"] is None
