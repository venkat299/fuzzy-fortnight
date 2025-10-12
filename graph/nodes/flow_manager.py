"""Adapter that wires dependencies for the flow manager agent."""
from __future__ import annotations

from datetime import datetime

from agents.flow_manager import FlowConfig, FlowDeps, handle_after_monitor_and_intent
from graph.state import GraphState


def run(state: GraphState):
    from agents.qg import competency, warmup, wrapup

    router_map = {
        "warmup": warmup.run,
        "competency": competency.run,
        "wrapup": wrapup.run,
    }
    stage_router = router_map.get(state.stage, warmup.run)

    deps = FlowDeps(
        qg_router=stage_router,
        evaluator=None,
        now=datetime.utcnow,
    )
    cfg = FlowConfig()

    decision = handle_after_monitor_and_intent(state, deps, cfg)
    state.events.append({"node": "flow", "decision": decision.type})
    return decision


__all__ = ["run"]
