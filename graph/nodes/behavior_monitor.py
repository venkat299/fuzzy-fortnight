"""Behavior monitor node wrapper."""
from __future__ import annotations

from agents.behavior_monitor import run_monitor
from agents.types import MonitorResult
from ..state import GraphState


def run(state: GraphState) -> MonitorResult:
    """Execute the behavior monitor and update streak counters."""

    result = run_monitor(
        interview_id=state.interview_id,
        candidate_id=state.candidate_id,
        stage=state.stage,
        question_id=state.question_id or "NA",
        question_text=state.question_text or "",
        user_msg=state.user_msg,
        skip_streak=state.skip_streak,
        blocks_in_row=state.blocks_in_row,
        hints_used_stage=state.hints_used_stage,
        context_tags=state.mem.get("context_tags", []),
    )

    if result.action == "BLOCK_AND_REFOCUS":
        state.blocks_in_row += 1
    elif result.action == "ALLOW":
        state.blocks_in_row = 0

    state.events.append({"node": "monitor", "action": result.action, "severity": result.severity})
    return result

