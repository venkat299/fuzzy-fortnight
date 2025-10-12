"""Persistence helpers for interview flags."""
from __future__ import annotations

import datetime as dt
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .sqlite import get_conn


class InterviewFlagPayload(BaseModel):
    interview_id: str
    candidate_id: str
    stage: str
    question_id: str
    action: str
    severity: str
    reason_codes: List[str]
    raw_text: str
    safe_reply: str
    skip_streak: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


def insert_interview_flag(**data: Any) -> int:
    """Insert an interview flag row and return its primary key."""

    payload = InterviewFlagPayload(**data)
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO interview_flags
               (timestamp, interview_id, candidate_id, stage, question_id,
                action, severity, reason_codes, raw_text, safe_reply, skip_streak, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                timestamp,
                payload.interview_id,
                payload.candidate_id,
                payload.stage,
                payload.question_id,
                payload.action,
                payload.severity,
                json.dumps(payload.reason_codes),
                payload.raw_text,
                payload.safe_reply,
                payload.skip_streak,
                json.dumps(payload.metadata),
            ),
        )
        return int(cur.lastrowid)
