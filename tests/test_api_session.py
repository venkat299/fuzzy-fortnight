import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import api_server
from candidate_agent import AutoReplyOutcome, QuestionAnswer
from candidate_management import CandidateStore
from flow_manager import ChatTurn, InterviewContext, SessionLaunch
from flow_manager.models import EvaluatorState, CompetencyScore
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
        band_notes=["Stakeholder’s perspective"],
        criteria=_criteria(),
        red_flags=["flag"],
        evidence=["Facilitated cross-team workshop", "Mentored juniors", "Drove alignment"],
        min_pass_score=3.4,
    )


def _write_config(path: Path) -> None:
    payload = {
        "llm_routes": {
            "stub-route": {
                "name": "stub-route",
                "base_url": "http://localhost",
                "endpoint": "/v1",
                "model": "stub-model",
                "timeout_s": 30,
                "max_retries": 1,
                "api_key_env": None,
                "sequential": False,
            }
        },
        "registry": {
            "jd_analysis.generate_competency_matrix": "stub-route",
            "rubric_design.generate_rubric": "stub-route",
            "flow_manager.warmup_agent": "stub-route",
            "flow_manager.competency_primer": "stub-route",
            "flow_manager.competency_agent": "stub-route",
            "candidate_agent.auto_reply": "stub-route",
            "flow_manager.evaluator_agent": "stub-route",
            "flow_manager.persona_agent": "stub-route",
        },
        "flow": {
            "warmup_questions": 1,
            "max_competency_followups": 3,
            "low_score_threshold": 2.0,
            "persona_enabled": False,
        },
        "noisy": {"enable_spelling_mistakes": False},
    }
    path.write_text(json.dumps(payload))


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
    config_path = tmp_path / "config.json"
    _write_config(config_path)
    monkeypatch.setattr(api_server, "CONFIG_PATH", config_path)
    monkeypatch.setattr(api_server, "start_session_with_config", fail_start_session)
    monkeypatch.setattr(
        api_server,
        "prime_competencies_with_config",
        lambda **kwargs: {comp: "Primer project" for comp in kwargs.get("competencies", [])},
    )

    client = TestClient(api_server.app)
    response = client.post(
        f"/api/interviews/{interview_id}/session",
        json={"candidate_id": candidate_id},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["context"]["candidate_name"] == "Jordan Blake"
    assert payload["context"]["stage"] == "warmup"
    assert payload["context"]["auto_answer_enabled"] is True
    assert payload["context"]["candidate_level"] == 3
    assert payload["context"]["qa_history"] == []
    assert payload["context"]["competency"] == "Collaboration"
    assert payload["context"]["competency_projects"]["Collaboration"] == "Primer project"
    assert payload["context"]["question_index"] == 0
    assert payload["context"]["competency_criterion_levels"]["Collaboration"] == {}
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
            stage="competency",
            candidate_name="Jordan Blake",
            job_title="Staff Engineer",
            resume_summary="Seasoned engineer",
            highlighted_experiences=["Facilitated cross-team workshop"],
            competency="Collaboration",
            competency_pillars=["Collaboration"],
            competency_projects={"Collaboration": "Workshop series"},
            competency_criteria={"Collaboration": ["Communication", "Stakeholders", "Delivery"]},
            evaluator=EvaluatorState(),
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
        assert context.job_description == "Owns distributed systems"
        assert context.competency_pillars
        assert context.competency_projects
        return fake_launch

    monkeypatch.setattr(api_server, "DATA_PATH", db_path)
    config_path = tmp_path / "config.json"
    _write_config(config_path)
    monkeypatch.setattr(api_server, "CONFIG_PATH", config_path)
    monkeypatch.setattr(api_server, "start_session_with_config", fake_start_session)
    monkeypatch.setattr(
        api_server,
        "prime_competencies_with_config",
        lambda **kwargs: {comp: "Primer project" for comp in kwargs.get("competencies", [])},
    )

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
    assert payload["context"]["competency_projects"]["Collaboration"] == "Workshop series"
    assert payload["context"]["evaluator"] == {
        "summary": "",
        "anchors": {},
        "scores": {},
        "rubric_updates": {},
    }


def test_begin_warmup_endpoint_does_not_append_candidate_reply(monkeypatch, tmp_path) -> None:
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
            competency_pillars=["Collaboration"],
            competency_projects={"Collaboration": "Primer project"},
            competency_criteria={"Collaboration": ["Communication", "Stakeholders", "Delivery"]},
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

    def fail_auto_reply(*args, **kwargs):  # pragma: no cover - should not run
        raise AssertionError("auto_reply_with_config should not be called during warmup")

    monkeypatch.setattr(api_server, "DATA_PATH", db_path)
    config_path = tmp_path / "config.json"
    _write_config(config_path)
    monkeypatch.setattr(api_server, "CONFIG_PATH", config_path)
    monkeypatch.setattr(api_server, "start_session_with_config", fake_start_session)
    monkeypatch.setattr(
        api_server,
        "prime_competencies_with_config",
        lambda **kwargs: {comp: "Primer project" for comp in kwargs.get("competencies", [])},
    )
    monkeypatch.setattr(api_server, "auto_reply_with_config", fail_auto_reply)

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
    assert len(payload["messages"]) == 1
    assert payload["messages"][0]["speaker"] == "Interviewer"
    assert payload["context"]["qa_history"] == []
    assert payload["context"]["candidate_level"] == 4
    assert payload["context"]["evaluator"] == {
        "summary": "",
        "anchors": {},
        "scores": {},
        "rubric_updates": {},
    }


def test_generate_candidate_auto_reply_returns_plan(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "interviews.sqlite"
    rubric_store = RubricStore(db_path)
    interview_id = "session-4"
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

    history = [
        QuestionAnswer(
            question="Tell me about a recent success.",
            answer="I led the migration to a service mesh.",
        )
    ]

    def fake_auto_reply(
        question,
        *,
        resume_summary,
        history,
        level,
        competency,
        project_anchor,
        targeted_criteria,
        config_path,
    ):
        assert "Seasoned engineer" in resume_summary
        assert level == 4
        assert len(history) == 1
        assert competency is None
        assert project_anchor == ""
        assert targeted_criteria == []
        return AutoReplyOutcome(
            message=QuestionAnswer(
                question=question,
                answer="I drove the incident response automation rollout with cross-team partners.",
            ),
            tone="positive",
            history=history
            + [
                QuestionAnswer(
                    question=question,
                    answer="I drove the incident response automation rollout with cross-team partners.",
                )
            ],
        )

    monkeypatch.setattr(api_server, "DATA_PATH", db_path)
    config_path = tmp_path / "config.json"
    _write_config(config_path)
    monkeypatch.setattr(api_server, "CONFIG_PATH", config_path)
    monkeypatch.setattr(api_server, "auto_reply_with_config", fake_auto_reply)

    client = TestClient(api_server.app)
    response = client.post(
        f"/api/interviews/{interview_id}/session/auto-reply",
        json={
            "candidate_id": candidate_id,
            "question": "How do you keep stakeholders aligned?",
            "qa_history": [entry.model_dump() for entry in history],
            "candidate_level": 4,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["tone"] == "positive"
    assert payload["message"]["answer"].startswith("I drove the incident response automation rollout")


def test_submit_candidate_reply_returns_follow_up(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "interviews.sqlite"
    rubric_store = RubricStore(db_path)
    interview_id = "session-5"
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

    captured_history: list[ChatTurn] = []

    def fake_advance_session(context, history, *, config_path):
        nonlocal captured_history
        captured_history = history
        assert context.competency == "Collaboration"
        assert context.competency_criterion_levels["Collaboration"].get("Communication") == 2
        return SessionLaunch(
            context=context,
            messages=[
                ChatTurn(
                    speaker="Interviewer",
                    content="Great context. Could you walk me through your stakeholder rhythm?",
                    tone="neutral",
                    competency="Collaboration",
                    targeted_criteria=["Stakeholders"],
                    project_anchor="Primer project",
                )
            ],
        )

    monkeypatch.setattr(api_server, "DATA_PATH", db_path)
    config_path = tmp_path / "config.json"
    _write_config(config_path)
    monkeypatch.setattr(api_server, "CONFIG_PATH", config_path)
    monkeypatch.setattr(api_server, "advance_session_with_config", fake_advance_session)

    prior_history = [
        {
            "question": "Tell me about a recent success.",
            "answer": "I led the migration to a service mesh.",
        }
    ]

    client = TestClient(api_server.app)
    response = client.post(
        f"/api/interviews/{interview_id}/session/reply",
        json={
            "candidate_id": candidate_id,
            "question": "How do you keep stakeholders aligned?",
            "answer": "I schedule recurring alignment forums with clear agendas and shared artifacts.",
            "tone": "positive",
            "stage": "warmup",
            "auto_answer_enabled": True,
            "candidate_level": 5,
            "qa_history": prior_history,
            "competency": "Collaboration",
            "competency_index": 0,
            "question_index": 0,
            "project_anchor": "Primer project",
            "competency_projects": {"Collaboration": "Primer project"},
            "competency_criteria": {"Collaboration": ["Communication", "Stakeholders", "Delivery"]},
            "competency_criterion_levels": {"Collaboration": {"Communication": 2}},
            "competency_covered": {"Collaboration": []},
            "competency_question_counts": {"Collaboration": 0},
            "competency_low_scores": {"Collaboration": 0},
            "targeted_criteria": ["Stakeholders"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["messages"][0]["speaker"] == "Candidate"
    assert payload["messages"][0]["tone"] == "positive"
    assert payload["messages"][1]["speaker"] == "Interviewer"
    assert payload["messages"][1]["targeted_criteria"] == ["Stakeholders"]
    assert len(payload["messages"]) == 3
    assert payload["messages"][2]["speaker"] == "System"
    assert "Targeted criteria" in payload["messages"][2]["content"]
    assert "Stakeholders" in payload["messages"][2]["content"]
    assert payload["context"]["qa_history"][-1]["answer"].startswith("I schedule recurring alignment forums")
    assert payload["context"]["qa_history"][-1]["competency"] == "Collaboration"
    assert payload["context"]["qa_history"][-1]["criteria"] == ["Stakeholders"]
    assert payload["context"]["qa_history"][-1]["stage"] == "warmup"
    assert payload["context"]["candidate_level"] == 5
    assert payload["context"]["evaluator"] == {
        "summary": "",
        "anchors": {},
        "scores": {},
        "rubric_updates": {},
    }
    assert payload["context"]["competency"] == "Collaboration"
    assert payload["context"]["project_anchor"] == "Primer project"
    assert (
        payload["context"]["competency_criterion_levels"]["Collaboration"]["Communication"]
        == 2
    )
    assert len(captured_history) == 4
    assert captured_history[-1].speaker == "Candidate"


def test_session_report_endpoint_returns_transcript(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "interviews.sqlite"
    rubric_store = RubricStore(db_path)
    interview_id = "session-6"
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

    def fake_advance_session(context, history, *, config_path):
        evaluator = EvaluatorState(
            summary="Captured warmup insight",
            anchors={"warmup": ["Identified stakeholder cadence"]},
            scores={
                "Collaboration": CompetencyScore(
                    competency="Collaboration",
                    score=3.5,
                    notes=["Strong collaboration story"],
                    rubric_updates=["Stakeholders explored"],
                    criterion_levels={"Stakeholders": 4},
                )
            },
            rubric_updates={"warmup": ["Stakeholders explored"]},
        )
        updated_context = context.model_copy(update={"evaluator": evaluator})
        return SessionLaunch(
            context=updated_context,
            messages=[
                ChatTurn(
                    speaker="Interviewer",
                    content="Thanks. Can you expand on delivery trade-offs?",
                    tone="neutral",
                    competency="Collaboration",
                    targeted_criteria=["Delivery"],
                    project_anchor="Primer project",
                )
            ],
        )

    monkeypatch.setattr(api_server, "DATA_PATH", db_path)
    config_path = tmp_path / "config.json"
    _write_config(config_path)
    monkeypatch.setattr(api_server, "CONFIG_PATH", config_path)
    monkeypatch.setattr(api_server, "advance_session_with_config", fake_advance_session)

    client = TestClient(api_server.app)
    reply_response = client.post(
        f"/api/interviews/{interview_id}/session/reply",
        json={
            "candidate_id": candidate_id,
            "question": "How do you keep stakeholders aligned?",
            "answer": "I schedule recurring alignment forums with clear agendas and shared artifacts.",
            "tone": "neutral",
            "stage": "warmup",
            "auto_answer_enabled": True,
            "candidate_level": 3,
            "qa_history": [],
            "competency": "Collaboration",
            "competency_index": 0,
            "question_index": 0,
            "project_anchor": "Primer project",
            "competency_projects": {"Collaboration": "Primer project"},
            "competency_criteria": {"Collaboration": ["Communication", "Stakeholders", "Delivery"]},
            "competency_criterion_levels": {"Collaboration": {"Communication": 2}},
            "competency_covered": {"Collaboration": []},
            "competency_question_counts": {"Collaboration": 0},
            "competency_low_scores": {"Collaboration": 0},
            "targeted_criteria": ["Stakeholders"],
        },
    )
    assert reply_response.status_code == 200

    report_response = client.get(
        f"/api/interviews/{interview_id}/sessions/{candidate_id}/report"
    )
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["interview_id"] == interview_id
    assert report["candidate_id"] == candidate_id
    assert report["overall_score"] == 3.5
    assert report["competency_scores"][0]["competency"] == "Collaboration"
    assert report["competency_scores"][0]["score"] == 3.5
    assert report["criterion_scores"][0]["level"] == 4
    assert report["exchanges"][0]["question"] == "How do you keep stakeholders aligned?"
    assert "Stakeholders" in report["exchanges"][0]["system_message"]
    assert report["rubric"]["interview_id"] == interview_id

    pdf_response = client.get(
        f"/api/interviews/{interview_id}/sessions/{candidate_id}/report.pdf"
    )
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"].startswith("application/pdf")
    assert pdf_response.content.startswith(b"%PDF")


def test_rubric_pdf_download(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "rubrics.sqlite"
    store = RubricStore(db_path)
    interview_id = "pdf-role"
    store.save(
        interview_id=interview_id,
        job_title="Staff Engineer",
        experience_years="7-10",
        job_description="Designs resilient distributed systems and mentors engineers.",
        rubrics=[_rubric()],
    )
    monkeypatch.setattr(api_server, "DATA_PATH", db_path)
    client = TestClient(api_server.app)
    response = client.get(f"/api/interviews/{interview_id}/rubric.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["content-disposition"].endswith('.pdf"')
    assert response.content.startswith(b"%PDF")
