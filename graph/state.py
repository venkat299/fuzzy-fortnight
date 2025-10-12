"""Shared LangGraph state definition."""
from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

Stage = Literal["warmup", "competency", "wrapup"]


class GraphState(BaseModel):
    """Serializable state tracked across LangGraph turns."""

    session_id: str
    interview_id: str
    candidate_id: str

    stage: Stage = "warmup"
    question_id: Optional[str] = None
    question_text: Optional[str] = None

    user_msg: Optional[str] = None
    queued_user_msg: Optional[str] = None
    quick_action: Optional[Dict[str, Any]] = None
    client_ts: Optional[str] = None

    skip_streak: int = 0
    blocks_in_row: int = 0
    hints_used_stage: int = 0

    last_eval: Optional[Dict[str, Any]] = None

    persona: str = "Friendly Expert"
    rubric: Dict[str, Any] = Field(default_factory=dict)

    mem: Dict[str, Any] = Field(default_factory=dict)

    latest_intent: Optional[str] = None

    events: list[Dict[str, Any]] = Field(default_factory=list)

    model_config = {
        "arbitrary_types_allowed": True,
    }
