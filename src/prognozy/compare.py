"""Porównanie wariantów bota bez łamania zasad konkursu.

Bot prognozuje (bez wysyłania) na otwartych pytaniach binarnych Metaculus
spoza turniejów botów. Wynik porównujemy z prognozą społeczności (CP), która
jest bardzo dobrym punktem odniesienia. Miara: oczekiwany "baseline score"
przy założeniu, że CP to prawdziwe prawdopodobieństwo. Najlepszy możliwy
wynik ma wariant, który trafia dokładnie w CP.

Dlaczego tak, a nie na pytaniach rozstrzygniętych: przy rozstrzygniętych
wyszukiwarka zwykle znajduje odpowiedź, więc wynik byłby zawyżony.
Dlaczego nie na pytaniach turniejowych: zasady zabraniają poprawiania bota
na podstawie jego prognoz na otwartych pytaniach turnieju.
"""

from __future__ import annotations

import json
import logging
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from forecasting_tools import BinaryQuestion, ForecastBot, MetaculusQuestion

logger = logging.getLogger(__name__)

_EPS = 1e-6


def expected_baseline_score(p: float, cp: float) -> float:
    """Oczekiwany baseline score Metaculus (log2), gdy prawdą jest cp."""
    p = min(max(p, _EPS), 1 - _EPS)
    return 100 * (cp * (math.log2(p) + 1) + (1 - cp) * (math.log2(1 - p) + 1))


@dataclass(frozen=True)
class Row:
    variant: str
    question_id: int | None
    url: str
    bot: float | None
    community: float
    score: float | None
    error: str | None = None


def exclude_tournament_questions(
    questions: Iterable[MetaculusQuestion], forbidden: Iterable[int | str]
) -> list[BinaryQuestion]:
    forbidden_str = {str(f) for f in forbidden}
    kept = []
    for q in questions:
        if not isinstance(q, BinaryQuestion) or q.community_prediction_at_access_time is None:
            continue
        if forbidden_str & {str(s) for s in q.tournament_slugs}:
            continue
        kept.append(q)
    return kept


async def run_comparison(
    questions: list[BinaryQuestion],
    variants: dict[str, ForecastBot],
) -> list[Row]:
    rows: list[Row] = []
    for name, bot in variants.items():
        results = await bot.forecast_questions(questions, return_exceptions=True)
        for q, result in zip(questions, results):
            cp = float(q.community_prediction_at_access_time)  # type: ignore[arg-type]
            if isinstance(result, BaseException):
                rows.append(Row(name, q.id_of_question, q.page_url, None, cp, None,
                                type(result).__name__))
                continue
            p = float(result.prediction)
            rows.append(Row(name, q.id_of_question, q.page_url, p, cp,
                            expected_baseline_score(p, cp)))
    return rows


def summarize(rows: list[Row]) -> str:
    lines = [
        "Wariant | pytania | śr. wynik (więcej = lepiej) | wynik CP | śr. |bot−CP| | błędy",
        "---|---|---|---|---|---",
    ]
    for variant in dict.fromkeys(r.variant for r in rows):
        ok = [r for r in rows if r.variant == variant and r.score is not None]
        errors = sum(1 for r in rows if r.variant == variant and r.score is None)
        if not ok:
            lines.append(f"{variant} | 0 | – | – | – | {errors}")
            continue
        mean_score = statistics.mean(r.score for r in ok)  # type: ignore[misc]
        best = statistics.mean(expected_baseline_score(r.community, r.community) for r in ok)
        gap = statistics.mean(abs(r.bot - r.community) for r in ok)  # type: ignore[operator]
        lines.append(
            f"{variant} | {len(ok)} | {mean_score:.1f} | {best:.1f} | {gap:.3f} | {errors}"
        )
    lines.append("")
    lines.append(
        "Wynik CP to sufit (bot trafiający dokładnie w prognozę społeczności). "
        "Różnice poniżej ~2 punktów przy 30 pytaniach to zwykle szum."
    )
    return "\n".join(lines)


def save_rows(rows: list[Row], directory: Path, now: Callable[[], datetime] | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = (now or (lambda: datetime.now(timezone.utc)))().strftime("%Y%m%d-%H%M%S")
    path = directory / f"porownanie-{stamp}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
    return path
