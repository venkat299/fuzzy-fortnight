"""Tests for the SQLite migration and write helpers."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile

import pytest

from config.settings import settings
from storage.actions import insert_quick_action
from storage.flags import insert_interview_flag
from storage.migrate import migrate
from storage.scores import (
    insert_score,
    insert_scores_overall,
    insert_scores_summary,
)


@pytest.fixture()
def temp_db(monkeypatch: pytest.MonkeyPatch):
    """Provide a temporary database path for each test."""

    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "test.db")
        monkeypatch.setattr(settings, "DB_PATH", db_path, raising=False)
        yield db_path


def test_migrate_and_inserts(temp_db: str):
    migrate(temp_db)
    assert os.path.exists(temp_db)

    flag_id = insert_interview_flag(
        interview_id="i1",
        candidate_id="c1",
        stage="warmup",
        question_id="q1",
        action="REDIRECT",
        severity="info",
        reason_codes=["off_topic"],
        raw_text="offtopic",
        safe_reply="Let's refocus.",
        skip_streak=0,
        metadata={"k": "v"},
    )
    assert flag_id > 0

    action_id = insert_quick_action(
        interview_id="i1",
        candidate_id="c1",
        stage="warmup",
        question_id="q1",
        action_id="hint",
        source="standard",
        latency_ms=123,
        metadata={"skip_streak": 1, "remaining_hints": 2},
    )
    assert action_id > 0

    score_id = insert_score(
        interview_id="i1",
        candidate_id="c1",
        competency="ARCH",
        item_id="ARCH_01",
        best_of_score=4.0,
        turn_scores_json={"turns": [{"overall": 3.7}, {"overall": 4.0}]},
    )
    assert score_id > 0

    summary_id = insert_scores_summary(
        interview_id="i1",
        candidate_id="c1",
        competency="ARCH",
        avg_score=3.9,
        median_score=4.0,
        max_score=5.0,
        attempted_count=3,
        skipped_count=1,
    )
    assert summary_id > 0

    overall_id = insert_scores_overall(
        interview_id="i1",
        candidate_id="c1",
        avg_score=4.1,
        median_score=4.0,
        max_score=5.0,
    )
    assert overall_id > 0

    with sqlite3.connect(temp_db) as conn:
        cur = conn.cursor()
        cur.execute("SELECT interview_id, metadata FROM interview_flags WHERE id=?", (flag_id,))
        row = cur.fetchone()
        assert row == ("i1", json.dumps({"k": "v"}))

        cur.execute("SELECT action_id, metadata FROM quick_actions WHERE id=?", (action_id,))
        row = cur.fetchone()
        assert row == ("hint", json.dumps({"skip_streak": 1, "remaining_hints": 2}))

        cur.execute("SELECT competency, turn_scores_json FROM scores WHERE id=?", (score_id,))
        row = cur.fetchone()
        assert row == ("ARCH", json.dumps({"turns": [{"overall": 3.7}, {"overall": 4.0}]}))

        cur.execute(
            "SELECT competency, avg_score, median_score, max_score FROM scores_summary WHERE id=?",
            (summary_id,),
        )
        row = cur.fetchone()
        assert row == ("ARCH", 3.9, 4.0, 5.0)

        cur.execute(
            "SELECT avg_score, median_score, max_score FROM scores_overall WHERE id=?",
            (overall_id,),
        )
        row = cur.fetchone()
        assert row == (4.1, 4.0, 5.0)


def test_invalid_payloads_raise(temp_db: str):
    migrate(temp_db)

    with pytest.raises(Exception):
        insert_interview_flag(  # type: ignore[arg-type]
            interview_id="i1",
            candidate_id="c1",
            stage="warmup",
            question_id="q1",
            action="REDIRECT",
            severity="info",
            reason_codes="off_topic",  # not a list
            raw_text="offtopic",
            safe_reply="Let's refocus.",
        )

    with pytest.raises(Exception):
        insert_quick_action(  # type: ignore[arg-type]
            interview_id="i1",
            candidate_id="c1",
            stage="warmup",
            question_id="q1",
            action_id="hint",
            source="standard",
            latency_ms="fast",  # not an int
        )

    with pytest.raises(Exception):
        insert_score(  # type: ignore[arg-type]
            interview_id="i1",
            candidate_id="c1",
            competency="ARCH",
            item_id="ARCH_01",
            best_of_score="great",  # not a float
        )
