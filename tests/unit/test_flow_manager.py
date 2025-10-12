from datetime import datetime

from config.registry import bind_model
from agents.flow_manager import FlowConfig, FlowDeps, handle_after_monitor_and_intent
from agents.qg.common import QGContext
from agents.types import QuestionMetadata, QuestionOut
from agents.hint_agent import HINT_KEY
from agents.response_evaluator import EVAL_KEY
from graph.state import GraphState
import services.scoring as scoring_mod


def fake_qg(ctx: QGContext):
    if ctx.facet_status and ctx.facet_status.best_of_score >= 4.0:
        return None
    return QuestionOut(
        question_text="Base question?",
        metadata=QuestionMetadata(
            competency_id="ARCH",
            item_id="ARCH_01",
            followup_index=ctx.followup_index,
            facet_id="F_BOUNDARIES",
            facet_name="Decomposition & Boundaries",
            evidence_targets=["x"],
        ),
    )


def setup_module(_module):
    def fake_hint_llm(**kwargs):
        inputs = kwargs.get("inputs", {})
        targets = inputs.get("evidence_targets") or []
        target = targets[0] if targets else "impact"
        return {"hint": f"Name your role and tie it to {target}."}

    bind_model(HINT_KEY, fake_hint_llm)

    def fake_eval_llm(**kwargs):
        return {
            "competency_id": "ARCH",
            "item_id": "ARCH_01",
            "turn_index": kwargs["inputs"]["followup_index"],
            "criterion_scores": [
                {"id": "C1", "score": 4},
                {"id": "C2", "score": 4},
                {"id": "C3", "score": 3},
            ],
            "overall": 3.7,
            "band": "mid",
            "notes": "solid answer",
        }

    bind_model(EVAL_KEY, fake_eval_llm)

    scoring_mod.insert_score = lambda **kwargs: None
    scoring_mod.insert_scores_summary = lambda **kwargs: None
    scoring_mod.insert_scores_overall = lambda **kwargs: None


def _deps(now: datetime = datetime.utcnow):
    return FlowDeps(
        qg_router=fake_qg,
        evaluator=None,
        now=lambda: now,
    )


def test_followup_then_block_advance():
    state = GraphState(session_id="s", interview_id="i", candidate_id="c")
    state.stage = "competency"
    state.mem.update(
        {
            "competency_id": "ARCH",
            "item_id": "ARCH_01",
            "facet_id": "F_BOUNDARIES",
            "facet_name": "Decomposition & Boundaries",
            "followup_index": 0,
        }
    )
    state.rubric = {
        "criteria": [
            {"id": "C1", "weight": 0.34},
            {"id": "C2", "weight": 0.33},
            {"id": "C3", "weight": 0.33},
        ]
    }
    state.question_text = "Q"
    state.question_id = "ARCH_01"
    state.user_msg = "Meaningful answer"
    state.latest_intent = "answer"

    decision = handle_after_monitor_and_intent(state, _deps(), FlowConfig())
    assert decision.type == "ASK"
    assert decision.payload["question"]["metadata"]["followup_index"] == 1
    assert state.mem["last_reply_for_item"] == "Meaningful answer"
    assert "live_scores" in decision.payload

    cache = state.mem["score_cache"]
    cache["competencies"]["ARCH"]["items"]["ARCH_01"]["best_of"] = 4.0
    state.user_msg = "Second answer"
    state.latest_intent = "answer"
    state.mem["followup_index"] = 1
    state.rubric = {
        "criteria": [
            {"id": "C1", "weight": 0.34},
            {"id": "C2", "weight": 0.33},
            {"id": "C3", "weight": 0.33},
        ]
    }

    next_decision = handle_after_monitor_and_intent(state, _deps(), FlowConfig())
    assert next_decision.type in {"AUTO_SKIP_MOVED", "EVAL_AND_ASK_NEXT"}
    assert state.mem["last_reply_for_item"] == "Second answer"
    assert "live_scores" in next_decision.payload


def test_hint_cap_and_nudge():
    state = GraphState(session_id="s", interview_id="i", candidate_id="c")
    state.stage = "competency"
    state.mem.update(
        {
            "competency_id": "ARCH",
            "item_id": "ARCH_01",
            "facet_id": "F_BOUNDARIES",
            "facet_name": "Decomposition & Boundaries",
        }
    )
    state.latest_intent = "ask_hint"
    state.hints_used_stage = 2

    decision = handle_after_monitor_and_intent(state, _deps(), FlowConfig(hints_per_stage=2))
    assert decision.type == "HINT"
    assert decision.payload.get("exhausted") is True


def test_three_blocks_auto_skip():
    state = GraphState(session_id="s", interview_id="i", candidate_id="c")
    state.blocks_in_row = 3
    state.stage = "competency"
    state.mem.update(
        {
            "competency_id": "ARCH",
            "item_id": "ARCH_01",
            "facet_id": "F_BOUNDARIES",
            "facet_name": "Decomposition & Boundaries",
        }
    )

    decision = handle_after_monitor_and_intent(state, _deps(), FlowConfig())
    assert decision.type == "AUTO_SKIP_MOVED"
