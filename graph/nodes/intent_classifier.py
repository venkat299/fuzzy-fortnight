"""Graph adapter for the intent classifier agent."""
from __future__ import annotations

from agents.intent_classifier import classify_intent


def run(state):
    """Classify the latest user message and annotate the state."""
    message = state.user_msg or ""
    result = classify_intent(
        stage=state.stage,
        question_text=state.question_text or "",
        user_msg=message,
    )
    state.latest_intent = result.intent
    state.events.append({"node": "intent", "intent": result.intent, "conf": result.confidence})
    return result
