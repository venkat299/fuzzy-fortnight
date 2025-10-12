"""SQLite helpers for the persistence layer."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from config.settings import settings


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection, ensuring the data directory exists."""

    directory = os.path.dirname(settings.DB_PATH) or "."
    os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(settings.DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
