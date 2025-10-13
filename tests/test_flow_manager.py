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
from flow_manager.agents import CompetencyPlan, EvaluationPlan, PersonaQuestion


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
        return WarmupPlan(
            persona_brief="Reference the candidate's recent week in a friendly way.",
            draft_question="How has your week been treating you?",
            tone="positive",
        )

    def fake_persona(task: str, schema, *, cfg) -> PersonaQuestion:
        captured["persona_task"] = task
        assert schema is PersonaQuestion
        return PersonaQuestion(question="How has your week been so far?")

    monkeypatch.setattr("flow_manager.agents.warmup.call", fake_call)
    monkeypatch.setattr("flow_manager.agents.persona.call", fake_persona)
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
        "flow_manager.persona_agent": (route, PersonaQuestion),
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
    assert "warmup" in captured["persona_task"].lower()
    assert "Draft question to refine" in captured["persona_task"]
    assert not eval_called


def test_warmup_uses_draft_when_persona_disabled(monkeypatch) -> None:
    route = _route()

    def fake_call(task: str, schema, *, cfg) -> WarmupPlan:
        assert schema is WarmupPlan
        return WarmupPlan(
            persona_brief="Keep things casual.",
            draft_question="How did you spend your weekend?",
            tone="positive",
        )

    def fail_persona(*args, **kwargs):
        raise AssertionError("Persona agent should be bypassed")

    monkeypatch.setattr("flow_manager.agents.warmup.call", fake_call)
    monkeypatch.setattr("flow_manager.agents.persona.call", fail_persona)
    context = InterviewContext(
        interview_id="draft123",
        stage="warmup",
        candidate_name="Morgan Lee",
        job_title="Product Manager",
        resume_summary="Drives product strategy for collaboration tools.",
        highlighted_experiences=["Launched async roadmap rituals"],
        competency_pillars=["Product Sense"],
    )
    registry = {
        "flow_manager.warmup_agent": (route, WarmupPlan),
        "flow_manager.competency_agent": (route, CompetencyPlan),
        "flow_manager.evaluator_agent": (route, EvaluationPlan),
        "flow_manager.persona_agent": (route, PersonaQuestion),
    }
    launch = start_session(
        context,
        registry=registry,
        settings=FlowSettings(warmup_questions=1, persona_enabled=False),
    )
    assert len(launch.messages) == 1
    assert launch.messages[0].content == "How did you spend your weekend?"


def test_start_session_skips_when_not_warmup(monkeypatch) -> None:
    route = _route()
    called = False

    def fake_call(task: str, schema, *, cfg) -> WarmupPlan:
        nonlocal called
        called = True
        return WarmupPlan(persona_brief="Say hello", draft_question="How are you?", tone="neutral")

    monkeypatch.setattr("flow_manager.agents.warmup.call", fake_call)
    monkeypatch.setattr(
        "flow_manager.agents.persona.call",
        lambda task, schema, *, cfg: PersonaQuestion(question="Hello"),
    )
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
        "flow_manager.persona_agent": (route, PersonaQuestion),
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
        lambda task, schema, *, cfg: WarmupPlan(
            persona_brief="Intro?",
            draft_question="Can you introduce yourself?",
            tone="neutral",
        ),
    )
    def fake_competency(task: str, schema, *, cfg) -> CompetencyPlan:
        assert cfg == route
        assert schema is CompetencyPlan
        return CompetencyPlan(
            persona_brief="Probe the analytics platform overhaul for architecture decisions.",
            draft_question="Can you walk me through the key architecture calls in that overhaul?",
            tone="neutral",
            targeted_criteria=["Architecture"],
        )

    monkeypatch.setattr("flow_manager.agents.competency.call", fake_competency)
    monkeypatch.setattr(
        "flow_manager.agents.persona.call",
        lambda task, schema, *, cfg: PersonaQuestion(
            question="Walk me through a complex architecture decision."
        ),
    )
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
        "flow_manager.persona_agent": (route, PersonaQuestion),
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


def test_competency_uses_draft_when_persona_disabled(monkeypatch) -> None:
    route = _route()

    def fake_eval(task: str, schema, *, cfg) -> EvaluationPlan:
        return EvaluationPlan(
            stage="competency",
            updated_summary="",
            anchors=[],
            scores=[],
            rubric_updates=[],
        )

    def fake_competency(task: str, schema, *, cfg) -> CompetencyPlan:
        return CompetencyPlan(
            persona_brief="Drill into the migration project decisions.",
            draft_question="What trade-offs did you weigh during the migration?",
            tone="neutral",
            targeted_criteria=["Trade-offs"],
        )

    def fail_persona(*args, **kwargs):
        raise AssertionError("Persona agent should be bypassed")

    monkeypatch.setattr("flow_manager.agents.evaluator.call", fake_eval)
    monkeypatch.setattr("flow_manager.agents.competency.call", fake_competency)
    monkeypatch.setattr("flow_manager.agents.persona.call", fail_persona)
    context = InterviewContext(
        interview_id="comp123",
        stage="competency",
        candidate_name="Riley Chen",
        job_title="Engineering Manager",
        resume_summary="Led core platform migrations.",
        highlighted_experiences=[],
        competency_pillars=["Systems Design"],
        competency_projects={"Systems Design": "Core platform migration"},
        competency_criteria={"Systems Design": ["Trade-offs", "Execution"]},
        competency_covered={"Systems Design": ["Execution"]},
    )
    history = [
        ChatTurn(speaker="Interviewer", content="Welcome", tone="positive"),
        ChatTurn(speaker="Candidate", content="Glad to be here", tone="positive"),
    ]
    registry = {
        "flow_manager.warmup_agent": (route, WarmupPlan),
        "flow_manager.competency_agent": (route, CompetencyPlan),
        "flow_manager.evaluator_agent": (route, EvaluationPlan),
        "flow_manager.persona_agent": (route, PersonaQuestion),
    }
    launch = advance_session(
        context,
        history,
        registry=registry,
        settings=FlowSettings(warmup_questions=1, persona_enabled=False),
    )
    assert len(launch.messages) == 1
    follow_up = launch.messages[0]
    assert follow_up.content == "What trade-offs did you weigh during the migration?"
    assert follow_up.targeted_criteria == ["Trade-offs"]


def test_competency_score_normalizes_fractional_levels() -> None:
    score = CompetencyScore(
        competency="Systems Design",
        score=3.0,
        notes=[],
        rubric_updates=[],
        criterion_levels={"Strong": 4.8, "Collaboration": "2.2", "  ": 3.3},
    )
    assert score.criterion_levels == {"Strong": 5, "Collaboration": 2}
