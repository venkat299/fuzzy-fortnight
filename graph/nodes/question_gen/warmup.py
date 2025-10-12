"""Warm-up question generator adapter for the graph."""
from __future__ import annotations

from agents.persona_manager import apply_persona
from agents.qg.common import QGContext
from agents.qg import warmup as warmup_qg
from agents.types import QuestionOut


DEFAULTS = {
    "competency_id": "WARMUP",
    "item_id": "WU_01",
    "facet_id": "WU1",
    "facet_name": "Context & Outcome",
}


def _next_followup_index(state) -> int:
    qg_state = state.mem.setdefault("warmup_qg", {"followup_index": -1})
    followup_index = qg_state["followup_index"] + 1
    if followup_index > 2:
        followup_index = 0
    qg_state["followup_index"] = followup_index
    return followup_index


def run(state) -> QuestionOut:
    followup_index = _next_followup_index(state)
    ctx = QGContext(
        stage="warmup",
        competency_id=DEFAULTS["competency_id"],
        item_id=DEFAULTS["item_id"],
        followup_index=followup_index,
        facet_id=DEFAULTS["facet_id"],
        facet_name=DEFAULTS["facet_name"],
        persona=state.persona,
        candidate_facts=state.mem.get("candidate_facts", {}),
    )
    question = warmup_qg.run(ctx)
    if question is None:
        state.mem["warmup_qg"]["followup_index"] = 0
        ctx.followup_index = 0
        question = warmup_qg.run(ctx)
    styled = apply_persona(
        question.question_text,
        persona=state.persona,
        purpose="ask_question",
    )
    return QuestionOut(question_text=styled, metadata=question.metadata)
