from __future__ import annotations  # Interview flow orchestration using LangGraph

from pathlib import Path
from typing import Any, Dict, List, Tuple, Type

from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from config import LlmRoute, load_app_registry
from .agents import WARMUP_AGENT_KEY, WarmupAgent, WarmupPlan
from .models import ChatTurn, FlowState, InterviewContext, SessionLaunch


def start_session(
    context: InterviewContext,
    *,
    registry: Dict[str, Tuple[LlmRoute, Type[BaseModel]]],
) -> SessionLaunch:  # Run the flow graph with a provided registry
    state = FlowState(context=context, messages=[])
    agent = _warmup_agent(registry)
    graph = StateGraph(dict)
    graph.add_node("router", _identity)
    graph.add_node("warmup", lambda payload: agent.invoke(_ensure_state(payload)).model_dump())
    graph.add_edge("warmup", END)
    graph.add_conditional_edges(
        "router",
        lambda payload: _route_stage(_ensure_state(payload)),
        {
            "warmup": "warmup",
            "end": END,
        },
    )
    graph.set_entry_point("router")
    compiled = graph.compile()
    final_payload = compiled.invoke(state.model_dump())
    final_state = FlowState.model_validate(final_payload)
    return SessionLaunch(context=final_state.context, messages=final_state.messages)


def start_session_with_config(
    context: InterviewContext,
    *,
    config_path: Path,
) -> SessionLaunch:  # Convenience helper loading registry from config file
    schemas: Dict[str, Type[BaseModel]] = {WARMUP_AGENT_KEY: WarmupPlan}
    registry = load_app_registry(config_path, schemas)
    return start_session(context, registry=registry)


def advance_session(
    context: InterviewContext,
    history: List[ChatTurn],
    *,
    registry: Dict[str, Tuple[LlmRoute, Type[BaseModel]]],
) -> SessionLaunch:  # Produce next flow turn given accumulated history
    state = FlowState(context=context, messages=list(history))
    agent = _warmup_agent(registry)
    updated = agent.invoke(state)
    existing = len(history)
    if existing >= len(updated.messages):
        return SessionLaunch(context=updated.context, messages=[])
    return SessionLaunch(context=updated.context, messages=updated.messages[existing:])


def advance_session_with_config(
    context: InterviewContext,
    history: List[ChatTurn],
    *,
    config_path: Path,
) -> SessionLaunch:  # Convenience helper for advancing the flow using config file
    schemas: Dict[str, Type[BaseModel]] = {WARMUP_AGENT_KEY: WarmupPlan}
    registry = load_app_registry(config_path, schemas)
    return advance_session(context, history, registry=registry)


def _warmup_agent(registry: Dict[str, Tuple[LlmRoute, Type[BaseModel]]]) -> WarmupAgent:  # Build warmup agent from registry
    if WARMUP_AGENT_KEY not in registry:
        raise KeyError(f"Registry missing {WARMUP_AGENT_KEY}")
    route, schema = registry[WARMUP_AGENT_KEY]
    if not issubclass(schema, WarmupPlan):
        raise TypeError("Warmup agent schema must extend WarmupPlan")
    return WarmupAgent(route, schema)  # type: ignore[arg-type]


def _route_stage(state: FlowState) -> str:  # Route state to warmup or end nodes
    if state.context.stage.lower() == "warmup":
        return "warmup"
    return "end"


def _identity(payload: Dict[str, Any]) -> Dict[str, Any]:  # Identity node required by LangGraph entry
    return payload


def _ensure_state(payload: FlowState | Dict[str, Any]) -> FlowState:  # Normalize payload into FlowState
    if isinstance(payload, FlowState):
        return payload
    if isinstance(payload, dict):
        return FlowState.model_validate(payload)
    raise TypeError("Unsupported state payload")


__all__ = [
    "advance_session",
    "advance_session_with_config",
    "ChatTurn",
    "InterviewContext",
    "SessionLaunch",
    "WarmupPlan",
    "start_session",
    "start_session_with_config",
]
