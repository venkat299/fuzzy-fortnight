"""Competency-stage question generator."""
from __future__ import annotations

from .common import QGContext, make_question, should_followup


def arch_boundaries(ctx: QGContext):
    if ctx.followup_index == 0:
        text = (
            "How did you decompose the system into components or services, and what contracts or boundaries "
            "prevented tight coupling?"
        )
        return make_question(text, ctx, ["components named", "boundary rationale", "coupling mitigations"])
    if not should_followup(ctx):
        return None
    if ctx.followup_index == 1:
        text = "What signals told you the boundaries were right (or wrong), and how did you adjust?"
        return make_question(text, ctx, ["validation signals", "revision loop"])
    text = (
        "Pick one boundary: describe failure propagation if it breaks, and how your design contains the blast radius."
    )
    return make_question(text, ctx, ["failure path", "containment strategy"])


def rel_idempotency(ctx: QGContext):
    if ctx.followup_index == 0:
        text = "How did you ensure idempotency across retries or replays, and where is idempotency enforced?"
        return make_question(text, ctx, ["idempotency locus", "retry policy", "duplicate handling"])
    if not should_followup(ctx):
        return None
    if ctx.followup_index == 1:
        text = "Show one operation where idempotency was non-trivial. How did you prove it?"
        return make_question(text, ctx, ["non-trivial case", "proof/verification"])
    text = "What metrics or alerts detect idempotency regressions in production?"
    return make_question(text, ctx, ["metric/alert named", "signal→action"])


def data_consistency(ctx: QGContext):
    if ctx.followup_index == 0:
        text = (
            "Which consistency model did you choose (for example, eventual or read-your-writes) and why was it "
            "sufficient for your SLAs?"
        )
        return make_question(text, ctx, ["model named", "SLA mapping", "risk/acceptance"])
    if not should_followup(ctx):
        return None
    if ctx.followup_index == 1:
        text = "Describe one user-visible edge condition and how you mitigated it."
        return make_question(text, ctx, ["edge case", "mitigation"])
    text = "What would change if the SLA tightened by 10×?"
    return make_question(text, ctx, ["design delta", "trade-off recalculated"])


def sec_access(ctx: QGContext):
    if ctx.followup_index == 0:
        text = "How did you classify data and enforce least privilege across services or roles?"
        return make_question(text, ctx, ["classification scheme", "LP enforcement point"])
    if not should_followup(ctx):
        return None
    if ctx.followup_index == 1:
        text = "Walk through one authorization failure path—what happens and what’s logged?"
        return make_question(text, ctx, ["failure path", "audit/logging"])
    text = "What reviewed artifacts prove compliance (for example, policies, controls, evidence)?"
    return make_question(text, ctx, ["evidence named", "review cadence"])


ROUTER = {
    "F_BOUNDARIES": arch_boundaries,
    "F_IDEMPOTENCY": rel_idempotency,
    "F_CONSISTENCY": data_consistency,
    "F_ACCESS": sec_access,
}


def run(ctx: QGContext):
    handler = ROUTER.get(ctx.facet_id)
    if handler:
        return handler(ctx)
    if ctx.followup_index == 0:
        return make_question(
            "Describe the core design decision and one trade-off you accepted.",
            ctx,
            ["decision named", "trade-off named"],
        )
    if not should_followup(ctx):
        return None
    return make_question(
        "What evidence showed this was the right trade-off, and how would you revisit it?",
        ctx,
        ["validation signal", "revisit criteria"],
    )
