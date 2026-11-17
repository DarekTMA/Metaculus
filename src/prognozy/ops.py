"""Sprawy operacyjne: powiadomienia o awarii i dzienny limit wydatków.

Powiadomienia: bot pinguje healthchecks.io (albo zgodny serwis) na starcie,
po sukcesie i po błędzie. Gdy pingi ustaną albo przyjdzie błąd, serwis
wysyła mail. Adres pingu jest w PROGNOZY_HEALTHCHECK_URL.

Limit wydatków: przed każdą porcją pytań bot pyta OpenRouter, ile kosztowało
dziś użycie klucza. Po przekroczeniu PROGNOZY_DAILY_BUDGET_USD kończy
przejście (pytania wrócą jutro). Biblioteka forecasting-tools nie zna cen
wszystkich nowych modeli, dlatego liczymy na podstawie danych samego OpenRouter.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

import requests

logger = logging.getLogger(__name__)

OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"
TIMEOUT = 15


class Healthcheck:
    def __init__(self, url: str | None, post: Callable[..., Any] | None = None) -> None:
        self._url = url.rstrip("/") if url else None
        self._post = post or requests.post

    def _ping(self, suffix: str, body: str = "") -> None:
        if not self._url:
            return
        try:
            self._post(self._url + suffix, data=body.encode()[:10_000], timeout=TIMEOUT)
        except Exception as exc:  # noqa: BLE001  (ping nie może zatrzymać bota)
            logger.warning("Ping healthcheck nie przeszedł: %s", exc)

    def start(self) -> None:
        self._ping("/start")

    def success(self, body: str = "") -> None:
        self._ping("", body)

    def fail(self, body: str = "") -> None:
        self._ping("/fail", body)


class BudgetExceeded(RuntimeError):
    pass


class DailyBudget:
    """Sprawdza dzisiejsze wydatki klucza OpenRouter."""

    def __init__(
        self,
        limit_usd: float | None,
        get: Callable[..., Any] | None = None,
        api_key: str | None = None,
    ) -> None:
        self._limit = limit_usd
        self._get = get or requests.get
        self._api_key = api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY")

    @property
    def enabled(self) -> bool:
        return self._limit is not None and bool(self._api_key)

    def spent_today(self) -> float | None:
        try:
            response = self._get(
                OPENROUTER_KEY_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            data = response.json().get("data", {})
            value = data.get("usage_daily")
            return float(value) if value is not None else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Nie udało się odczytać wydatków z OpenRouter: %s", exc)
            return None

    def check(self) -> None:
        """Rzuca BudgetExceeded, gdy dzisiejszy limit jest wyczerpany."""
        if not self.enabled:
            return
        spent = self.spent_today()
        if spent is None:
            # Nie zatrzymujemy bota z powodu chwilowej awarii odczytu;
            # twardy limit i tak warto ustawić na samym kluczu w OpenRouter.
            return
        if spent >= self._limit:  # type: ignore[operator]
            raise BudgetExceeded(
                f"Dzisiejsze wydatki {spent:.2f} $ osiągnęły limit {self._limit:.2f} $."
            )
        logger.info("Wydatki dziś: %.2f $ z %.2f $.", spent, self._limit)
