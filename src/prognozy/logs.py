"""Logowanie z maskowaniem kluczy.

Każdy rekord logu przechodzi przez filtr, który zastępuje wartości tajnych
zmiennych środowiskowych napisem ***. Dzięki temu klucz nie trafi do journald
nawet wtedy, gdy jakaś biblioteka wypisze go w komunikacie błędu.
"""

from __future__ import annotations

import logging
import os

from prognozy.config import SECRET_ENV_VARS

MASK = "***"
MAX_MESSAGE_CHARS = 1500  # błędy bibliotek potrafią mieć kilkadziesiąt tysięcy znaków
_MIN_SECRET_LEN = 6  # krótszych wartości nie maskujemy (np. "1"), żeby nie psuć logów


def _secret_values() -> list[str]:
    values = []
    for name in SECRET_ENV_VARS:
        value = os.getenv(name)
        if value and len(value.strip()) >= _MIN_SECRET_LEN:
            values.append(value.strip())
    # Najpierw dłuższe, żeby częściowe nakładanie się nie zostawiało fragmentów.
    return sorted(set(values), key=len, reverse=True)


def redact(text: str, secrets: list[str] | None = None) -> str:
    for secret in secrets if secrets is not None else _secret_values():
        text = text.replace(secret, MASK)
    return text


class SecretRedactingFilter(logging.Filter):
    def __init__(self) -> None:
        super().__init__()
        self._secrets = _secret_values()

    def filter(self, record: logging.LogRecord) -> bool:
        message = redact(record.getMessage(), self._secrets)
        if len(message) > MAX_MESSAGE_CHARS:
            message = message[:MAX_MESSAGE_CHARS] + f" … [ucięto {len(message) - MAX_MESSAGE_CHARS} znaków]"
        record.msg = message
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text, self._secrets)
        return True


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    handler.addFilter(SecretRedactingFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # Głośne biblioteki: wystarczą ostrzeżenia.
    for noisy in ("LiteLLM", "httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("forecasting_tools.ai_models.model_tracker").setLevel(
        logging.ERROR
    )
