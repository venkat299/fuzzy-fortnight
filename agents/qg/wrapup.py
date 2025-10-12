"""Wrap-up question generator."""
from __future__ import annotations

from .common import QGContext, make_question, should_followup


def reflection(ctx: QGContext):
    if ctx.followup_index == 0:
        text = "If you could redo one decision from this scenario, what would you change and why?"
        return make_question(text, ctx, ["decision named", "improvement rationale"])
    if not should_followup(ctx):
        return None
    if ctx.followup_index == 1:
        text = (
            "What’s one risk you didn’t discuss that could undermine the solution, and how would you monitor it?"
        )
        return make_question(text, ctx, ["risk named", "monitor signal"])
    text = "Anything we didn’t ask that helps assess your fit for this role?"
    return make_question(text, ctx, ["new relevant info", "tie-back to role"])


def run(ctx: QGContext):
    return reflection(ctx)
