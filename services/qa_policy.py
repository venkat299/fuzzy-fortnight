"""Quick-action policy helpers."""
from __future__ import annotations

from typing import List

STANDARD = ["hint", "think_30", "repeat", "skip"]
NUDGE = ["hint", "think_30"]


def row(skip_streak: int, hints_used_stage: int, hints_cap: int = 2) -> List[str]:
    """Return the quick-action row for the current skip streak.

    After three consecutive skips we limit to a nudge row with hint + think.
    """

    if skip_streak >= 3:
        return NUDGE
    return STANDARD


def remaining_hints(hints_used_stage: int, hints_cap: int = 2) -> int:
    """Return the remaining hints available in the stage."""

    return max(0, hints_cap - hints_used_stage)
