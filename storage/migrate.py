"""SQLite schema migrations."""
from __future__ import annotations

import os
import sqlite3
from typing import Iterable

SCHEMA: Iterable[str] = [
    """
CREATE TABLE IF NOT EXISTS interview_flags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,
  interview_id TEXT NOT NULL,
  candidate_id TEXT NOT NULL,
  stage TEXT NOT NULL,
  question_id TEXT NOT NULL,
  action TEXT NOT NULL,
  severity TEXT NOT NULL,
  reason_codes TEXT NOT NULL,
  raw_text TEXT NOT NULL,
  safe_reply TEXT NOT NULL,
  skip_streak INTEGER,
  metadata TEXT
);
""",
    """
CREATE TABLE IF NOT EXISTS quick_actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,
  interview_id TEXT NOT NULL,
  candidate_id TEXT NOT NULL,
  stage TEXT NOT NULL,
  question_id TEXT NOT NULL,
  action_id TEXT NOT NULL,
  source TEXT NOT NULL,
  latency_ms INTEGER,
  metadata TEXT
);
""",
    """
CREATE TABLE IF NOT EXISTS scores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  interview_id TEXT NOT NULL,
  candidate_id TEXT NOT NULL,
  competency TEXT NOT NULL,
  item_id TEXT NOT NULL,
  best_of_score REAL NOT NULL,
  turn_scores_json TEXT NOT NULL
);
""",
    """
CREATE TABLE IF NOT EXISTS scores_summary (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,
  interview_id TEXT NOT NULL,
  candidate_id TEXT NOT NULL,
  competency TEXT NOT NULL,
  avg_score REAL NOT NULL,
  median_score REAL NOT NULL,
  max_score REAL NOT NULL,
  attempted_count INTEGER NOT NULL,
  skipped_count INTEGER NOT NULL
);
""",
    """
CREATE TABLE IF NOT EXISTS scores_overall (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,
  interview_id TEXT NOT NULL,
  candidate_id TEXT NOT NULL,
  avg_score REAL NOT NULL,
  median_score REAL NOT NULL,
  max_score REAL NOT NULL
);
""",
]


def migrate(db_path: str = "data/interview.db") -> None:
    """Apply schema migrations to the SQLite database."""

    directory = os.path.dirname(db_path) or "."
    os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        for stmt in SCHEMA:
            cur.execute(stmt)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
