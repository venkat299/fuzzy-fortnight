import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import LlmRoute
from candidate_agent.auto_reply import (
    AutoReplyAgent,
    AutoReplyContext,
    AutoReplyPlan,
    QuestionAnswer,
    set_noisy_seed,
)


def _route() -> LlmRoute:
    return LlmRoute(
        name="candidate-test",
        base_url="http://example.com",
        endpoint="/llm",
        model="test",
        timeout_s=1.0,
    )


def test_auto_reply_agent_uses_memory(monkeypatch) -> None:
    route = _route()
    captured: dict[str, str] = {}

    def fake_call(task: str, schema, *, cfg) -> AutoReplyPlan:
        captured["task"] = task
        assert schema is AutoReplyPlan
        assert cfg == route
        return AutoReplyPlan(answer="I recently automated incident response runbooks.", tone="positive")

    monkeypatch.setattr("candidate_agent.auto_reply.call", fake_call)
    set_noisy_seed(3)
    context = AutoReplyContext(
        resume_summary="Senior engineer focusing on reliability across distributed systems.",
        history=[
            QuestionAnswer(
                question="Tell me about a time you led a migration.",
                answer="I coordinated a data-center migration with zero downtime.",
            )
        ],
    )
    agent = AutoReplyAgent(route, AutoReplyPlan)
    outcome = agent.invoke(
        "What customer problems are you solving right now?",
        memory=context,
        level=4,
    )
    assert "Interviewer: Tell me about a time you led a migration." in captured["task"]
    assert "Candidate: I coordinated a data-center migration with zero downtime." in captured["task"]
    assert "Candidate reply depth level: 4" in captured["task"]
    assert "You are NoisyCandidate-L4" in captured["task"]
    assert outcome.message.answer
    assert len(outcome.history) == 2
    assert outcome.history[-1].question.startswith("What customer problems")
    assert outcome.tone == "positive"


def test_auto_reply_agent_clamps_level(monkeypatch) -> None:
    route = _route()
    captured: dict[str, str] = {}

    def fake_call(task: str, schema, *, cfg) -> AutoReplyPlan:
        captured["task"] = task
        return AutoReplyPlan(answer="I am reflecting on an earlier project.")

    monkeypatch.setattr("candidate_agent.auto_reply.call", fake_call)
    set_noisy_seed(3)
    context = AutoReplyContext(resume_summary="Platform engineer focused on observability.")
    agent = AutoReplyAgent(route, AutoReplyPlan)
    agent.invoke(
        "Walk me through how you ensured reliability under pressure.",
        memory=context,
        level=-2,
    )
    assert "You are NoisyCandidate-L1" in captured["task"]
    assert "Candidate reply depth level: 1" in captured["task"]


def test_auto_reply_plan_from_raw_content_plain_text() -> None:
    plan = AutoReplyPlan.from_raw_content("Ah, solving complex problems is my forte!")
    assert plan.answer.startswith("Ah, solving complex problems")
    assert plan.tone == "neutral"


def test_auto_reply_plan_from_raw_content_dict_string() -> None:
    payload = '{"content": "I focus on resilient pipelines.", "tone": "Positive"}'
    plan = AutoReplyPlan.from_raw_content(payload)
    assert plan.answer == "I focus on resilient pipelines."
    assert plan.tone == "positive"
