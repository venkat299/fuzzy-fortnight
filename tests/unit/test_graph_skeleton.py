"""Tests for the LangGraph skeleton."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agents.response_evaluator import EVAL_KEY
from config.registry import INTENT_KEY, MONITOR_KEY, bind_model
from graph.checkpointer import BASE_DIR as DEFAULT_BASE_DIR
from graph import checkpointer
from graph.build import run_graph_turn, step
from graph.state import GraphState


@pytest.fixture(autouse=True)
def bind_monitor_model():
    def stub_monitor(**kwargs):
        forced = kwargs.get("forced_action", "ALLOW")
        return {
            "action": forced,
            "severity": "info" if forced == "ALLOW" else "low",
            "reason_codes": [],
            "rationale": "stub",
            "safe_reply": "",
            "quick_actions": [],
            "proceed_to_intent_classifier": forced == "ALLOW",
        }

    bind_model(MONITOR_KEY, stub_monitor)
    yield


@pytest.fixture(autouse=True)
def bind_intent_model():
    def stub_intent(**kwargs):
        return {
            "intent": "answer",
            "confidence": 0.95,
            "rationale": "test stub",
        }

    bind_model(INTENT_KEY, stub_intent)
    yield


@pytest.fixture(autouse=True)
def bind_eval_model():
    def stub_eval(**kwargs):
        inputs = kwargs.get("inputs", {})
        followup_index = inputs.get("followup_index", 0)
        return {
            "competency_id": inputs.get("competency_id", "ARCH"),
            "item_id": inputs.get("item_id", "ARCH_01"),
            "turn_index": followup_index,
            "criterion_scores": [
                {"id": "C1", "score": 4},
                {"id": "C2", "score": 4},
                {"id": "C3", "score": 3},
            ],
            "overall": 3.7,
            "band": "mid",
            "notes": "stub eval",
        }

    bind_model(EVAL_KEY, stub_eval)
    yield


@pytest.fixture(autouse=True)
def override_checkpoints(tmp_path, monkeypatch):
    base_dir = tmp_path / "checkpoints"
    monkeypatch.setattr(checkpointer, "BASE_DIR", str(base_dir))
    yield
    monkeypatch.setattr(checkpointer, "BASE_DIR", DEFAULT_BASE_DIR)


def _load_checkpoint(session_id: str) -> GraphState | None:
    path = Path(checkpointer.BASE_DIR) / f"{session_id}.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return GraphState(**data)


def test_first_turn_triggers_question():
    state = GraphState(session_id="s1", interview_id="i1", candidate_id="c1")

    result = step(state)

    assert result["decision"]["type"] == "ASK"
    checkpoint_state = _load_checkpoint("s1")
    assert checkpoint_state is not None
    assert checkpoint_state.question_id == "WU_01"


def test_answer_flow_evaluates_and_asks_next(tmp_path):
    state = GraphState(session_id="s2", interview_id="i2", candidate_id="c2")
    state.rubric = {
        "criteria": [
            {"id": "C1", "weight": 0.34},
            {"id": "C2", "weight": 0.33},
            {"id": "C3", "weight": 0.33},
        ]
    }

    first = step(state)
    assert first["decision"]["type"] == "ASK"

    response = run_graph_turn(
        state,
        user_msg="I led the migration by planning milestones, coordinating engineers, and delivering measurable impact.",
        quick_action=None,
    )

    assert response["decision"]["type"] in {"ASK", "EVAL_AND_ASK_NEXT"}
    checkpoint_state = _load_checkpoint("s2")
    assert checkpoint_state is not None
    assert checkpoint_state.question_id is not None
    assert checkpoint_state.last_eval is not None


def test_quick_action_priority_queues_message():
    state = GraphState(session_id="s3", interview_id="i3", candidate_id="c3")

    step(state)
    state.user_msg = None

    detailed_reply = (
        "Here is a detailed response sharing specific actions, impact, outcomes, and leadership growth."
    )
    result = run_graph_turn(
        state,
        user_msg=detailed_reply,
        quick_action={"id": "repeat"},
    )

    assert result["decision"]["type"] == "REASK"
    assert state.queued_user_msg == detailed_reply
    assert state.user_msg is None

    follow_up = run_graph_turn(state)
    assert follow_up["decision"]["type"] in {"ASK", "EVAL_AND_ASK_NEXT"}


def test_checkpoint_round_trip(tmp_path):
    state = GraphState(
        session_id="s4",
        interview_id="i4",
        candidate_id="c4",
        stage="competency",
        question_id="COMP_01",
        question_text="Describe a challenge",
        persona="Direct Coach",
        rubric={"k": "v"},
        mem={"facts": [1, 2, 3]},
    )

    path = checkpointer.save_checkpoint(state)
    assert os.path.exists(path)

    loaded = checkpointer.load_checkpoint("s4")
    assert loaded == state
