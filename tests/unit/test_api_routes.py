from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import router
from agents.hint_agent import HINT_KEY
from agents.response_evaluator import EVAL_KEY
from config.registry import INTENT_KEY, MONITOR_KEY, bind_model


def _bind_defaults():
    bind_model(
        MONITOR_KEY,
        lambda **_: {
            "action": "ALLOW",
            "severity": "info",
            "reason_codes": [],
            "rationale": "ok",
            "safe_reply": "",
            "quick_actions": [],
            "proceed_to_intent_classifier": True,
        },
    )
    bind_model(
        INTENT_KEY,
        lambda **_: {"intent": "answer", "confidence": 0.9, "rationale": "stub"},
    )
    bind_model(
        EVAL_KEY,
        lambda **_: {
            "competency_id": "ARCH",
            "item_id": "ARCH_01",
            "turn_index": 0,
            "criterion_scores": [
                {"id": "C1", "score": 4},
                {"id": "C2", "score": 3},
                {"id": "C3", "score": 4},
            ],
            "overall": 3.7,
            "band": "mid",
            "notes": "stub",
        },
    )
    bind_model(
        HINT_KEY,
        lambda **kwargs: {
            "hint": "Focus on your role, a key decision, and a measurable outcome."
        },
    )


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_start_turn_finish_cycle(fake_models):
    _bind_defaults()
    client = _client()

    start_payload = client.post(
        "/api/interview-sessions/start",
        json={"interview_id": "INT-1", "candidate_id": "CAND-1"},
    ).json()

    turn_payload = client.post(
        "/api/interview-sessions/turn",
        json={"session_id": start_payload["session_id"], "user_msg": "Answer with depth."},
    ).json()

    assert turn_payload["question"] is not None
    assert turn_payload["live_scores"] is not None

    finish_payload = client.post(
        "/api/interview-sessions/finish", json={"session_id": start_payload["session_id"]}
    ).json()
    assert finish_payload["quick_actions"] == []
    assert finish_payload["live_scores"] is not None
