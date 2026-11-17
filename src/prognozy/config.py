"""Ustawienia bota. Wszystko pochodzi ze zmiennych środowiskowych.

Klucze (METACULUS_TOKEN, OPENROUTER_API_KEY, ASKNEWS_* itd.) czyta bezpośrednio
biblioteka forecasting-tools. Tutaj są tylko ustawienia samego bota oraz
sprawdzenie, czy wymagane klucze w ogóle istnieją. Wartości kluczy nigdy nie
są logowane.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Zmienne, których wartości traktujemy jako tajne (maskowane w logach).
SECRET_ENV_VARS = (
    "METACULUS_TOKEN",
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "ASKNEWS_CLIENT_ID",
    "ASKNEWS_SECRET",
    "ASKNEWS_API_KEY",
    "PERPLEXITY_API_KEY",
    "EXA_API_KEY",
    "PROGNOZY_HEALTHCHECK_URL",  # kto zna adres, może fałszować pingi
)

LLM_KEY_VARS = ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")

_PLACEHOLDERS = {"", "REPLACE_ME", "changeme", "xxx"}


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "tak", "on"}


def _env_int(name: str, default: int) -> int:
    value = _env(name)
    return default if value is None else int(value)


def has_real_value(name: str) -> bool:
    value = os.getenv(name)
    return value is not None and value.strip() not in _PLACEHOLDERS


@dataclass(frozen=True)
class Settings:
    # Czy wysyłać prognozy. Domyślnie NIE: wysyłanie trzeba włączyć świadomie.
    publish: bool = False
    state_dir: Path = Path("./stan")
    # Ile prognoz uśredniamy (mediana) na pytanie.
    predictions_per_question: int = 5
    # Minimalna długość zebranego researchu; krótszy = brak informacji = pomijamy pytanie.
    min_research_chars: int = 200
    # Nadpisania modeli (puste = domyślne z forecasting-tools, dobrane do kluczy).
    model_default: str | None = None
    model_parser: str | None = None
    model_summarizer: str | None = None
    # Lista modeli wyszukujących (przez OpenRouter/OpenAI), oddzielona przecinkami.
    search_models: tuple[str, ...] = field(default_factory=tuple)
    # Kilka modeli do końcowej prognozy: prognozy rozkładają się po kolei na modele.
    # Pusta lista = jeden model (model_default albo domyślny z biblioteki).
    forecast_models: tuple[str, ...] = field(default_factory=tuple)
    # Notowania Polymarket/Manifold jako dodatkowe źródło.
    markets: bool = True
    # Adres pingu healthchecks.io (pusty = bez powiadomień).
    healthcheck_url: str | None = None
    # Dzienny limit wydatków na OpenRouter w $ (pusty = bez limitu w bocie).
    daily_budget_usd: float | None = None
    # Ile pytań między kolejnymi sprawdzeniami budżetu.
    batch_size: int = 5
    # Najwyżej tyle zapytań na minutę do jednego modelu (nowe konta OpenRouter: limit 20).
    llm_rpm: int = 15
    # Ile pytań prognozować naraz.
    parallel_questions: int = 1
    # Prompt caching dla modeli Claude (taniej przy kilku prognozach na pytanie).
    prompt_cache: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        search = _env("PROGNOZY_SEARCH_MODELS")
        budget = _env("PROGNOZY_DAILY_BUDGET_USD")
        return cls(
            forecast_models=_csv(_env("PROGNOZY_FORECAST_MODELS")),
            markets=_env_bool("PROGNOZY_MARKETS", True),
            healthcheck_url=_env("PROGNOZY_HEALTHCHECK_URL"),
            daily_budget_usd=float(budget) if budget else None,
            batch_size=_env_int("PROGNOZY_BATCH_SIZE", 5),
            llm_rpm=_env_int("PROGNOZY_LLM_RPM", 15),
            parallel_questions=_env_int("PROGNOZY_PARALLEL_QUESTIONS", 1),
            prompt_cache=_env_bool("PROGNOZY_PROMPT_CACHE", True),
            publish=_env_bool("PROGNOZY_PUBLISH", False),
            state_dir=Path(_env("PROGNOZY_STATE_DIR", "./stan")),
            predictions_per_question=_env_int("PROGNOZY_PREDICTIONS", 5),
            min_research_chars=_env_int("PROGNOZY_MIN_RESEARCH_CHARS", 200),
            model_default=_env("PROGNOZY_MODEL_DEFAULT"),
            model_parser=_env("PROGNOZY_MODEL_PARSER"),
            model_summarizer=_env("PROGNOZY_MODEL_SUMMARIZER"),
            search_models=_csv(search),
        )


def _csv(value: str | None) -> tuple[str, ...]:
    return tuple(s.strip() for s in (value or "").split(",") if s.strip())


def missing_requirements() -> list[str]:
    """Zwraca listę braków w konfiguracji (pusta = wszystko jest)."""
    problems: list[str] = []
    if not has_real_value("METACULUS_TOKEN"):
        problems.append("Brak METACULUS_TOKEN (token konta bota na Metaculus).")
    if not any(has_real_value(k) for k in LLM_KEY_VARS):
        problems.append(
            "Brak klucza do modelu AI: ustaw OPENROUTER_API_KEY "
            "(kredyty od Metaculus) albo OPENAI_API_KEY / ANTHROPIC_API_KEY."
        )
    return problems
