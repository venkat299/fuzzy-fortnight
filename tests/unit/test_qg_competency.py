from agents.qg.common import FacetStatus, QGContext
from agents.qg import competency as C


def test_arch_boundaries_flow():
    ctx = QGContext(
        stage="competency",
        competency_id="ARCH",
        item_id="ARCH_01",
        followup_index=0,
        facet_id="F_BOUNDARIES",
        facet_name="Decomposition & Boundaries",
    )
    q0 = C.run(ctx)
    assert q0 is not None
    assert "decompose" in q0.question_text.lower()

    ctx.followup_index = 1
    ctx.facet_status = FacetStatus(best_of_score=3.0)
    q1 = C.run(ctx)
    assert q1 is not None
    assert "signals" in q1.question_text.lower()

    ctx.followup_index = 2
    q2 = C.run(ctx)
    assert q2 is not None
    assert "blast radius" in q2.question_text.lower()


def test_block_followup_when_high():
    ctx = QGContext(
        stage="competency",
        competency_id="ARCH",
        item_id="ARCH_01",
        followup_index=2,
        facet_id="F_BOUNDARIES",
        facet_name="Decomposition & Boundaries",
        facet_status=FacetStatus(best_of_score=4.5),
    )
    assert C.run(ctx) is None
