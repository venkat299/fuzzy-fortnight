"""Graph execution helpers."""
from __future__ import annotations

from typing import Any, Dict, Optional

from observability.logger import log_event
from observability.tracing import span

from .state import GraphState
from .nodes import behavior_monitor, flow_manager, intent_classifier


def step(state: GraphState) -> Dict[str, Any]:
    """Execute a single LangGraph step for the provided state."""

    log_event("step.start", state.session_id, stage=state.stage)

    with span(state, "behavior_monitor"):
        log_event("node.start", state.session_id, node="behavior_monitor")
        monitor_result = behavior_monitor.run(state)
    log_event(
        "node.end",
        state.session_id,
        node="behavior_monitor",
        outcome=monitor_result.action,
        severity=monitor_result.severity,
    )

    if monitor_result.action != "ALLOW":
        if monitor_result.action == "BLOCK_AND_REFOCUS" and state.blocks_in_row >= 3:
            state.events.append({"type": "AUTO_SKIP_NEXT"})
        payload: Dict[str, Any] = {
            "ui_messages": [monitor_result.safe_reply] if monitor_result.safe_reply else [],
            "quick_actions": monitor_result.quick_actions or None,
            "state": state.model_dump(),
        }
        log_event(
            "step.end",
            state.session_id,
            stage=state.stage,
            decision="monitor_gate",
            action=monitor_result.action,
        )
        return payload

    with span(state, "intent_classifier"):
        log_event("node.start", state.session_id, node="intent_classifier")
        intent_result = intent_classifier.run(state)
    log_event(
        "node.end",
        state.session_id,
        node="intent_classifier",
        intent=intent_result.intent,
        confidence=intent_result.confidence,
    )

    with span(state, "flow_manager"):
        log_event("node.start", state.session_id, node="flow_manager")
        flow_decision = flow_manager.run(state)
    log_event(
        "node.end",
        state.session_id,
        node="flow_manager",
        decision=flow_decision.type,
    )

    log_event("step.end", state.session_id, stage=state.stage, decision=flow_decision.type)
    return {
        "decision": flow_decision.model_dump(),
        "state": state.model_dump(),
    }


def run_graph_turn(
    state: GraphState,
    user_msg: Optional[str] = None,
    quick_action: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Coordinate priority routing between quick actions and user input."""

    if quick_action and user_msg:
        state.quick_action = quick_action
        state.queued_user_msg = user_msg
        state.user_msg = None
    else:
        state.quick_action = quick_action
        if quick_action is None and user_msg is None and state.queued_user_msg:
            state.user_msg = state.queued_user_msg
            state.queued_user_msg = None
        else:
            state.user_msg = user_msg

    result = step(state)

    if quick_action and user_msg and state.queued_user_msg is None:
        state.queued_user_msg = user_msg

    return result
