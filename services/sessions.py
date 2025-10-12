"""Helpers for loading and bootstrapping interview sessions."""
from __future__ import annotations

import uuid
from typing import Optional

from graph.checkpointer import load_checkpoint
from graph.state import GraphState


def new_session(interview_id: str, candidate_id: str, persona: str) -> GraphState:
    """Create a new GraphState with a generated session identifier."""

    session_id = str(uuid.uuid4())
    state = GraphState(session_id=session_id, interview_id=interview_id, candidate_id=candidate_id)
    state.persona = persona
    return state


def load_session(session_id: str) -> Optional[GraphState]:
    """Load the last checkpointed state for ``session_id`` if present."""

    return load_checkpoint(session_id)
