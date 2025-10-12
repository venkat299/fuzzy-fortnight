"""Unit tests for the intent classifier agent."""
from __future__ import annotations

from agents.intent_classifier import classify_intent
from config.registry import INTENT_KEY, bind_model


def fake_intent_llm_answer(**kwargs):
    return {"intent": "answer", "confidence": 0.92, "rationale": "direct evidence"}


def fake_intent_llm_lowconf(**kwargs):
    return {"intent": "answer", "confidence": 0.41, "rationale": "uncertain"}


def fake_intent_llm_hint(**kwargs):
    return {"intent": "ask_hint", "confidence": 0.88, "rationale": "explicit hint request"}


def test_answer_high_conf(monkeypatch):
    bind_model(INTENT_KEY, fake_intent_llm_answer)
    result = classify_intent(stage="competency", question_text="Q", user_msg="We used idempotent handlers")
    assert result.intent == "answer"
    assert result.confidence > 0.60


def test_low_conf_coerces_to_clarify(monkeypatch):
    bind_model(INTENT_KEY, fake_intent_llm_lowconf)
    result = classify_intent(stage="competency", question_text="Q", user_msg="hmm maybe")
    assert result.intent == "ask_clarify"
    assert result.confidence < 0.60


def test_hint(monkeypatch):
    bind_model(INTENT_KEY, fake_intent_llm_hint)
    result = classify_intent(stage="warmup", question_text="Q", user_msg="could I get a hint?")
    assert result.intent == "ask_hint"
