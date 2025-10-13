from __future__ import annotations  # Interview flow state models

from typing import Any, Dict, List, Mapping

from pydantic import BaseModel, Field, field_validator


class CompetencyScore(BaseModel):  # Competency evaluation score and notes
    competency: str
    score: float = Field(ge=0.0, le=5.0)
    notes: List[str] = Field(default_factory=list)
    rubric_updates: List[str] = Field(default_factory=list)
    criterion_levels: Dict[str, int] = Field(default_factory=dict)

    @field_validator("criterion_levels", mode="before")
    @classmethod
    def _normalize_levels(cls, value: Any) -> Dict[str, int]:  # Coerce raw levels into bounded ints
        return _coerce_level_map(value)


class EvaluatorState(BaseModel):  # Evaluator memory and scoring snapshot
    summary: str = ""
    anchors: Dict[str, List[str]] = Field(default_factory=dict)
    scores: Dict[str, CompetencyScore] = Field(default_factory=dict)
    rubric_updates: Dict[str, List[str]] = Field(default_factory=dict)


class FlowProgress(BaseModel):  # Stage progression counters
    warmup_limit: int = Field(default=1, ge=0)
    warmup_asked: int = Field(default=0, ge=0)
    competency_index: int = Field(default=0, ge=0)
    competency_question_counts: Dict[str, int] = Field(default_factory=dict)
    low_score_counts: Dict[str, int] = Field(default_factory=dict)
    awaiting_stage: str | None = None


class InterviewContext(BaseModel):  # Flow context describing the interview stage
    interview_id: str
    stage: str
    candidate_name: str
    job_title: str
    resume_summary: str
    highlighted_experiences: List[str] = Field(default_factory=list)
    job_description: str = ""
    competency_pillars: List[str] = Field(default_factory=list)
    competency: str | None = None
    competency_index: int = Field(default=0, ge=0)
    question_index: int = Field(default=0, ge=0)
    project_anchor: str = ""
    competency_projects: Dict[str, str] = Field(default_factory=dict)
    competency_criteria: Dict[str, List[str]] = Field(default_factory=dict)
    competency_covered: Dict[str, List[str]] = Field(default_factory=dict)
    competency_criterion_levels: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    competency_question_counts: Dict[str, int] = Field(default_factory=dict)
    competency_low_scores: Dict[str, int] = Field(default_factory=dict)
    targeted_criteria: List[str] = Field(default_factory=list)
    evaluator: EvaluatorState = Field(default_factory=EvaluatorState)


class ChatTurn(BaseModel):  # Chat message produced by the flow
    speaker: str
    content: str
    tone: str = "neutral"
    competency: str | None = None
    targeted_criteria: List[str] = Field(default_factory=list)
    project_anchor: str = ""


class FlowState(BaseModel):  # LangGraph state tracking context and transcript
    context: InterviewContext
    messages: List[ChatTurn] = Field(default_factory=list)
    progress: FlowProgress = Field(default_factory=FlowProgress)


class SessionLaunch(BaseModel):  # Flow output returned to API callers
    context: InterviewContext
    messages: List[ChatTurn]


__all__ = [
    "CompetencyScore",
    "EvaluatorState",
    "FlowProgress",
    "ChatTurn",
    "FlowState",
    "InterviewContext",
    "SessionLaunch",
]


def _coerce_level_map(value: Any) -> Dict[str, int]:  # Convert raw level mapping to int bounds
    if not isinstance(value, Mapping):
        return {}
    result: Dict[str, int] = {}
    for key, raw in value.items():
        name = str(key).strip()
        if not name:
            continue
        try:
            numeric = float(raw)
        except (TypeError, ValueError):
            continue
        result[name] = int(max(0, min(5, round(numeric))))
    return result
