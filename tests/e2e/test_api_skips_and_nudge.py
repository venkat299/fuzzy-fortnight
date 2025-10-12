from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import router


app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_three_skips_trigger_nudge(fake_models):
    start = client.post(
        "/api/interview-sessions/start", json={"interview_id": "i3", "candidate_id": "c3"}
    ).json()
    session_id = start["session_id"]

    for _ in range(3):
        resp = client.post(
            "/api/interview-sessions/turn", json={"session_id": session_id, "quick_action": {"id": "skip"}}
        )
        assert resp.status_code == 200

    final = client.post(
        "/api/interview-sessions/turn", json={"session_id": session_id}
    )
    assert final.status_code == 200
    assert final.json()["quick_actions"] == ["hint", "think_30"]
