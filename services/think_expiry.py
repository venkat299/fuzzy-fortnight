"""Think-timer expiry helper for interview sessions."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from graph.nodes.interrupt_recovery import run as interrupt_resume


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def maybe_resume_think(state: Any, now: Optional[datetime] = None):
    """Resume via interrupt recovery when the think timer has expired."""

    mem = getattr(state, "mem", {})
    if not isinstance(mem, dict):
        return None
    think_until = mem.get("think_until")
    if not think_until:
        return None

    try:
        due = datetime.fromisoformat(think_until)
    except Exception:
        mem["think_until"] = None
        return None

    due = _as_utc(due)
    current = _as_utc(now) if now else datetime.now(timezone.utc)

    if current >= due:
        mem["think_until"] = None
        return interrupt_resume(state, reason="think_expired")
    return None


__all__ = ["maybe_resume_think"]
