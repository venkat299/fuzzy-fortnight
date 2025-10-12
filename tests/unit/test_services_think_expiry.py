from datetime import datetime, timedelta, timezone

import pytest

from graph.state import GraphState
from services.think_expiry import maybe_resume_think


@pytest.fixture()
def base_state():
    state = GraphState(session_id="s", interview_id="i", candidate_id="c")
    state.mem["think_until"] = None
    return state


def test_no_think(base_state):
    assert maybe_resume_think(base_state) is None


def test_invalid_timestamp(base_state):
    base_state.mem["think_until"] = "not-a-date"
    assert maybe_resume_think(base_state) is None
    assert base_state.mem["think_until"] is None


def test_think_expired_triggers_resume(monkeypatch, base_state):
    payload = {"resume_line": "resume", "question": {}}

    def fake_resume(state, reason):
        assert reason == "think_expired"
        return payload

    monkeypatch.setattr("services.think_expiry.interrupt_resume", fake_resume)

    due = datetime.now(timezone.utc) - timedelta(seconds=5)
    base_state.mem["think_until"] = due.isoformat()
    result = maybe_resume_think(base_state, now=datetime.now(timezone.utc))
    assert result is payload
    assert base_state.mem["think_until"] is None


def test_naive_timestamp_supported(monkeypatch, base_state):
    monkeypatch.setattr(
        "services.think_expiry.interrupt_resume",
        lambda state, reason: {"resume_line": "ok", "question": {}},
    )
    due = (datetime.now(timezone.utc) - timedelta(seconds=5)).replace(tzinfo=None)
    base_state.mem["think_until"] = due.isoformat()
    result = maybe_resume_think(base_state, now=datetime.now(timezone.utc))
    assert result["resume_line"] == "ok"
