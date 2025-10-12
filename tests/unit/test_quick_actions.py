from __future__ import annotations

from config.settings import settings
from graph.state import GraphState

from api.routes import _log_quick_action, _resp_from_state
from services.qa_policy import remaining_hints, row


def test_policy_rows():
    assert row(skip_streak=0, hints_used_stage=0) == ["hint", "think_30", "repeat", "skip"]
    assert row(skip_streak=3, hints_used_stage=0) == ["hint", "think_30"]


def test_remaining_hints():
    assert remaining_hints(0, 2) == 2
    assert remaining_hints(2, 2) == 0


def test_logging(monkeypatch):
    captured = {}

    def fake_insert(**kwargs):
        captured.update(kwargs)
        return 1

    monkeypatch.setattr("api.routes.insert_quick_action", fake_insert)

    state = GraphState(session_id="s", interview_id="i", candidate_id="c")
    state.stage = "competency"
    state.question_id = "Q1"
    state.skip_streak = 2
    state.hints_used_stage = 1

    _log_quick_action(state, "hint", source="standard", latency_ms=50)

    assert captured["action_id"] == "hint"
    assert captured["metadata"]["skip_streak"] == 2
    assert captured["metadata"]["remaining_hints"] == 1


def test_resp_includes_ui_state():
    state = GraphState(session_id="s", interview_id="i", candidate_id="c")
    payload = {"ui_messages": ["hello"], "question": {"text": "Q"}}
    resp = _resp_from_state(state, payload)
    assert resp.ui_state == {
        "skip_streak": 0,
        "hints_used_stage": 0,
        "hints_cap": settings.HINTS_PER_STAGE,
    }
    assert resp.quick_actions == ["hint", "think_30", "repeat", "skip"]
