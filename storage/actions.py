"""Persistence helpers for quick actions."""
from __future__ import annotations

import datetime as dt
import json
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from .sqlite import get_conn


class QuickActionPayload(BaseModel):
    interview_id: str
    candidate_id: str
    stage: str
    question_id: str
    action_id: str
    source: str
    latency_ms: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


def insert_quick_action(**data: Any) -> int:
    """Insert a quick action row and return its primary key."""

    payload = QuickActionPayload(**data)
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO quick_actions
               (timestamp, interview_id, candidate_id, stage, question_id,
                action_id, source, latency_ms, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                timestamp,
                payload.interview_id,
                payload.candidate_id,
                payload.stage,
                payload.question_id,
                payload.action_id,
                payload.source,
                payload.latency_ms,
                json.dumps(payload.metadata),
            ),
        )
        return int(cur.lastrowid)
