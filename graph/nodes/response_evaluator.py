"""Response evaluator node that delegates to the scoring agent."""
from __future__ import annotations

from agents.response_evaluator import score_turn


def run(state, reply: str):
    rubric = state.rubric or {}
    competency_id = state.mem.get("competency_id", "")
    item_id = state.mem.get("item_id", state.question_id or "")
    followup_index = int(state.mem.get("followup_index", 0))
    evaluation = score_turn(
        competency_id=competency_id,
        item_id=item_id,
        followup_index=followup_index,
        question_text=state.question_text or "",
        candidate_reply=reply,
        rubric=rubric,
        is_blocked=False,
    )
    state.mem["last_reply_for_item"] = reply
    state.last_eval = evaluation.model_dump()
    return evaluation
