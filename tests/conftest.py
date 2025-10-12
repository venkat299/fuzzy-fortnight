import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage.migrate import migrate
from config.settings import settings
from config.registry import bind_model, INTENT_KEY, MONITOR_KEY


@pytest.fixture(autouse=True)
def tmp_db(monkeypatch):
    td = tempfile.TemporaryDirectory()
    db_path = os.path.join(td.name, "test.db")
    monkeypatch.setattr(settings, "DB_PATH", db_path, raising=False)
    migrate(db_path)
    try:
        yield
    finally:
        td.cleanup()


@pytest.fixture
def fake_models():
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
        lambda **_: {
            "intent": "answer",
            "confidence": 0.9,
            "rationale": "ok",
        },
    )
    return True
