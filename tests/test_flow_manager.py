import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import FlowSettings, LlmRoute
from flow_manager import (
    ChatTurn,
    InterviewContext,
    SessionLaunch,
    WarmupPlan,
    advance_session,
    start_session,
)
from flow_manager.models import CompetencyScore
from flow_manager.agents import CompetencyPlan, EvaluationPlan


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
    eval_called = False

    def fake_call(task: str, schema, *, cfg) -> WarmupPlan:
        captured["task"] = task
        assert cfg == route
        assert schema is WarmupPlan
        return WarmupPlan(question="How has your week been so far?", tone="positive")

    monkeypatch.setattr("flow_manager.agents.warmup.call", fake_call)
    def fake_eval(task: str, schema, *, cfg) -> EvaluationPlan:
        nonlocal eval_called
        eval_called = True
        raise AssertionError("Evaluator should not run during warmup question generation")

    monkeypatch.setattr("flow_manager.agents.evaluator.call", fake_eval)
    context = InterviewContext(
        interview_id="abc123",
        stage="warmup",
        candidate_name="Jamie Rivera",
        job_title="Data Scientist",
        resume_summary="Built ML pipelines for growth analytics.",
        highlighted_experiences=["Led experimentation guild", "Shipped forecasting platform"],
        competency_pillars=["Systems Design"],
    )
    registry = {
        "flow_manager.warmup_agent": (route, WarmupPlan),
        "flow_manager.competency_agent": (route, CompetencyPlan),
        "flow_manager.evaluator_agent": (route, EvaluationPlan),
    }
    launch = start_session(context, registry=registry, settings=FlowSettings(warmup_questions=1))
    assert isinstance(launch, SessionLaunch)
    assert launch.context.stage == "competency"
    assert launch.context.interview_id == context.interview_id
    assert launch.context.evaluator.summary == ""
    assert len(launch.messages) == 1
    message = launch.messages[0]
    assert isinstance(message, ChatTurn)
    assert message.speaker == "Interviewer"
    assert message.content == "How has your week been so far?"
    assert message.tone == "positive"
    assert "Build rapport" in captured["task"]
    assert "Highlighted Experiences" in captured["task"]
    assert not eval_called


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
        competency_pillars=["Leadership"],
    )
    registry = {
        "flow_manager.warmup_agent": (route, WarmupPlan),
        "flow_manager.competency_agent": (route, CompetencyPlan),
        "flow_manager.evaluator_agent": (route, EvaluationPlan),
    }
    launch = start_session(context, registry=registry, settings=FlowSettings(warmup_questions=1))
    assert launch.messages == []
    assert not called


def test_advance_session_routes_evaluator(monkeypatch) -> None:
    route = _route()

    def fake_eval(task: str, schema, *, cfg) -> EvaluationPlan:
        assert cfg == route
        assert schema is EvaluationPlan
        return EvaluationPlan(
            stage="competency",
            updated_summary="Candidate discussed onboarding projects.",
            anchors=["Friendly tone"],
            scores=[
                CompetencyScore(
                    competency="Systems Design",
                    score=3.6,
                    notes=["Architecture foundations present"],
                    rubric_updates=["Architecture coverage met"],
                    criterion_levels={"Architecture": 3},
                )
            ],
            rubric_updates=["Warmup captured"],
        )

    monkeypatch.setattr("flow_manager.agents.evaluator.call", fake_eval)
    monkeypatch.setattr(
        "flow_manager.agents.warmup.call",
        lambda task, schema, *, cfg: WarmupPlan(question="Intro?", tone="neutral"),
    )
    def fake_competency(task: str, schema, *, cfg) -> CompetencyPlan:
        assert cfg == route
        assert schema is CompetencyPlan
        return CompetencyPlan(
            question="Walk me through a complex architecture decision.",
            tone="neutral",
            targeted_criteria=["Architecture"],
        )

    monkeypatch.setattr("flow_manager.agents.competency.call", fake_competency)
    context = InterviewContext(
        interview_id="abc123",
        stage="competency",
        candidate_name="Jamie Rivera",
        job_title="Data Scientist",
        resume_summary="Built ML pipelines for growth analytics.",
        highlighted_experiences=[],
        competency_pillars=["Systems Design"],
        competency_projects={"Systems Design": "Analytics platform overhaul"},
        competency_criteria={"Systems Design": ["Architecture", "Scaling", "Trade-offs"]},
    )
    history = [
        ChatTurn(speaker="Interviewer", content="Tell me about yourself", tone="neutral"),
        ChatTurn(speaker="Candidate", content="I led data teams", tone="neutral"),
        ChatTurn(
            speaker="Interviewer",
            content="Describe a recent architecture decision",
            tone="neutral",
        ),
        ChatTurn(
            speaker="Candidate",
            content="I redesigned the analytics pipeline to handle streaming data",
            tone="neutral",
        ),
    ]
    registry = {
        "flow_manager.warmup_agent": (route, WarmupPlan),
        "flow_manager.competency_agent": (route, CompetencyPlan),
        "flow_manager.evaluator_agent": (route, EvaluationPlan),
    }
    launch = advance_session(
        context,
        history,
        registry=registry,
        settings=FlowSettings(warmup_questions=1),
    )
    assert launch.context.stage == "competency"
    assert launch.context.evaluator.summary == "Candidate discussed onboarding projects."
    assert launch.context.evaluator.anchors["competency"] == ["Friendly tone"]
    assert len(launch.messages) == 1
    follow_up = launch.messages[0]
    assert follow_up.competency == "Systems Design"
    assert follow_up.targeted_criteria == ["Architecture"]
    assert launch.context.competency_covered["Systems Design"] == ["Architecture"]
    assert (
        launch.context.competency_criterion_levels["Systems Design"]["Architecture"]
        == 3
    )


def test_competency_score_normalizes_fractional_levels() -> None:
    score = CompetencyScore(
        competency="Systems Design",
        score=3.0,
        notes=[],
        rubric_updates=[],
        criterion_levels={"Strong": 4.8, "Collaboration": "2.2", "  ": 3.3},
    )
    assert score.criterion_levels == {"Strong": 5, "Collaboration": 2}
