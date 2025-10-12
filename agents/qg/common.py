"""Shared utilities for question generators."""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from agents.types import QuestionMetadata, QuestionOut

Stage = Literal["warmup", "competency", "wrapup"]


class FacetStatus(BaseModel):
    """Scoring snapshot for a question facet."""

    best_of_score: float = 1.0


class QGContext(BaseModel):
    """Context passed into stage-specific question generators."""

    stage: Stage
    competency_id: str
    item_id: str
    followup_index: int
    facet_id: str
    facet_name: str
    facet_status: Optional[FacetStatus] = None
    persona: str = "Friendly Expert"
    candidate_facts: Dict[str, str] = Field(default_factory=dict)


HIGH_SATISFIED = 4.0


def should_followup(ctx: QGContext) -> bool:
    """Return True when a follow-up question should be asked."""

    if ctx.followup_index == 0:
        return True
    if ctx.followup_index > 2:
        return False
    if ctx.facet_status and ctx.facet_status.best_of_score >= HIGH_SATISFIED:
        return False
    return True


def make_question(text: str, ctx: QGContext, evidence_targets: List[str]) -> QuestionOut:
    """Create a QuestionOut payload with the supplied metadata."""

    return QuestionOut(
        question_text=text.strip(),
        metadata=QuestionMetadata(
            competency_id=ctx.competency_id,
            item_id=ctx.item_id,
            followup_index=ctx.followup_index,
            facet_id=ctx.facet_id,
            facet_name=ctx.facet_name,
            evidence_targets=evidence_targets,
        ),
    )


__all__ = [
    "FacetStatus",
    "QGContext",
    "Stage",
    "should_followup",
    "make_question",
    "HIGH_SATISFIED",
]
