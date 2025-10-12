from __future__ import annotations  # Interview flow state models

from typing import List

from pydantic import BaseModel, Field


class InterviewContext(BaseModel):  # Flow context describing the interview stage
    interview_id: str
    stage: str
    candidate_name: str
    job_title: str
    resume_summary: str
    highlighted_experiences: List[str] = Field(default_factory=list)


class ChatTurn(BaseModel):  # Chat message produced by the flow
    speaker: str
    content: str
    tone: str = "neutral"


class FlowState(BaseModel):  # LangGraph state tracking context and transcript
    context: InterviewContext
    messages: List[ChatTurn] = Field(default_factory=list)


class SessionLaunch(BaseModel):  # Flow output returned to API callers
    context: InterviewContext
    messages: List[ChatTurn]


__all__ = [
    "ChatTurn",
    "FlowState",
    "InterviewContext",
    "SessionLaunch",
]
