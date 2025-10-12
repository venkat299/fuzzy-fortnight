from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import router
from config.registry import bind_model


app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_full_flow(fake_models):
    bind_model(
        "models.response_evaluator",
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
            "notes": "ok",
        },
    )

    start_resp = client.post(
        "/api/interview-sessions/start",
        json={"interview_id": "i1", "candidate_id": "c1"},
    )
    assert start_resp.status_code == 200
    session_id = start_resp.json()["session_id"]

    turn_resp = client.post(
        "/api/interview-sessions/turn",
        json={"session_id": session_id, "user_msg": "Detailed answer covering trade-offs."},
    )
    assert turn_resp.status_code == 200
    body = turn_resp.json()
    assert "question" in body and body["question"] is not None
    assert body.get("live_scores") is not None

    finish_resp = client.post(
        "/api/interview-sessions/finish", json={"session_id": session_id}
    )
    assert finish_resp.status_code == 200
    assert "live_scores" in finish_resp.json()
