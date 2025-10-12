from agents.qg.common import FacetStatus, QGContext
from agents.qg import warmup as W


def test_warmup_base_and_followups():
    ctx = QGContext(
        stage="warmup",
        competency_id="WARMUP",
        item_id="WU_01",
        followup_index=0,
        facet_id="WU1",
        facet_name="Context & Outcome",
    )
    q0 = W.run(ctx)
    assert q0 is not None
    assert "project" in q0.question_text.lower()

    ctx.followup_index = 1
    ctx.facet_status = FacetStatus(best_of_score=3.0)
    q1 = W.run(ctx)
    assert q1 is not None
    assert "key decision" in q1.question_text.lower()

    ctx.followup_index = 2
    q2 = W.run(ctx)
    assert q2 is not None
    assert "signal" in q2.question_text.lower()


def test_warmup_block_when_high():
    ctx = QGContext(
        stage="warmup",
        competency_id="WARMUP",
        item_id="WU_01",
        followup_index=1,
        facet_id="WU1",
        facet_name="Context & Outcome",
        facet_status=FacetStatus(best_of_score=4.0),
    )
    assert W.run(ctx) is None
