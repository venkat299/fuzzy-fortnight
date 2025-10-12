"""Pydantic schemas for the interview session API."""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


QuickActionId = Literal["hint", "think_30", "repeat", "skip"]


class StartReq(BaseModel):
    interview_id: str
    candidate_id: str
    persona_override: Optional[str] = None


class TurnReq(BaseModel):
    session_id: str
    state_ref: Optional[str] = None
    user_msg: Optional[str] = None
    quick_action: Optional[Dict[str, Optional[str]]] = None
    client_ts: Optional[str] = None


class FinishReq(BaseModel):
    session_id: str


class UIMessage(BaseModel):
    role: Literal["assistant", "system"] = "assistant"
    text: str


class QuestionPayload(BaseModel):
    text: str
    metadata: Optional[Dict] = None


class ApiResp(BaseModel):
    session_id: str
    state_ref: str
    ui_messages: List[UIMessage] = Field(default_factory=list)
    question: Optional[QuestionPayload] = None
    quick_actions: List[QuickActionId] = Field(default_factory=list)
    live_scores: Optional[Dict] = None
    event_log: List[Dict] = Field(default_factory=list)
    ui_state: Optional[Dict[str, int]] = None
