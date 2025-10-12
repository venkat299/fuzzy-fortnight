"""Persona-aligned hint agent that relies on an LLM backend."""
from __future__ import annotations

from typing import Any, Dict, List

from config.registry import get_model
from agents.persona_manager import apply_persona

HINT_KEY = "models.hint_agent"


def _collect_prior_hints(state: Any, facet_id: str) -> List[str]:
    prior_store = state.mem.setdefault("prior_hints", {})
    hints = prior_store.get(facet_id, [])
    if not isinstance(hints, list):
        hints = []
        prior_store[facet_id] = hints
    return hints[-3:]


def _remember_hint(state: Any, facet_id: str, hint: str) -> None:
    prior_store = state.mem.setdefault("prior_hints", {})
    hints = prior_store.setdefault(facet_id, [])
    hints.append(hint)
    if len(hints) > 5:
        del hints[:-5]


def run(state: Any) -> str:
    """Generate a micro-hint for the active facet using the bound LLM."""

    persona = getattr(state, "persona", "Friendly Expert")
    facet_id = state.mem.get("facet_id", "WU1")
    facet_name = state.mem.get("facet_name", "Context & Outcome")
    question_text = state.question_text or ""
    evidence_targets: List[str] = list(state.mem.get("evidence_targets") or [])
    prior_hints = _collect_prior_hints(state, facet_id)
    last_reply = (
        getattr(state, "user_msg", None)
        or state.mem.get("last_reply_for_item", "")
    )

    llm = get_model(HINT_KEY)
    raw: Dict[str, str] = llm(
        system_prompt_path="prompts/hint_agent.txt",
        inputs={
            "persona": persona,
            "facet": {"id": facet_id, "name": facet_name},
            "question_text": question_text,
            "evidence_targets": evidence_targets,
            "prior_hints": prior_hints,
            "last_reply": last_reply,
            "constraints": {"max_sentences": 2},
        },
        temperature=0.2,
        max_tokens=120,
    )

    hint = (raw or {}).get("hint", "").strip()
    if not hint:
        hint = "Offer one concrete step toward this facet."

    styled = apply_persona(hint, persona=persona, purpose="hint")
    _remember_hint(state, facet_id, styled)
    return styled


__all__ = ["run", "HINT_KEY"]
