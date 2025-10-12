"""Intent classifier agent backed by the model registry."""
from __future__ import annotations

from typing import Any, Dict

from pydantic import ValidationError

from agents.types import IntentResult
from config.registry import INTENT_KEY, get_model

CONF_THRESHOLD = 0.60


def _mk_inputs(*, stage: str, question_text: str, user_msg: str) -> Dict[str, Any]:
    """Assemble the structured payload passed to the LLM."""
    return {
        "stage": stage,
        "question_text": question_text,
        "user_msg": user_msg,
        "context": {},
        "policy": {"low_content_tokens": 12, "allow_shortcuts": False},
    }


def classify_intent(*, stage: str, question_text: str, user_msg: str) -> IntentResult:
    """Run the registry-bound LLM and coerce low-confidence outcomes."""
    llm = get_model(INTENT_KEY)
    raw = llm(
        system_prompt_path="prompts/intent_classifier.txt",
        inputs=_mk_inputs(stage=stage, question_text=question_text, user_msg=user_msg),
    )
    try:
        result = IntentResult.model_validate(raw)
    except ValidationError:
        result = IntentResult(intent="other", confidence=0.0, rationale="fallback parsing")

    if result.confidence < CONF_THRESHOLD:
        return IntentResult(intent="ask_clarify", confidence=result.confidence, rationale=result.rationale)
    return result
