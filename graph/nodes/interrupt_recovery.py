"""Interrupt recovery node wrapper."""
from __future__ import annotations

from typing import Any, Dict

from agents.interrupt_recovery import run_resume


def run(state: Any, reason: str) -> Dict[str, Any]:
    """Execute the interrupt recovery agent and merge state patches."""

    payload = run_resume(
        session_id=state.session_id,
        reason=reason,
        persona=getattr(state, "persona", "Friendly Expert"),
        fallback_question_text=state.question_text,
    )

    state_patch = payload.get("state_patch") or {}
    if state_patch.get("stage") is not None:
        state.stage = state_patch["stage"]
    if state_patch.get("question_id") is not None:
        state.question_id = state_patch["question_id"]
    if state_patch.get("question_text") is not None:
        state.question_text = state_patch["question_text"]
    mem_patch = state_patch.get("mem") or {}
    if mem_patch:
        state.mem.update(mem_patch)

    state.events.append({"node": "interrupt_recovery", "reason": reason})
    return payload


__all__ = ["run"]
