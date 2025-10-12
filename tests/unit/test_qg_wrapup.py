from agents.qg.common import QGContext
from agents.qg import wrapup as R


def test_wrapup_sequence():
    ctx = QGContext(
        stage="wrapup",
        competency_id="WRAP",
        item_id="WR_01",
        followup_index=0,
        facet_id="WU-END",
        facet_name="Reflection",
    )
    q0 = R.run(ctx)
    assert q0 is not None
    assert "redo one decision" in q0.question_text.lower()

    ctx.followup_index = 1
    q1 = R.run(ctx)
    assert q1 is not None
    assert "risk" in q1.question_text.lower()

    ctx.followup_index = 2
    q2 = R.run(ctx)
    assert q2 is not None
    assert "assess your fit" in q2.question_text.lower()
