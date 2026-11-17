"""Lokalny rejestr wysłanych prognoz (SQLite w katalogu stanu).

Chroni przed dublami: jeśli usługa uruchomi się ponownie albo Metaculus
z opóźnieniem pokaże, że prognoza już jest, bot nie wyśle jej drugi raz.

Stany wpisu:
- ``prediction_posted``: prognoza wysłana, komentarz jeszcze nie
  (np. sieć padła w połowie). Następne uruchomienie dośle sam komentarz.
- ``done``: prognoza i komentarz wysłane.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PREDICTION_POSTED = "prediction_posted"
DONE = "done"


@dataclass(frozen=True)
class Entry:
    question_id: int
    post_id: int
    status: str
    comment: str
    updated_at: str


class Ledger:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        with closing(self._connect()) as db, db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS forecasts (
                    question_id INTEGER PRIMARY KEY,
                    post_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    comment TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def get(self, question_id: int) -> Entry | None:
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT question_id, post_id, status, comment, updated_at "
                "FROM forecasts WHERE question_id = ?",
                (question_id,),
            ).fetchone()
        return Entry(*row) if row else None

    def is_done(self, question_id: int) -> bool:
        entry = self.get(question_id)
        return entry is not None and entry.status == DONE

    def has_any(self, question_id: int) -> bool:
        return self.get(question_id) is not None

    def mark(self, question_id: int, post_id: int, status: str, comment: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as db, db:
            db.execute(
                """
                INSERT INTO forecasts (question_id, post_id, status, comment, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(question_id) DO UPDATE SET
                    post_id = excluded.post_id,
                    status = excluded.status,
                    comment = excluded.comment,
                    updated_at = excluded.updated_at
                """,
                (question_id, post_id, status, comment, now),
            )

    def pending_comments(self) -> list[Entry]:
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT question_id, post_id, status, comment, updated_at "
                "FROM forecasts WHERE status = ?",
                (PREDICTION_POSTED,),
            ).fetchall()
        return [Entry(*row) for row in rows]
