"""Ograniczenie liczby zapytań do modeli na minutę.

Nowe konta OpenRouter mają limit ok. 20 zapytań na minutę na model. Bot robi
5 prognoz na pytanie, każdą odczytuje tani model, więc bez ogranicznika łatwo
go przekroczyć. Ogranicznik działa osobno dla każdego modelu i obejmuje też
ponowienia biblioteki, bo siedzi w metodzie wywoływanej przy każdej próbie.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Callable

from forecasting_tools import GeneralLlm

WINDOW_SECONDS = 60.0
_DEFAULT_RPM = 15


class RpmLimiter:
    """Przesuwne okno: najwyżej `rpm` startów zapytań na 60 sekund."""

    def __init__(
        self,
        rpm: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], "asyncio.Future"] = asyncio.sleep,  # type: ignore[assignment]
    ) -> None:
        self.rpm = max(1, rpm)
        self._clock = clock
        self._sleep = sleep
        self._starts: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = self._clock()
                while self._starts and now - self._starts[0] >= WINDOW_SECONDS:
                    self._starts.popleft()
                if len(self._starts) < self.rpm:
                    self._starts.append(now)
                    return
                await self._sleep(WINDOW_SECONDS - (now - self._starts[0]) + 0.05)


_rpm = _DEFAULT_RPM
_limiters: dict[str, RpmLimiter] = {}


def configure(rpm: int) -> None:
    global _rpm
    _rpm = max(1, rpm)
    _limiters.clear()


def limiter_for(model: str) -> RpmLimiter:
    if model not in _limiters:
        _limiters[model] = RpmLimiter(_rpm)
    return _limiters[model]


class ThrottledLlm(GeneralLlm):
    """GeneralLlm, który przed każdą próbą czeka na wolne miejsce w limicie."""

    async def _mockable_direct_call_to_model(self, prompt):  # type: ignore[override]
        await limiter_for(self.model).acquire()
        return await super()._mockable_direct_call_to_model(prompt)


def throttled(llm: GeneralLlm | str | None) -> GeneralLlm | str | None:
    """Zamienia model (nazwę albo GeneralLlm) na wersję z ogranicznikiem."""
    if llm is None or isinstance(llm, ThrottledLlm):
        return llm
    if isinstance(llm, str):
        # Specjalne "modele" biblioteki (np. asknews/...) zostawiamy bez zmian.
        return llm if "/" not in llm or llm.startswith(("asknews/", "smart-searcher")) else ThrottledLlm(model=llm)
    kwargs = {k: v for k, v in dict(llm.litellm_kwargs).items() if k != "model"}
    return ThrottledLlm(
        model=llm.model,
        allowed_tries=getattr(llm, "allowed_tries", 3),
        **kwargs,
    )
