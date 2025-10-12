"""Behavior monitor agent combining heuristics with LLM refinement."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from agents.persona_manager import apply_persona
from agents.types import MonitorResult
from config.safety import SafetyFinding, allow_terms, match_categories
from config.registry import MONITOR_KEY, get_model
from config.settings import settings
from storage.flags import insert_interview_flag


def token_count(text: Optional[str]) -> int:
    """Approximate token count using whitespace splitting."""

    if not text:
        return 0
    return len(text.strip().split())


def cosine_to_topic_placeholder(_: str, __: Dict[str, Any]) -> float:
    """Placeholder cosine similarity until embeddings are wired."""

    return 0.70


def build_llm_inputs(
    *,
    stage: str,
    question_text: str,
    user_msg: str,
    counts: Dict[str, int],
    context_tags: List[str],
    cosine: float,
    safety_hits: List[str],
) -> Dict[str, Any]:
    """Assemble the payload forwarded to the behavior monitor LLM."""

    return {
        "stage": stage,
        "question_text": question_text,
        "user_msg": user_msg,
        "embeddings": {"cosine_to_topic": cosine},
        "counts": counts,
        "settings": {
            "thresholds": {
                "off_topic_cutoff": settings.OFF_TOPIC_CUTOFF,
                "low_content_tokens": settings.LOW_CONTENT_TOKENS,
            },
            "think_seconds": settings.THINK_SECONDS,
            "hints_cap_per_stage": settings.HINTS_PER_STAGE,
        },
        "context_tags": context_tags,
        "safety_hits": safety_hits,
        "allowlist_enabled_terms": allow_terms(),
    }


def choose_severity(reason_codes: List[str], repeat_blocks: int) -> str:
    """Derive severity based on reason codes and block streak."""

    if "unsafe" in reason_codes:
        return "critical"
    if "jailbreak" in reason_codes:
        return "high" if repeat_blocks < 2 else "critical"
    if "off_topic" in reason_codes or "low_content" in reason_codes:
        return "low"
    if "silence" in reason_codes:
        return "info"
    return "info"


def _persona_purpose_for(action: str) -> Optional[str]:
    mapping = {
        "REMIND": "remind",
        "NUDGE_DEPTH": "nudge_depth",
        "REDIRECT": "redirect",
        "BLOCK_AND_REFOCUS": "block_refocus",
    }
    return mapping.get(action)


def _default_safe_reply_core(action: str) -> str:
    if action == "NUDGE_DEPTH":
        return "Could you add what you did, a key decision, and the outcome?"
    if action == "REDIRECT":
        return "Could you walk me through that project instead?"
    if action == "BLOCK_AND_REFOCUS":
        return "Let’s keep exploring your experience with this question."
    return ""


def default_quick_actions(action: str, skip_streak: int) -> List[str]:
    """Default quick action palette when the LLM omits recommendations."""

    if action == "REMIND":
        return ["hint", "think_30", "repeat", "skip"]
    if action == "REDIRECT":
        return ["hint", "repeat", "skip"]
    if action == "NUDGE_DEPTH":
        return ["hint", "repeat", "skip"]
    if action == "BLOCK_AND_REFOCUS":
        return ["repeat"]
    return []


def run_monitor(
    *,
    interview_id: str,
    candidate_id: str,
    stage: str,
    question_id: str,
    question_text: str,
    user_msg: Optional[str],
    skip_streak: int,
    blocks_in_row: int,
    hints_used_stage: int,
    context_tags: Optional[List[str]] = None,
    cosine_provider=cosine_to_topic_placeholder,
) -> MonitorResult:
    """Evaluate the user message and decide whether to allow downstream processing."""

    context_tags = context_tags or []

    if user_msg is None:
        counts = {
            "skip_streak": skip_streak,
            "blocks_in_row": blocks_in_row,
            "hints_used_stage": hints_used_stage,
        }
        monitor_llm = get_model(MONITOR_KEY)
        raw = monitor_llm(
            system_prompt_path="prompts/behavior_monitor.txt",
            inputs=build_llm_inputs(
                stage=stage,
                question_text=question_text,
                user_msg="",
                counts=counts,
                context_tags=context_tags,
                cosine=1.0,
                safety_hits=[],
            ),
            forced_action="ALLOW",
        )
        result = MonitorResult.model_validate(raw)
        result.quick_actions = []
        result.proceed_to_intent_classifier = True
        return result

    msg = user_msg
    token_len = token_count(msg)
    cosine = cosine_provider(
        msg,
        {"stage": stage, "question_id": question_id, "question_text": question_text},
    )
    finding: SafetyFinding = match_categories(msg, context_tags)

    reason_codes: List[str] = []
    action = "ALLOW"
    severity_override: Optional[str] = None

    if finding.allow_list_reason:
        finding = SafetyFinding(category=None, severity="info", hits=[])

    if not msg.strip() or msg.strip() in {"…", "..."}:
        action = "REMIND"
        reason_codes = ["silence"]
    elif finding.category == "unsafe":
        action = "BLOCK_AND_REFOCUS"
        reason_codes = ["unsafe"]
        severity_override = finding.severity
    elif finding.category == "jailbreak":
        action = "BLOCK_AND_REFOCUS"
        reason_codes = ["jailbreak"]
        severity_override = finding.severity
    elif finding.category == "pii":
        action = "REDIRECT"
        reason_codes = ["unsafe"]
        severity_override = finding.severity
    elif finding.category == "offtopic":
        action = "REDIRECT"
        reason_codes = ["off_topic"]
        severity_override = finding.severity
    elif cosine < settings.OFF_TOPIC_CUTOFF:
        action = "REDIRECT"
        reason_codes = ["off_topic"]
    elif token_len < settings.LOW_CONTENT_TOKENS:
        action = "NUDGE_DEPTH"
        reason_codes = ["low_content"]

    severity = severity_override or choose_severity(reason_codes, blocks_in_row)

    counts = {
        "skip_streak": skip_streak,
        "blocks_in_row": blocks_in_row,
        "hints_used_stage": hints_used_stage,
    }

    monitor_llm = get_model(MONITOR_KEY)
    safety_patterns = [hit.pattern for hit in finding.hits]
    llm_inputs = build_llm_inputs(
        stage=stage,
        question_text=question_text,
        user_msg=msg,
        counts=counts,
        context_tags=context_tags,
        cosine=cosine,
        safety_hits=safety_patterns,
    )

    raw = monitor_llm(
        system_prompt_path="prompts/behavior_monitor.txt",
        inputs=llm_inputs,
        forced_action=action,
    )

    try:
        result = MonitorResult.model_validate(raw)
    except ValidationError:
        result = MonitorResult(
            action=action,
            severity=severity,
            reason_codes=reason_codes,
            rationale="schema fallback",
            safe_reply=_default_safe_reply_core(action),
            quick_actions=default_quick_actions(action, skip_streak),
            proceed_to_intent_classifier=action == "ALLOW",
        )
    else:
        if not result.reason_codes and reason_codes:
            result.reason_codes = reason_codes
        if not result.safe_reply:
            result.safe_reply = _default_safe_reply_core(result.action)
        if result.action != "ALLOW":
            defaults = default_quick_actions(result.action, skip_streak)
            if result.quick_actions:
                merged: List[str] = []
                for item in result.quick_actions + defaults:
                    if item not in merged:
                        merged.append(item)
                result.quick_actions = merged
            else:
                result.quick_actions = defaults
            result.proceed_to_intent_classifier = False
        result.severity = severity

    purpose = _persona_purpose_for(result.action)
    if purpose:
        core_text = result.safe_reply or _default_safe_reply_core(result.action)
        result.safe_reply = apply_persona(core_text, purpose=purpose)

    if result.action != "ALLOW":
        insert_interview_flag(
            interview_id=interview_id,
            candidate_id=candidate_id,
            stage=stage,
            question_id=question_id or "NA",
            action=result.action,
            severity=result.severity,
            reason_codes=result.reason_codes,
            raw_text=msg,
            safe_reply=result.safe_reply,
            skip_streak=skip_streak,
            metadata={
                "cosine": cosine,
                "token_count": token_len,
                "safety_hits": safety_patterns,
            },
        )

    return result


__all__ = ["run_monitor"]
