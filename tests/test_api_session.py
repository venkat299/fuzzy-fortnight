import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import api_server
from candidate_agent import AutoReplyOutcome, QuestionAnswer
from candidate_management import CandidateStore
from flow_manager import ChatTurn, InterviewContext, SessionLaunch
from rubric_design.rubric_design import Rubric, RubricAnchor, RubricCriterion, RubricStore


def _anchors() -> list[RubricAnchor]:
    return [RubricAnchor(level=index + 1, text=f"Level {index + 1}") for index in range(5)]


def _criteria() -> list[RubricCriterion]:
    weights = [0.34, 0.33, 0.33]
    names = ["Communication", "Stakeholders", "Delivery"]
    return [
        RubricCriterion(name=name, weight=weight, anchors=_anchors())
        for name, weight in zip(names, weights, strict=True)
    ]


def _rubric() -> Rubric:
    return Rubric(
        competency="Collaboration",
        band="4-6",
        band_notes=["note"],
        criteria=_criteria(),
        red_flags=["flag"],
        evidence=["Facilitated cross-team workshop", "Mentored juniors", "Drove alignment"],
        min_pass_score=3.4,
    )


def test_start_session_endpoint_returns_context_without_messages(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "interviews.sqlite"
    rubric_store = RubricStore(db_path)
    interview_id = "session-1"
    rubric_store.save(
        interview_id=interview_id,
        job_title="Staff Engineer",
        experience_years="7-10",
        job_description="Owns distributed systems",
        rubrics=[_rubric()],
    )
    candidate_store = CandidateStore(db_path)
    candidate = candidate_store.create_candidate(
        full_name="Jordan Blake",
        resume="Seasoned engineer who builds resilient services and collaborates deeply with design.",
        interview_id=interview_id,
        status="scheduled",
    )
    candidate_id = candidate.candidate_id

    def fail_start_session(*args, **kwargs):  # pragma: no cover - should not run
        raise AssertionError("start_session_with_config should not be called")

    monkeypatch.setattr(api_server, "DATA_PATH", db_path)
    monkeypatch.setattr(api_server, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(api_server, "start_session_with_config", fail_start_session)

    client = TestClient(api_server.app)
    response = client.post(
        f"/api/interviews/{interview_id}/session",
        json={"candidate_id": candidate_id},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["context"]["candidate_name"] == "Jordan Blake"
    assert payload["context"]["stage"] == "warmup"
    assert payload["context"]["auto_answer_enabled"] is False
    assert payload["context"]["candidate_level"] == 3
    assert payload["context"]["qa_history"] == []
    assert payload["messages"] == []
    assert payload["rubric"]["interview_id"] == interview_id


def test_begin_warmup_endpoint_returns_question(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "interviews.sqlite"
    rubric_store = RubricStore(db_path)
    interview_id = "session-2"
    rubric_store.save(
        interview_id=interview_id,
        job_title="Staff Engineer",
        experience_years="7-10",
        job_description="Owns distributed systems",
        rubrics=[_rubric()],
    )
    candidate_store = CandidateStore(db_path)
    candidate = candidate_store.create_candidate(
        full_name="Jordan Blake",
        resume="Seasoned engineer who builds resilient services and collaborates deeply with design.",
        interview_id=interview_id,
        status="scheduled",
    )
    candidate_id = candidate.candidate_id

    fake_launch = SessionLaunch(
        context=InterviewContext(
            interview_id=interview_id,
            stage="warmup",
            candidate_name="Jordan Blake",
            job_title="Staff Engineer",
            resume_summary="Seasoned engineer",
            highlighted_experiences=["Facilitated cross-team workshop"],
        ),
        messages=[
            ChatTurn(
                speaker="Interviewer",
                content="To kick things off, what recent project made you most proud?",
                tone="positive",
            )
        ],
    )

    def fake_start_session(context, *, config_path):
        assert context.interview_id == interview_id
        assert context.candidate_name == "Jordan Blake"
        assert "resilient services" in context.resume_summary.lower()
        assert context.highlighted_experiences
        return fake_launch

    monkeypatch.setattr(api_server, "DATA_PATH", db_path)
    monkeypatch.setattr(api_server, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(api_server, "start_session_with_config", fake_start_session)

    client = TestClient(api_server.app)
    response = client.post(
        f"/api/interviews/{interview_id}/session/start",
        json={"candidate_id": candidate_id},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["context"]["candidate_name"] == "Jordan Blake"
    assert payload["messages"][0]["content"].startswith("To kick things off")
    assert payload["context"]["qa_history"] == []


def test_begin_warmup_endpoint_appends_candidate_reply(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "interviews.sqlite"
    rubric_store = RubricStore(db_path)
    interview_id = "session-3"
    rubric_store.save(
        interview_id=interview_id,
        job_title="Staff Engineer",
        experience_years="7-10",
        job_description="Owns distributed systems",
        rubrics=[_rubric()],
    )
    candidate_store = CandidateStore(db_path)
    candidate = candidate_store.create_candidate(
        full_name="Jordan Blake",
        resume="Seasoned engineer who builds resilient services and collaborates deeply with design.",
        interview_id=interview_id,
        status="scheduled",
    )
    candidate_id = candidate.candidate_id

    fake_launch = SessionLaunch(
        context=InterviewContext(
            interview_id=interview_id,
            stage="warmup",
            candidate_name="Jordan Blake",
            job_title="Staff Engineer",
            resume_summary="Seasoned engineer",
            highlighted_experiences=["Facilitated cross-team workshop"],
        ),
        messages=[
            ChatTurn(
                speaker="Interviewer",
                content="To kick things off, what recent project made you most proud?",
                tone="positive",
            )
        ],
    )

    def fake_start_session(context, *, config_path):
        return fake_launch

    def fake_auto_reply(question, *, resume_summary, history, level, config_path):
        assert question.startswith("To kick")
        assert "Seasoned engineer" in resume_summary
        assert history == []
        assert level == 4
        return AutoReplyOutcome(
            message=QuestionAnswer(
                question=question,
                answer="I've been proud of leading the incident response automation rollout.",
            ),
            tone="positive",
            history=[
                QuestionAnswer(
                    question=question,
                    answer="I've been proud of leading the incident response automation rollout.",
                )
            ],
        )

    monkeypatch.setattr(api_server, "DATA_PATH", db_path)
    monkeypatch.setattr(api_server, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(api_server, "start_session_with_config", fake_start_session)
    monkeypatch.setattr(api_server, "auto_reply_with_config", fake_auto_reply)

    client = TestClient(api_server.app)
    response = client.post(
        f"/api/interviews/{interview_id}/session/start",
        json={
            "candidate_id": candidate_id,
            "auto_answer_enabled": True,
            "candidate_level": 4,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["messages"]) == 2
    assert payload["messages"][1]["speaker"] == "Candidate"
    assert payload["messages"][1]["content"].startswith("I've been proud")
    assert payload["context"]["qa_history"][0]["answer"].startswith("I've been proud")
    assert payload["context"]["candidate_level"] == 4
