import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import router
from config.registry import bind_model, MONITOR_KEY
from config.settings import settings


app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_flag_logging(fake_models):
    bind_model(
        MONITOR_KEY,
        lambda **_: {
            "action": "REDIRECT",
            "severity": "low",
            "reason_codes": ["off_topic"],
            "rationale": "offtopic",
            "safe_reply": "Let’s refocus.",
            "quick_actions": ["hint", "repeat"],
            "proceed_to_intent_classifier": False,
        },
    )

    start = client.post(
        "/api/interview-sessions/start", json={"interview_id": "i4", "candidate_id": "c4"}
    ).json()
    session_id = start["session_id"]

    resp = client.post(
        "/api/interview-sessions/turn", json={"session_id": session_id, "user_msg": "salary?"}
    )
    assert resp.status_code == 200

    conn = sqlite3.connect(settings.DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT action, severity FROM interview_flags ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    assert row == ("REDIRECT", "low")
