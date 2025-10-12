import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import LlmRoute
from flow_manager import (
    ChatTurn,
    InterviewContext,
    SessionLaunch,
    WarmupPlan,
    start_session,
)


def _route() -> LlmRoute:
    return LlmRoute(
        name="warmup-test",
        base_url="http://example.com",
        endpoint="/llm",
        model="test",
        timeout_s=1.0,
    )


def test_start_session_generates_warmup(monkeypatch) -> None:
    route = _route()
    captured: dict[str, str] = {}

    def fake_call(task: str, schema, *, cfg) -> WarmupPlan:
        captured["task"] = task
        assert cfg == route
        assert schema is WarmupPlan
        return WarmupPlan(question="How has your week been so far?", tone="positive")

    monkeypatch.setattr("flow_manager.agents.warmup.call", fake_call)
    context = InterviewContext(
        interview_id="abc123",
        stage="warmup",
        candidate_name="Jamie Rivera",
        job_title="Data Scientist",
        resume_summary="Built ML pipelines for growth analytics.",
        highlighted_experiences=["Led experimentation guild", "Shipped forecasting platform"],
    )
    launch = start_session(context, registry={"flow_manager.warmup_agent": (route, WarmupPlan)})
    assert isinstance(launch, SessionLaunch)
    assert launch.context == context
    assert len(launch.messages) == 1
    message = launch.messages[0]
    assert isinstance(message, ChatTurn)
    assert message.speaker == "Interviewer"
    assert message.content == "How has your week been so far?"
    assert message.tone == "positive"
    assert "Build rapport" in captured["task"]
    assert "Highlighted Experiences" in captured["task"]


def test_start_session_skips_when_not_warmup(monkeypatch) -> None:
    route = _route()
    called = False

    def fake_call(task: str, schema, *, cfg) -> WarmupPlan:
        nonlocal called
        called = True
        return WarmupPlan(question="Hello", tone="neutral")

    monkeypatch.setattr("flow_manager.agents.warmup.call", fake_call)
    context = InterviewContext(
        interview_id="xyz789",
        stage="competency",
        candidate_name="Alex Murphy",
        job_title="Engineering Manager",
        resume_summary="Scaled teams across two continents.",
        highlighted_experiences=["Managed platform migration"],
    )
    launch = start_session(context, registry={"flow_manager.warmup_agent": (route, WarmupPlan)})
    assert launch.messages == []
    assert not called
