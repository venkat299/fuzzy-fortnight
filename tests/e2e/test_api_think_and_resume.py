from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import router
from graph.checkpointer import load_checkpoint, save_checkpoint


app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_think_and_resume(fake_models):
    start = client.post(
        "/api/interview-sessions/start", json={"interview_id": "i2", "candidate_id": "c2"}
    ).json()
    session_id = start["session_id"]

    think_resp = client.post(
        "/api/interview-sessions/turn", json={"session_id": session_id, "quick_action": {"id": "think_30"}}
    )
    assert think_resp.status_code == 200

    state = load_checkpoint(session_id)
    state.mem["think_until"] = "2000-01-01T00:00:00Z"
    save_checkpoint(state)

    resume_resp = client.post(
        "/api/interview-sessions/turn", json={"session_id": session_id}
    )
    assert resume_resp.status_code == 200
    payload = resume_resp.json()
    assert payload["ui_messages"]
    assert payload["question"] is not None
