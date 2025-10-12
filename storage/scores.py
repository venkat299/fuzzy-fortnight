"""Persistence helpers for score tracking."""
from __future__ import annotations

import datetime as dt
import json
from typing import Any, Dict

from pydantic import BaseModel, Field

from .sqlite import get_conn


class ScorePayload(BaseModel):
    interview_id: str
    candidate_id: str
    competency: str
    item_id: str
    best_of_score: float
    turn_scores_json: Dict[str, Any] = Field(default_factory=dict)


class ScoresSummaryPayload(BaseModel):
    interview_id: str
    candidate_id: str
    competency: str
    avg_score: float
    median_score: float
    max_score: float
    attempted_count: int
    skipped_count: int


class ScoresOverallPayload(BaseModel):
    interview_id: str
    candidate_id: str
    avg_score: float
    median_score: float
    max_score: float


def insert_score(**data: Any) -> int:
    """Insert a per-item score record."""

    payload = ScorePayload(**data)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO scores
               (interview_id, candidate_id, competency, item_id, best_of_score, turn_scores_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                payload.interview_id,
                payload.candidate_id,
                payload.competency,
                payload.item_id,
                payload.best_of_score,
                json.dumps(payload.turn_scores_json),
            ),
        )
        return int(cur.lastrowid)


def insert_scores_summary(**data: Any) -> int:
    """Insert a per-competency summary row."""

    payload = ScoresSummaryPayload(**data)
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO scores_summary
               (timestamp, interview_id, candidate_id, competency, avg_score, median_score, max_score,
                attempted_count, skipped_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                timestamp,
                payload.interview_id,
                payload.candidate_id,
                payload.competency,
                payload.avg_score,
                payload.median_score,
                payload.max_score,
                payload.attempted_count,
                payload.skipped_count,
            ),
        )
        return int(cur.lastrowid)


def insert_scores_overall(**data: Any) -> int:
    """Insert an interview-level summary row."""

    payload = ScoresOverallPayload(**data)
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO scores_overall
               (timestamp, interview_id, candidate_id, avg_score, median_score, max_score)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                timestamp,
                payload.interview_id,
                payload.candidate_id,
                payload.avg_score,
                payload.median_score,
                payload.max_score,
            ),
        )
        return int(cur.lastrowid)
