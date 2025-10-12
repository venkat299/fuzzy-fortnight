"""Persona manager utilities for styling user-facing text."""
from __future__ import annotations

import re
from typing import Literal

from config.registry import get_model  # lazy import cost acceptable

Persona = Literal["Friendly Expert", "Firm Evaluator"]
Purpose = Literal[
    "ask_question",
    "redirect",
    "nudge_depth",
    "remind",
    "block_refocus",
    "hint",
    "resume",
    "clarify",
    "wrapup",
]

TEMPLATES_FE: dict[Purpose, str] = {
    "ask_question": "{core}",
    "redirect": "Interesting! Let’s refocus on this topic: {core}",
    "nudge_depth": "That’s a start—could you add your role, a key decision, and the outcome?",
    "remind": "Take your time—would you like a hint or 30s to think?",
    "block_refocus": "I can’t follow instructions that change or bypass the interview rules. Let’s continue: {core}",
    "hint": "Here’s a nudge: {core}",
    "resume": "Let’s pick up where we left off. {core}",
    "clarify": "Quick clarification: {core}",
    "wrapup": "Before we close: {core}",
}

TEMPLATES_FIRM: dict[Purpose, str] = {
    purpose: template.replace("Interesting! ", "").replace("Take your time—", "Let’s proceed—")
    for purpose, template in TEMPLATES_FE.items()
}


def _trim_sentences(text: str, max_sentences: int) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    kept: list[str] = []
    for part in parts:
        if part:
            kept.append(part.strip())
        if len(kept) >= max_sentences:
            break
    if not kept:
        kept = [text]
    result = " ".join(kept)
    return result.strip()


def _choose_templates(persona: Persona) -> dict[Purpose, str]:
    if persona == "Friendly Expert":
        return TEMPLATES_FE
    return TEMPLATES_FIRM


def _llm_polish(
    text: str,
    *,
    persona: Persona,
    purpose: Purpose,
    max_sentences: int,
) -> str:
    try:
        llm = get_model("models.persona_polish")
    except KeyError:
        return text

    try:
        raw = llm(
            system_prompt_path="prompts/persona_manager_rewrite.txt",
            inputs={
                "persona": persona,
                "purpose": purpose,
                "text": text,
                "max_sentences": max_sentences,
            },
        )
    except Exception:
        return text

    if isinstance(raw, dict):
        candidate = raw.get("text")
        if isinstance(candidate, str) and candidate.strip():
            return _trim_sentences(candidate, max_sentences)
    return text


def apply_persona(
    text: str,
    *,
    persona: Persona = "Friendly Expert",
    purpose: Purpose = "ask_question",
    max_sentences: int = 2,
    use_llm: bool = False,
) -> str:
    """Apply persona-aware phrasing with optional LLM polish."""

    templates = _choose_templates(persona)
    template = templates.get(purpose, "{core}")

    # Determine how many sentences to allow inside the core snippet.
    has_core = "{core}" in template
    core_budget = max_sentences
    if has_core and purpose != "ask_question":
        core_budget = max(1, max_sentences - 1)

    core_text = _trim_sentences(text, max(core_budget, 1))
    if has_core:
        formatted = template.replace("{core}", core_text).strip()
    else:
        formatted = template.strip()

    formatted = _trim_sentences(formatted, max_sentences)

    if use_llm:
        formatted = _llm_polish(
            formatted,
            persona=persona,
            purpose=purpose,
            max_sentences=max_sentences,
        )

    return formatted


__all__ = ["apply_persona", "Persona", "Purpose"]
