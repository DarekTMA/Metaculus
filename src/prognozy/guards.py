"""Bezpieczniki sprawdzane tuż przed wysłaniem prognozy.

Jeśli którykolwiek warunek nie jest spełniony, prognoza nie zostaje wysłana.
Lepiej pominąć pytanie niż wysłać coś błędnego.
"""

from __future__ import annotations

import math

from forecasting_tools import (
    BinaryQuestion,
    DateQuestion,
    MultipleChoiceQuestion,
    NumericDistribution,
    NumericQuestion,
    PredictedOptionList,
)

BINARY_MIN = 0.01
BINARY_MAX = 0.99
MIN_COMMENT_CHARS = 100
# Metaculus wymaga, by CDF rosła o co najmniej ok. 5e-5 na krok (dla 201 punktów).
# Sprawdzamy z małym marginesem na zaokrąglenia.
CDF_MIN_STEP = 1e-5
CDF_OPEN_BOUND_MIN = 0.001
CDF_TOLERANCE = 1e-6

SUPPORTED_QUESTION_TYPES = (
    BinaryQuestion,
    MultipleChoiceQuestion,
    NumericQuestion,  # obejmuje też DiscreteQuestion
    DateQuestion,
)


class GuardError(ValueError):
    """Prognoza nie przeszła kontroli i nie może zostać wysłana."""


def is_supported(question: object) -> bool:
    return isinstance(question, SUPPORTED_QUESTION_TYPES)


def check_comment(comment: str | None) -> None:
    if comment is None or len(comment.strip()) < MIN_COMMENT_CHARS:
        raise GuardError("Brak komentarza z uzasadnieniem (albo jest za krótki).")


def check_binary(probability: float) -> None:
    if not isinstance(probability, (int, float)) or math.isnan(probability):
        raise GuardError(f"Prognoza binarna nie jest liczbą: {probability!r}")
    if not BINARY_MIN <= probability <= BINARY_MAX:
        raise GuardError(
            f"Prognoza binarna {probability} poza zakresem {BINARY_MIN}–{BINARY_MAX}."
        )


def check_multiple_choice(
    prediction: PredictedOptionList, question: MultipleChoiceQuestion
) -> None:
    names = [o.option_name for o in prediction.predicted_options]
    if sorted(names) != sorted(question.options):
        raise GuardError(
            f"Opcje prognozy {names} nie zgadzają się z opcjami pytania {question.options}."
        )
    probs = [o.probability for o in prediction.predicted_options]
    if any(math.isnan(p) or p <= 0 or p >= 1 for p in probs):
        raise GuardError(f"Prawdopodobieństwa opcji poza (0, 1): {probs}")
    if abs(sum(probs) - 1.0) > 0.01:
        raise GuardError(f"Prawdopodobieństwa opcji nie sumują się do 1: {sum(probs)}")


def check_cdf(
    cdf: list[float],
    *,
    expected_size: int,
    open_lower_bound: bool,
    open_upper_bound: bool,
) -> None:
    if len(cdf) != expected_size:
        raise GuardError(f"CDF ma {len(cdf)} punktów, oczekiwano {expected_size}.")
    if any(math.isnan(v) for v in cdf):
        raise GuardError("CDF zawiera NaN.")
    if cdf[0] < -CDF_TOLERANCE or cdf[-1] > 1 + CDF_TOLERANCE:
        raise GuardError("CDF wychodzi poza zakres 0–1.")
    for a, b in zip(cdf, cdf[1:]):
        if b - a < CDF_MIN_STEP:
            raise GuardError("CDF nie jest ściśle rosnąca (monotoniczna).")
    if open_lower_bound:
        if cdf[0] < CDF_OPEN_BOUND_MIN - CDF_TOLERANCE:
            raise GuardError("Otwarta dolna granica: CDF[0] musi być ≥ 0.001.")
    elif abs(cdf[0]) > CDF_TOLERANCE:
        raise GuardError("Zamknięta dolna granica: CDF[0] musi być 0.")
    if open_upper_bound:
        if cdf[-1] > 1 - CDF_OPEN_BOUND_MIN + CDF_TOLERANCE:
            raise GuardError("Otwarta górna granica: CDF[-1] musi być ≤ 0.999.")
    elif abs(cdf[-1] - 1) > CDF_TOLERANCE:
        raise GuardError("Zamknięta górna granica: CDF[-1] musi być 1.")


def check_numeric(
    prediction: NumericDistribution, question: NumericQuestion | DateQuestion
) -> None:
    cdf = [p.percentile for p in prediction.get_cdf()]
    check_cdf(
        cdf,
        expected_size=getattr(question, "cdf_size", None) or 201,
        open_lower_bound=question.open_lower_bound,
        open_upper_bound=question.open_upper_bound,
    )


def check_report(question: object, prediction: object, comment: str | None) -> None:
    """Sprawdza całą prognozę. Rzuca GuardError, jeśli nie wolno jej wysłać."""
    check_comment(comment)
    if isinstance(question, BinaryQuestion):
        check_binary(prediction)  # type: ignore[arg-type]
    elif isinstance(question, MultipleChoiceQuestion):
        if not isinstance(prediction, PredictedOptionList):
            raise GuardError("Zły typ prognozy dla pytania wielokrotnego wyboru.")
        check_multiple_choice(prediction, question)
    elif isinstance(question, (NumericQuestion, DateQuestion)):
        if not isinstance(prediction, NumericDistribution):
            raise GuardError("Zły typ prognozy dla pytania liczbowego/daty.")
        check_numeric(prediction, question)
    else:
        raise GuardError(f"Nieobsługiwany typ pytania: {type(question).__name__}")
