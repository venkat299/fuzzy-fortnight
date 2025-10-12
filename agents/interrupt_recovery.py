"""Interrupt recovery agent for resuming interviews."""
from __future__ import annotations

from typing import Any, Dict, Optional, Literal

from agents.persona_manager import apply_persona
from graph.checkpointer import load_checkpoint

Reason = Literal["think_expired", "pause_resume", "reconnected"]


_REASON_TO_COPY: Dict[Reason, str] = {
    "think_expired": "Time’s up—ready to share your thoughts?",
    "pause_resume": "Welcome back—shall we continue?",
    "reconnected": "We’re reconnected. Let’s pick up where we left off.",
}


def _resume_line(persona: str, reason: Reason) -> str:
    core = _REASON_TO_COPY.get(reason, "Let’s pick up where we left off.")
    return apply_persona(core, persona=persona, purpose="resume", max_sentences=2)


def _build_metadata(state: Any) -> Optional[Dict[str, Any]]:
    mem = getattr(state, "mem", {}) or {}
    if not mem:
        return None
    metadata = {
        "competency_id": mem.get("competency_id"),
        "item_id": mem.get("item_id"),
        "followup_index": mem.get("followup_index"),
        "facet_id": mem.get("facet_id"),
        "facet_name": mem.get("facet_name"),
        "evidence_targets": mem.get("evidence_targets"),
    }
    if all(value is None for value in metadata.values()):
        return None
    return metadata


def _state_patch(state: Any, reason: Reason) -> Dict[str, Any]:
    mem = getattr(state, "mem", {}) or {}
    patch_mem: Dict[str, Any] = {
        "competency_id": mem.get("competency_id"),
        "item_id": mem.get("item_id"),
        "facet_id": mem.get("facet_id"),
        "facet_name": mem.get("facet_name"),
        "followup_index": mem.get("followup_index"),
        "evidence_targets": mem.get("evidence_targets"),
        "think_until": None if reason == "think_expired" else mem.get("think_until"),
    }
    return {
        "stage": getattr(state, "stage", None),
        "question_id": getattr(state, "question_id", None),
        "question_text": getattr(state, "question_text", None),
        "mem": patch_mem,
    }


def run_resume(
    *,
    session_id: str,
    reason: Reason,
    persona: str,
    fallback_question_text: Optional[str] = None,
) -> Dict[str, Any]:
    state = load_checkpoint(session_id)
    resume_line = _resume_line(persona, reason)

    if state is None:
        question_text = fallback_question_text or "Let’s revisit the previous question briefly."
        rendered = apply_persona(
            question_text,
            persona=persona,
            purpose="ask_question",
            max_sentences=2,
        )
        return {
            "resume_line": resume_line,
            "question": {"text": rendered, "metadata": None},
            "state_patch": {"question_text": rendered},
        }

    question_text = state.question_text or "Let’s revisit the previous question."
    rendered = apply_persona(
        question_text,
        persona=persona,
        purpose="ask_question",
        max_sentences=2,
    )

    metadata = _build_metadata(state)
    patch = _state_patch(state, reason)

    return {
        "resume_line": resume_line,
        "question": {"text": rendered, "metadata": metadata},
        "state_patch": patch,
    }


__all__ = ["run_resume", "Reason"]
