from __future__ import annotations  # Session report domain models

from typing import List

from pydantic import BaseModel, Field

from flow_manager.models import EvaluatorState
from rubric_design import InterviewRubricSnapshot


class SessionExchange(BaseModel):  # Transcript exchange persisted for reporting
    sequence: int
    stage: str
    question: str
    answer: str
    competency: str | None = None
    criteria: List[str] = Field(default_factory=list)
    system_message: str = ""
    evaluator: EvaluatorState


class SessionReport(BaseModel):  # Stored session report with rubric and transcript
    session_id: str
    interview_id: str
    candidate_id: str
    candidate_name: str
    job_title: str
    rubric: InterviewRubricSnapshot
    exchanges: List[SessionExchange]
    created_at: str
    updated_at: str


__all__ = ["SessionExchange", "SessionReport"]
