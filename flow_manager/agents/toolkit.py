from __future__ import annotations  # Shared LangChain helpers for interview agents

from typing import Iterable, List, Sequence

from ..models import ChatTurn


def transcript_messages(history: Sequence[ChatTurn]) -> List[dict]:  # Map chat turns to LangChain message dicts
    messages: List[dict] = []
    for turn in history:
        role = _resolve_role(turn.speaker)
        content = turn.content.strip()
        if not content:
            continue
        payload = {"role": role, "content": content}
        if turn.targeted_criteria:
            payload["targeted_criteria"] = list(turn.targeted_criteria)
        if turn.competency:
            payload["competency"] = turn.competency
        if turn.project_anchor:
            payload["project_anchor"] = turn.project_anchor
        messages.append(payload)
    return messages


def clamp_text(text: str, limit: int = 600) -> str:  # Compact whitespace and clip length
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def bullet_list(entries: Iterable[str]) -> str:  # Render entries as markdown bullets
    lines = [item.strip() for item in entries if item and item.strip()]
    if not lines:
        return "None provided."
    return "\n".join(f"- {line}" for line in lines)


def _resolve_role(speaker: str) -> str:
    name = (speaker or "").strip().lower()
    if name in {"candidate", "applicant"}:
        return "user"
    if name in {"interviewer", "system"}:
        return "assistant"
    return "user"


__all__ = ["bullet_list", "clamp_text", "transcript_messages"]
