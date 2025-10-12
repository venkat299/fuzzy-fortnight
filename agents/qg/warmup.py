"""Warm-up question generator."""
from __future__ import annotations

from .common import QGContext, make_question, should_followup


def base_context_outcome(ctx: QGContext):
    if ctx.followup_index == 0:
        text = (
            "In a recent project you’re proud of, what problem were you solving, what was your role, "
            "and what was the measurable outcome?"
        )
        return make_question(text, ctx, ["role stated", "problem framed", "metric/outcome"])
    if not should_followup(ctx):
        return None
    if ctx.followup_index == 1:
        text = (
            "Could you zoom in on one key decision? Why that choice over an alternative, and what trade-off did "
            "you accept?"
        )
        return make_question(text, ctx, ["alternative considered", "trade-off named", "why chosen"])
    text = "What signal told you that decision was effective (or not), and how did you adjust?"
    return make_question(text, ctx, ["validation signal", "revision loop"])


def run(ctx: QGContext):
    if ctx.facet_id == "WU1":
        return base_context_outcome(ctx)
    return base_context_outcome(ctx)
