"""Bot prognozujący zbudowany na ForecastBot z biblioteki forecasting-tools.

Przebieg dla jednego pytania (sterowany przez ForecastBot):
1. ``run_research``: kilka źródeł naraz (patrz research.py); brak informacji
   oznacza pominięcie pytania.
2. N niezależnych prognoz (domyślnie 5), jednym modelem albo po kolei
   kilkoma (PROGNOZY_FORECAST_MODELS).
3. Mediana prognoz (agregacja z biblioteki). Bez sztucznego przesuwania do
   skrajności.

Prompty są po angielsku, bo w tym języku są pytania i modele radzą sobie
z nimi najlepiej.
"""

from __future__ import annotations

import asyncio
import hashlib
import itertools
import logging
from datetime import datetime, timezone

from forecasting_tools import (
    BinaryPrediction,
    BinaryQuestion,
    DatePercentile,
    DateQuestion,
    ForecastBot,
    GeneralLlm,
    MetaculusQuestion,
    MultipleChoiceQuestion,
    NumericDistribution,
    NumericQuestion,
    Percentile,
    PredictedOptionList,
    ReasonedPrediction,
    clean_indents,
    structure_output,
)

from prognozy.guards import BINARY_MAX, BINARY_MIN
from prognozy.research import Researcher
from prognozy.throttle import ThrottledLlm, throttled

logger = logging.getLogger(__name__)

_COMMON_GUIDANCE = """
Forecasting guidance:
- Read the resolution criteria and fine print carefully. Only what they say counts.
- Start from the status quo and base rates; the world usually changes slowly.
- If the research mentions prediction-market prices or similar questions, weigh them.
- Be calibrated. Do not push your forecast towards extremes without strong evidence.
"""

_UNRESOLVED_NOTE = (
    "- If the text treats the question as already resolved in the past instead of "
    "giving a forecast, do NOT return a parsed output; say the answer is not given.\n"
)


def _supports_prompt_cache(model: str) -> bool:
    # Znacznik cache_control rozumieją modele Claude (bezpośrednio i przez OpenRouter).
    return "claude" in model.lower()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _question_block(question: MetaculusQuestion, research: str) -> str:
    return clean_indents(
        f"""
        Question:
        {question.question_text}

        Background:
        {question.background_info}

        Resolution criteria (not yet satisfied):
        {question.resolution_criteria}

        Fine print:
        {question.fine_print}

        Research from your assistants:
        {research}

        Today is {_today()}.
        """
    )


class PrognozyBot(ForecastBot):
    _max_concurrent_questions = 2
    _structure_output_validation_samples = 2

    def __init__(
        self,
        *,
        researcher: Researcher,
        forecast_models: tuple[str, ...] = (),
        parallel_questions: int = 1,
        prompt_cache: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._researcher = researcher
        self._limiter = asyncio.Semaphore(self._max_concurrent_questions)
        # Ile pytań naraz. 1 = najbezpieczniej przy limitach zapytań nowych kont.
        self._question_limiter = asyncio.Semaphore(max(1, parallel_questions))
        # Uśrednianie kilku modeli: kolejne prognozy idą po kolei do kolejnych modeli.
        self._forecasters = [
            ThrottledLlm(model=m, temperature=0.3, timeout=180, allowed_tries=3)
            for m in forecast_models
        ]
        self._next_forecaster = itertools.count()
        # Prompt caching: ten sam długi prompt idzie do modelu 5 razy. Pierwsze
        # wywołanie zapisuje go w pamięci podręcznej dostawcy, kolejne płacą
        # za tę część ok. 10% ceny. Pozostałe czekają, aż pierwsze się skończy,
        # bo równoległe zapytania nie trafiłyby w świeży wpis.
        self._prompt_cache = prompt_cache
        self._cache_warmups: dict[tuple[str, str], asyncio.Event] = {}

    async def _run_individual_question(self, question):  # type: ignore[override]
        async with self._question_limiter:
            return await super()._run_individual_question(question)

    def _forecaster(self) -> GeneralLlm:
        if not self._forecasters:
            return self.get_llm("default", "llm")
        return self._forecasters[next(self._next_forecaster) % len(self._forecasters)]

    async def _invoke_with_cache(self, llm: GeneralLlm, prompt: str) -> str:
        key = (llm.model, hashlib.sha256(prompt.encode()).hexdigest())
        warmup = self._cache_warmups.get(key)
        first = warmup is None
        if first:
            warmup = self._cache_warmups[key] = asyncio.Event()
        else:
            await warmup.wait()
        message = [{"role": "user", "content": prompt, "cache_control": {"type": "ephemeral"}}]
        try:
            return await llm.invoke(message)  # type: ignore[arg-type]
        finally:
            if first:
                warmup.set()

    async def _reason(self, prompt: str) -> str:
        """Jedno rozumowanie modelu. Nazwa modelu trafia do komentarza."""
        llm = self._forecaster()
        if self._prompt_cache and _supports_prompt_cache(llm.model):
            reasoning = await self._invoke_with_cache(llm, prompt)
        else:
            reasoning = await llm.invoke(prompt)
        return f"(model: {llm.model})\n\n{reasoning}"

    @staticmethod
    def build_llms(
        default: str | None, parser: str | None, summarizer: str | None
    ) -> dict[str, str | GeneralLlm | None] | None:
        """Nadpisania modeli z konfiguracji; None = domyślne z biblioteki."""
        llms: dict[str, str | GeneralLlm | None] = dict(
            ForecastBot._llm_config_defaults()
        )
        if default:
            llms["default"] = GeneralLlm(model=default, temperature=0.3, timeout=180)
        if parser:
            llms["parser"] = GeneralLlm(model=parser, temperature=0.0)
        if summarizer:
            llms["summarizer"] = GeneralLlm(model=summarizer, temperature=0.3)
        # Wyszukiwanie robi nasz Researcher, nie domyślny "researcher" biblioteki.
        llms["researcher"] = None
        # Każdy model z ogranicznikiem zapytań na minutę.
        return {purpose: throttled(llm) for purpose, llm in llms.items()}

    # ------------------------------------------------------------- RESEARCH

    async def run_research(self, question: MetaculusQuestion) -> str:
        async with self._limiter:
            research = await self._researcher.run(question)
            logger.info("Research gotowy dla %s (%d znaków)", question.page_url, len(research))
            return research

    # ------------------------------------------------------------- BINARY

    async def _run_forecast_on_binary(
        self, question: BinaryQuestion, research: str
    ) -> ReasonedPrediction[float]:
        prompt = clean_indents(
            f"""
            You are a professional forecaster.

            {_question_block(question, research)}
            {_COMMON_GUIDANCE}
            Before answering, write:
            (a) How much time is left until the outcome is known.
            (b) The status quo outcome if nothing changed.
            (c) A short scenario that leads to No.
            (d) A short scenario that leads to Yes.

            The last thing you write is your final answer as: "Probability: ZZ%", 0-100
            """
        )
        reasoning = await self._reason(prompt)
        parsed: BinaryPrediction = await structure_output(
            reasoning,
            BinaryPrediction,
            model=self.get_llm("parser", "llm"),
            num_validation_samples=self._structure_output_validation_samples,
            additional_instructions=(
                "The text gives a probability forecast for a binary question.\n"
                + _UNRESOLVED_NOTE
            ),
        )
        value = max(BINARY_MIN, min(BINARY_MAX, parsed.prediction_in_decimal))
        return ReasonedPrediction(prediction_value=value, reasoning=reasoning)

    # ------------------------------------------------------------- MULTIPLE CHOICE

    async def _run_forecast_on_multiple_choice(
        self, question: MultipleChoiceQuestion, research: str
    ) -> ReasonedPrediction[PredictedOptionList]:
        prompt = clean_indents(
            f"""
            You are a professional forecaster.

            {_question_block(question, research)}
            The options are: {question.options}
            {_COMMON_GUIDANCE}
            - Leave some probability on every option to allow for surprises.

            Before answering, write:
            (a) How much time is left until the outcome is known.
            (b) The status quo outcome if nothing changed.
            (c) A scenario that leads to an unexpected outcome.

            The last thing you write is your probabilities for the options,
            in this order {question.options}, as:
            Option_A: Probability_A
            Option_B: Probability_B
            ...
            """
        )
        reasoning = await self._reason(prompt)
        parsed: PredictedOptionList = await structure_output(
            text_to_structure=reasoning,
            output_type=PredictedOptionList,
            model=self.get_llm("parser", "llm"),
            num_validation_samples=self._structure_output_validation_samples,
            additional_instructions=clean_indents(
                f"""
                Option names must be exactly these: {question.options}
                Remove any "Option" prefix that is not part of the names.
                Include options with 0% instead of skipping them.
                {_UNRESOLVED_NOTE}
                """
            ),
        )
        return ReasonedPrediction(prediction_value=parsed, reasoning=reasoning)

    # ------------------------------------------------------------- NUMERIC / DATE

    @staticmethod
    def _bound_messages(question: NumericQuestion | DateQuestion) -> str:
        if isinstance(question, DateQuestion):
            upper = question.upper_bound.date().isoformat()
            lower = question.lower_bound.date().isoformat()
            unit = ""
        else:
            upper = (
                question.nominal_upper_bound
                if question.nominal_upper_bound is not None
                else question.upper_bound
            )
            lower = (
                question.nominal_lower_bound
                if question.nominal_lower_bound is not None
                else question.lower_bound
            )
            unit = question.unit_of_measure or ""
        up = (
            f"The question creator thinks the value is likely not higher than {upper} {unit}."
            if question.open_upper_bound
            else f"The value cannot be higher than {upper} {unit}."
        )
        low = (
            f"The question creator thinks the value is likely not lower than {lower} {unit}."
            if question.open_lower_bound
            else f"The value cannot be lower than {lower} {unit}."
        )
        return f"{low}\n{up}"

    @staticmethod
    def _single_distribution_note(question: NumericQuestion | DateQuestion) -> str:
        note = (
            "- Return exactly ONE distribution: the final one answering the question. "
            "Never merge percentile lists for different entities or scenarios.\n"
        )
        if question.group_question_option is not None:
            note += (
                f'- This question is only about "{question.group_question_option}". '
                "Ignore distributions for other subjects.\n"
            )
        return note

    _PERCENTILE_STEPS = """
    Before answering, write:
    (a) How much time is left until the outcome is known.
    (b) The outcome if nothing changed.
    (c) The outcome if the current trend continued.
    (d) What experts and markets expect.
    (e) An unexpected scenario with a low outcome.
    (f) An unexpected scenario with a high outcome.

    Good forecasters are humble and set wide 90/10 intervals for unknown unknowns.
    """

    async def _run_forecast_on_numeric(
        self, question: NumericQuestion, research: str
    ) -> ReasonedPrediction[NumericDistribution]:
        unit = question.unit_of_measure or "not stated (infer it)"
        prompt = clean_indents(
            f"""
            You are a professional forecaster.

            {_question_block(question, research)}
            Units for the answer: {unit}
            {self._bound_messages(question)}
            {_COMMON_GUIDANCE}
            Formatting: use the requested units, never scientific notation,
            and percentiles must increase (P10 < P20 < ... < P90).
            {self._PERCENTILE_STEPS}
            The last thing you write is your final answer as:
            Percentile 10: XX
            Percentile 20: XX
            Percentile 40: XX
            Percentile 60: XX
            Percentile 80: XX
            Percentile 90: XX
            """
        )
        reasoning = await self._reason(prompt)
        percentiles: list[Percentile] = await structure_output(
            reasoning,
            list[Percentile],
            model=self.get_llm("parser", "llm"),
            num_validation_samples=self._structure_output_validation_samples,
            additional_instructions=clean_indents(
                f"""
                The text gives a percentile forecast for: "{question.question_text}".
                {self._single_distribution_note(question)}
                - Give values in these units: {question.unit_of_measure}. Convert if the
                  text uses other units (e.g. $500,000,000 with unit "B $" is 0.5).
                - Convert scientific notation to plain numbers.
                - If only a single value is given (no percentiles), do not return a parsed output.
                {_UNRESOLVED_NOTE}
                """
            ),
        )
        prediction = NumericDistribution.from_question(percentiles, question)
        return ReasonedPrediction(prediction_value=prediction, reasoning=reasoning)

    async def _run_forecast_on_date(
        self, question: DateQuestion, research: str
    ) -> ReasonedPrediction[NumericDistribution]:
        prompt = clean_indents(
            f"""
            You are a professional forecaster.

            {_question_block(question, research)}
            {self._bound_messages(question)}
            {_COMMON_GUIDANCE}
            Formatting: dates as YYYY-MM-DD (add THH:MM:SSZ in UTC only if hours matter),
            in chronological order from P10 (earliest) to P90 (latest).
            {self._PERCENTILE_STEPS}
            The last thing you write is your final answer as:
            Percentile 10: YYYY-MM-DD
            Percentile 20: YYYY-MM-DD
            Percentile 40: YYYY-MM-DD
            Percentile 60: YYYY-MM-DD
            Percentile 80: YYYY-MM-DD
            Percentile 90: YYYY-MM-DD
            """
        )
        reasoning = await self._reason(prompt)
        date_percentiles: list[DatePercentile] = await structure_output(
            reasoning,
            list[DatePercentile],
            model=self.get_llm("parser", "llm"),
            num_validation_samples=self._structure_output_validation_samples,
            additional_instructions=clean_indents(
                f"""
                The text gives a date forecast for: "{question.question_text}".
                {self._single_distribution_note(question)}
                - Return datetimes; assume midnight UTC if no hour is given.
                - If only a single date is given (no percentiles), do not return a parsed output.
                {_UNRESOLVED_NOTE}
                """
            ),
        )
        percentiles = [
            Percentile(percentile=p.percentile, value=p.value.timestamp())
            for p in date_percentiles
        ]
        prediction = NumericDistribution.from_question(percentiles, question)
        return ReasonedPrediction(prediction_value=prediction, reasoning=reasoning)
