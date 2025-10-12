"""Interview flow management policies and routing."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Literal, Optional

from pydantic import BaseModel, Field

from agents.persona_manager import apply_persona
from agents.qg.common import QGContext, FacetStatus, HIGH_SATISFIED
from agents.response_evaluator import score_turn
from services import scoring

DecisionType = Literal[
    "ASK",
    "REASK",
    "HINT",
    "PAUSE_THINK",
    "SKIP_AND_NEXT",
    "EVAL_AND_ASK_NEXT",
    "AUTO_SKIP_MOVED",
    "CLARIFY",
]


class FlowDecision(BaseModel):
    """Decision payload returned to the UI adapter."""

    type: DecisionType
    payload: Dict[str, Any] = Field(default_factory=dict)


class FlowConfig(BaseModel):
    hints_per_stage: int = 2
    think_seconds: int = 30
    max_followups_per_item: int = 2
    nudge_after_consecutive_skips: int = 3


class FlowDeps(BaseModel):
    qg_router: Callable[[QGContext], Optional[Any]]
    evaluator: Optional[Callable[[Any, str], Any]] = None
    now: Callable[[], datetime]


_STAGE_DEFAULTS: Dict[str, Dict[str, str]] = {
    "warmup": {
        "competency_id": "WARMUP",
        "item_id": "WU_01",
        "facet_id": "WU1",
        "facet_name": "Context & Outcome",
    },
    "competency": {
        "competency_id": "ARCH",
        "item_id": "ARCH_01",
        "facet_id": "F_BOUNDARIES",
        "facet_name": "Decomposition & Boundaries",
    },
    "wrapup": {
        "competency_id": "WRAP",
        "item_id": "WR_01",
        "facet_id": "WU-END",
        "facet_name": "Reflection",
    },
}


def _save_checkpoint(state: Any) -> None:
    from graph.checkpointer import save_checkpoint

    save_checkpoint(state)


def _ensure_stage_defaults(state: Any) -> None:
    scoring.attach_cache(state)
    defaults = _STAGE_DEFAULTS.get(state.stage, {})
    for key, value in defaults.items():
        state.mem.setdefault(key, value)
    state.mem.setdefault("followup_index", 0)


def _attach_live_scores(payload: Dict[str, Any], state: Any) -> None:
    try:
        live = scoring.live_scores(state)
    except Exception:  # pragma: no cover - defensive
        return
    live_dict = live.model_dump()
    state.mem["live_scores"] = live_dict
    payload.setdefault("live_scores", live_dict)


def _finalize_decision(state: Any, decision: FlowDecision, cfg: FlowConfig) -> FlowDecision:
    if (
        decision.type in {"ASK", "EVAL_AND_ASK_NEXT", "AUTO_SKIP_MOVED"}
        and state.skip_streak >= cfg.nudge_after_consecutive_skips
    ):
        state.skip_streak = 0
    return decision


def _facet_best_of(state: Any) -> float:
    """Fetch the current best-of score for the active facet."""

    cache = scoring.attach_cache(state)
    comp_id = state.mem.get("competency_id") or _STAGE_DEFAULTS.get(state.stage, {}).get("competency_id")
    item_id = state.mem.get("item_id") or state.question_id
    if not comp_id or not item_id:
        return 1.0
    bucket = cache["competencies"].get(comp_id)
    if not bucket:
        return 1.0
    entry = bucket["items"].get(item_id)
    if not entry:
        return 1.0
    return float(entry.get("best_of", 1.0))


def _build_qg_ctx(state: Any, followup_index: int) -> QGContext:
    _ensure_stage_defaults(state)
    return QGContext(
        stage=state.stage,
        competency_id=state.mem["competency_id"],
        item_id=state.mem["item_id"],
        followup_index=followup_index,
        facet_id=state.mem["facet_id"],
        facet_name=state.mem["facet_name"],
        facet_status=FacetStatus(best_of_score=_facet_best_of(state)),
        persona=state.persona,
        candidate_facts=state.mem.get("entity_facts", {}),
    )


def _ask(state: Any, deps: FlowDeps, *, followup_index: int = 0) -> FlowDecision:
    ctx = _build_qg_ctx(state, followup_index)
    question = deps.qg_router(ctx)
    if question is None:
        return FlowDecision(
            type="AUTO_SKIP_MOVED",
            payload={"reason": "facet_satisfied"},
        )

    state.question_text = question.question_text
    state.question_id = question.metadata.item_id
    state.mem.update(
        {
            "competency_id": question.metadata.competency_id,
            "item_id": question.metadata.item_id,
            "facet_id": question.metadata.facet_id,
            "facet_name": question.metadata.facet_name,
            "followup_index": question.metadata.followup_index,
            "evidence_targets": question.metadata.evidence_targets,
        }
    )

    rendered = apply_persona(
        question.question_text,
        persona=state.persona,
        purpose="ask_question",
    )
    state.events.append(
        {
            "type": "ASK_QUESTION",
            "question_id": state.question_id,
            "followup_index": question.metadata.followup_index,
        }
    )
    _save_checkpoint(state)
    payload = {
        "question": {
            "text": rendered,
            "metadata": question.metadata.model_dump(),
        }
    }
    _attach_live_scores(payload, state)
    return FlowDecision(type="ASK", payload=payload)


def _reask(state: Any) -> FlowDecision:
    rendered = apply_persona(
        state.question_text or "",
        persona=state.persona,
        purpose="ask_question",
    )
    payload = {"question": {"text": rendered}}
    _attach_live_scores(payload, state)
    return FlowDecision(type="REASK", payload=payload)


def _handle_hint(state: Any, *, exhausted: bool = False) -> FlowDecision:
    from graph.nodes import hint_agent

    hint_text = hint_agent.run(state)
    payload = {"text": hint_text}
    if exhausted:
        payload["exhausted"] = True
    _attach_live_scores(payload, state)
    return FlowDecision(type="HINT", payload=payload)


def _handle_skip(state: Any, deps: FlowDeps, cfg: FlowConfig, *, reason: str) -> FlowDecision:
    state.skip_streak += 1
    current_comp = state.mem.get("competency_id") or _STAGE_DEFAULTS.get(state.stage, {}).get("competency_id", state.stage)
    current_item = state.mem.get("item_id") or state.question_id or ""
    scoring.mark_skip(state, current_comp, current_item)
    state.mem["followup_index"] = 0
    ask_decision = _ask(state, deps, followup_index=0)
    payload = {"reason": reason}
    if ask_decision.type == "ASK":
        payload.update(ask_decision.payload)
    if state.skip_streak >= cfg.nudge_after_consecutive_skips:
        payload["nudge"] = True
    _attach_live_scores(payload, state)
    return FlowDecision(type="SKIP_AND_NEXT", payload=payload)


def handle_after_monitor_and_intent(state: Any, deps: FlowDeps, cfg: FlowConfig) -> FlowDecision:
    """Entry point once the behavior monitor has allowed the turn."""

    # Quick-action priority
    if state.quick_action:
        action = state.quick_action
        state.quick_action = None
        aid = action.get("id")
        if aid == "repeat":
            return _finalize_decision(state, _reask(state), cfg)
        if aid == "hint":
            if state.hints_used_stage >= cfg.hints_per_stage:
                message = apply_persona(
                    "Give it a try—focus on your role, a key decision, and the outcome.",
                    persona=state.persona,
                    purpose="nudge_depth",
                )
                payload = {"text": message, "exhausted": True}
                _attach_live_scores(payload, state)
                return _finalize_decision(
                    state,
                    FlowDecision(type="HINT", payload=payload),
                    cfg,
                )
            state.hints_used_stage += 1
            return _finalize_decision(state, _handle_hint(state), cfg)
        if aid == "skip":
            return _finalize_decision(
                state,
                _handle_skip(state, deps, cfg, reason="user_skip"),
                cfg,
            )
        if aid == "think_30":
            until = (deps.now() + timedelta(seconds=cfg.think_seconds)).isoformat()
            state.mem["think_until"] = until
            payload = {"until": until}
            _attach_live_scores(payload, state)
            return _finalize_decision(
                state,
                FlowDecision(type="PAUSE_THINK", payload=payload),
                cfg,
            )

    if state.blocks_in_row >= 3:
        state.blocks_in_row = 0
        decision = _handle_skip(state, deps, cfg, reason="three_blocks")
        decision.type = "AUTO_SKIP_MOVED"
        return _finalize_decision(state, decision, cfg)

    intent = getattr(state, "latest_intent", None)

    if intent == "ask_hint":
        if state.hints_used_stage >= cfg.hints_per_stage:
            message = apply_persona(
                "Give it a try—focus on your role, a key decision, and the outcome.",
                persona=state.persona,
                purpose="nudge_depth",
            )
            payload = {"text": message, "exhausted": True}
            _attach_live_scores(payload, state)
            return _finalize_decision(
                state,
                FlowDecision(type="HINT", payload=payload),
                cfg,
            )
        state.hints_used_stage += 1
        return _finalize_decision(state, _handle_hint(state), cfg)

    if intent == "ask_think":
        until = (deps.now() + timedelta(seconds=cfg.think_seconds)).isoformat()
        state.mem["think_until"] = until
        payload = {"until": until}
        _attach_live_scores(payload, state)
        return _finalize_decision(
            state,
            FlowDecision(type="PAUSE_THINK", payload=payload),
            cfg,
        )

    if intent == "ask_pause":
        _save_checkpoint(state)
        text = apply_persona(
            "We can pause and resume when you’re ready.",
            persona=state.persona,
            purpose="remind",
        )
        payload = {"text": text}
        _attach_live_scores(payload, state)
        return _finalize_decision(
            state,
            FlowDecision(type="REASK", payload=payload),
            cfg,
        )

    if intent == "ask_clarify":
        text = apply_persona(
            "Do you want me to focus on scope A or B? If different, name it briefly.",
            persona=state.persona,
            purpose="clarify",
        )
        payload = {"text": text}
        _attach_live_scores(payload, state)
        return _finalize_decision(
            state,
            FlowDecision(type="CLARIFY", payload=payload),
            cfg,
        )

    if intent == "other":
        text = apply_persona(
            "Let’s refocus on the current topic.",
            persona=state.persona,
            purpose="redirect",
        )
        payload = {"text": text}
        _attach_live_scores(payload, state)
        return _finalize_decision(
            state,
            FlowDecision(type="REASK", payload=payload),
            cfg,
        )

    if not state.question_id:
        return _finalize_decision(state, _ask(state, deps, followup_index=0), cfg)

    if state.user_msg:
        evaluation = score_turn(
            competency_id=state.mem.get("competency_id", state.stage),
            item_id=state.mem.get("item_id", state.question_id or ""),
            followup_index=int(state.mem.get("followup_index", 0)),
            question_text=state.question_text or "",
            candidate_reply=state.user_msg,
            rubric=state.rubric,
            is_blocked=False,
        )
        scoring.record_eval(state, evaluation)
        state.last_eval = evaluation.model_dump()
        state.mem["last_reply_for_item"] = state.user_msg
        followup_index = int(state.mem.get("followup_index", 0))
        if (
            followup_index < cfg.max_followups_per_item
            and _facet_best_of(state) < HIGH_SATISFIED
        ):
            ask_decision = _ask(state, deps, followup_index=followup_index + 1)
            if ask_decision.type == "ASK":
                ask_decision.payload["eval"] = evaluation.model_dump()
                _attach_live_scores(ask_decision.payload, state)
            return _finalize_decision(state, ask_decision, cfg)
        payload = {"eval": evaluation.model_dump(), "moved": True}
        _attach_live_scores(payload, state)
        return _finalize_decision(
            state,
            FlowDecision(type="EVAL_AND_ASK_NEXT", payload=payload),
            cfg,
        )

    return _finalize_decision(state, _reask(state), cfg)


__all__ = [
    "FlowDecision",
    "FlowConfig",
    "FlowDeps",
    "handle_after_monitor_and_intent",
]
