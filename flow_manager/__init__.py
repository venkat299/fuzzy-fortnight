from __future__ import annotations  # Interview flow orchestration using LangGraph

from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple, Type

from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from config import FlowSettings, LlmRoute, load_config, resolve_registry
from .agents import (
    COMPETENCY_AGENT_KEY,
    CompetencyAgent,
    CompetencyPlan,
    EVALUATOR_AGENT_KEY,
    EvaluationPlan,
    EvaluatorAgent,
    WARMUP_AGENT_KEY,
    WarmupAgent,
    WarmupPlan,
)
from .models import (
    ChatTurn,
    CompetencyScore,
    FlowProgress,
    FlowState,
    InterviewContext,
    SessionLaunch,
)


def start_session(
    context: InterviewContext,
    *,
    registry: Dict[str, Tuple[LlmRoute, Type[BaseModel]]],
    settings: FlowSettings,
) -> SessionLaunch:  # Run the warmup stage for a new session
    warmup_agent = _warmup_agent(registry)
    _evaluator_agent(registry)  # Ensure evaluator is configured before launch
    seeded_context = _seed_competency_context(context)
    progress = FlowProgress(
        warmup_limit=max(settings.warmup_questions, 0),
        warmup_asked=0,
        competency_index=seeded_context.competency_index,
        competency_question_counts=dict(seeded_context.competency_question_counts),
        low_score_counts=dict(seeded_context.competency_low_scores),
    )
    state = FlowState(context=seeded_context, messages=[], progress=progress)
    graph = StateGraph(dict)
    graph.add_node("router", _identity)
    graph.add_node(
        "warmup",
        lambda payload: _run_warmup(warmup_agent, settings, _ensure_state(payload)).model_dump(),
    )
    graph.add_edge("warmup", END)
    graph.add_conditional_edges(
        "router",
        lambda payload: _route_start(_ensure_state(payload)),
        {
            "warmup": "warmup",
            "end": END,
        },
    )
    graph.set_entry_point("router")
    final_state = FlowState.model_validate(graph.compile().invoke(state.model_dump()))
    return SessionLaunch(context=final_state.context, messages=final_state.messages)


def start_session_with_config(
    context: InterviewContext,
    *,
    config_path: Path,
) -> SessionLaunch:  # Convenience helper loading registry from config file
    cfg = load_config(config_path)
    schemas: Dict[str, Type[BaseModel]] = {
        WARMUP_AGENT_KEY: WarmupPlan,
        COMPETENCY_AGENT_KEY: CompetencyPlan,
        EVALUATOR_AGENT_KEY: EvaluationPlan,
    }
    registry = resolve_registry(cfg, schemas)
    return start_session(context, registry=registry, settings=cfg.flow)


def advance_session(
    context: InterviewContext,
    history: List[ChatTurn],
    *,
    registry: Dict[str, Tuple[LlmRoute, Type[BaseModel]]],
    settings: FlowSettings,
) -> SessionLaunch:  # Evaluate latest answer and progress stages
    evaluator = _evaluator_agent(registry)
    competency_agent = _competency_agent(registry)
    warmup_limit = max(settings.warmup_questions, 0)
    progress = FlowProgress(
        warmup_limit=warmup_limit,
        warmup_asked=min(_count_interviewer_questions(history), warmup_limit),
        competency_index=context.competency_index,
        competency_question_counts=dict(context.competency_question_counts),
        low_score_counts=dict(context.competency_low_scores),
    )
    seeded_context = _seed_competency_context(context)
    state = FlowState(context=seeded_context, messages=list(history), progress=progress)
    exchange = _latest_exchange(history)
    if exchange is None:
        return SessionLaunch(context=seeded_context, messages=[])
    question, answer, question_number = exchange
    stage = _stage_for_question(question_number, warmup_limit)
    plan = evaluator.invoke(state, stage=stage, question=question, answer=answer)
    (
        evaluated_context,
        evaluated_progress,
        coverage_complete,
        low_score_triggered,
    ) = _apply_evaluation(
        seeded_context,
        state.progress,
        plan,
        stage,
        warmup_limit,
        question_number,
        settings,
    )
    updated_state = FlowState(
        context=evaluated_context,
        messages=list(history),
        progress=evaluated_progress,
    )
    if evaluated_context.stage != "competency":
        return SessionLaunch(context=evaluated_context, messages=[])
    routed_state = _drive_competency_loop(
        updated_state,
        competency_agent,
        settings=settings,
        answered_stage=stage,
        coverage_complete=coverage_complete,
        low_score_triggered=low_score_triggered,
    )
    followups = routed_state.messages[len(history) :]
    return SessionLaunch(context=routed_state.context, messages=followups)


def advance_session_with_config(
    context: InterviewContext,
    history: List[ChatTurn],
    *,
    config_path: Path,
) -> SessionLaunch:  # Convenience helper for advancing the flow using config file
    cfg = load_config(config_path)
    schemas: Dict[str, Type[BaseModel]] = {
        WARMUP_AGENT_KEY: WarmupPlan,
        COMPETENCY_AGENT_KEY: CompetencyPlan,
        EVALUATOR_AGENT_KEY: EvaluationPlan,
    }
    registry = resolve_registry(cfg, schemas)
    return advance_session(context, history, registry=registry, settings=cfg.flow)


def _run_warmup(agent: WarmupAgent, settings: FlowSettings, state: FlowState) -> FlowState:  # Execute warmup node
    updated = agent.invoke(state)
    asked = state.progress.warmup_asked + 1
    limit = max(settings.warmup_questions, 0)
    progress = state.progress.model_copy(
        update={
            "warmup_limit": limit,
            "warmup_asked": asked,
            "awaiting_stage": "warmup",
        }
    )
    next_stage = "warmup"
    if limit == 0 or asked >= limit:
        next_stage = "competency"
    context = updated.context.model_copy(update={"stage": next_stage})
    if next_stage == "competency":
        seeded = _seed_competency_context(context)
        progress = progress.model_copy(
            update={"competency_index": seeded.competency_index, "awaiting_stage": "competency"}
        )
        context = seeded.model_copy(
            update={
                "stage": next_stage,
                "question_index": 0,
                "targeted_criteria": [],
                "project_anchor": seeded.project_anchor,
            }
        )
    return updated.model_copy(update={"context": context, "progress": progress})


def _apply_evaluation(
    context: InterviewContext,
    progress: FlowProgress,
    plan: EvaluationPlan,
    stage: str,
    warmup_limit: int,
    question_number: int,
    settings: FlowSettings,
) -> tuple[InterviewContext, FlowProgress, bool, bool]:  # Merge evaluator results and track competency state
    seeded = _seed_competency_context(context)
    anchors = dict(seeded.evaluator.anchors)
    rubric_updates = dict(seeded.evaluator.rubric_updates)
    if plan.anchors:
        anchors[stage] = plan.anchors
    if plan.rubric_updates:
        existing = rubric_updates.get(stage, [])
        rubric_updates[stage] = _dedupe(existing + plan.rubric_updates)
    scores = dict(seeded.evaluator.scores)
    for score in plan.scores:
        scores[score.competency] = score
    summary = plan.updated_summary.strip() or seeded.evaluator.summary
    evaluator_state = seeded.evaluator.model_copy(
        update={
            "summary": summary,
            "anchors": anchors,
            "scores": scores,
            "rubric_updates": rubric_updates,
        }
    )
    next_stage = seeded.stage
    if stage == "warmup" and warmup_limit > 0 and question_number >= warmup_limit:
        next_stage = "competency"
    base_context = seeded.model_copy(update={"stage": next_stage, "evaluator": evaluator_state})
    updated_progress = progress
    coverage_complete = False
    low_score_triggered = False
    if stage == "competency":
        (
            base_context,
            updated_progress,
            coverage_complete,
            low_score_triggered,
        ) = _update_competency_tracking(base_context, updated_progress, plan, settings)
    if stage == "warmup" and next_stage == "competency":
        project = _current_project(base_context)
        base_context = base_context.model_copy(
            update={
                "question_index": base_context.question_index,
                "targeted_criteria": [],
                "project_anchor": project,
            }
        )
        updated_progress = updated_progress.model_copy(update={"awaiting_stage": "competency"})
    return base_context, updated_progress, coverage_complete, low_score_triggered


def _drive_competency_loop(
    state: FlowState,
    agent: CompetencyAgent,
    *,
    settings: FlowSettings,
    answered_stage: str,
    coverage_complete: bool,
    low_score_triggered: bool,
) -> FlowState:  # Decide whether to continue competency loop and generate next question
    context = _seed_competency_context(state.context)
    progress = state.progress.model_copy(
        update={
            "competency_index": context.competency_index,
            "competency_question_counts": dict(context.competency_question_counts),
            "low_score_counts": dict(context.competency_low_scores),
        }
    )
    routed = state.model_copy(update={"context": context, "progress": progress})
    if context.stage != "competency":
        return routed
    current = context.competency
    if not current:
        return routed
    if answered_stage == "competency":
        advance = _should_advance_competency(
            context,
            settings,
            current,
            coverage_complete,
            low_score_triggered,
        )
    else:
        advance = False
    if advance:
        context, progress = _advance_competency(context, progress)
        routed = routed.model_copy(update={"context": context, "progress": progress})
        current = context.competency
        if context.stage != "competency" or not current:
            return routed
    project = _current_project(context)
    remaining = _remaining_criteria(context, current)
    seeded_context = context.model_copy(update={"project_anchor": project})
    routed = routed.model_copy(update={"context": seeded_context})
    prompted = agent.invoke(routed, competency=current, project_anchor=project, remaining_criteria=remaining)
    question_index = seeded_context.question_index + 1
    question_counts = dict(seeded_context.competency_question_counts)
    question_counts[current] = question_index
    updated_context = prompted.context.model_copy(
        update={
            "question_index": question_index,
            "competency_question_counts": question_counts,
            "project_anchor": project,
        }
    )
    updated_progress = progress.model_copy(
        update={
            "competency_index": updated_context.competency_index,
            "competency_question_counts": question_counts,
        }
    )
    return prompted.model_copy(update={"context": updated_context, "progress": updated_progress})


def _update_competency_tracking(
    context: InterviewContext,
    progress: FlowProgress,
    plan: EvaluationPlan,
    settings: FlowSettings,
) -> tuple[InterviewContext, FlowProgress, bool, bool]:  # Update rubric coverage and low-score counts
    current = context.competency
    if not current:
        return context, progress, False, False
    criteria = context.competency_criteria.get(current, [])
    covered = list(context.competency_covered.get(current, []))
    lookup = {item.lower(): item for item in criteria}
    hits = _extract_criteria_hits(plan, criteria, current)
    levels_map = {
        name: dict(values)
        for name, values in context.competency_criterion_levels.items()
    }
    existing_levels = dict(levels_map.get(current, {}))
    score_entry = _find_score(plan, current)
    level_hits: List[str] = []
    if score_entry:
        merged_levels, level_hits = _merge_levels(existing_levels, score_entry.criterion_levels, lookup)
        levels_map[current] = merged_levels
    else:
        levels_map.setdefault(current, existing_levels)
    observed = hits
    if level_hits:
        observed = _dedupe([*observed, *level_hits]) if observed else level_hits
    merged = _dedupe([*covered, *observed]) if observed else covered
    coverage_complete = _coverage_sufficient(criteria, merged)
    low_scores = dict(context.competency_low_scores)
    current_low = low_scores.get(current, 0)
    if score_entry and score_entry.score < settings.low_score_threshold:
        current_low += 1
    low_scores[current] = current_low
    low_score_triggered = current_low >= settings.max_competency_followups
    updated_context = context.model_copy(
        update={
            "competency_covered": {**context.competency_covered, current: merged},
            "competency_low_scores": low_scores,
            "competency_criterion_levels": levels_map,
        }
    )
    low_score_counts = dict(progress.low_score_counts)
    low_score_counts[current] = current_low
    updated_progress = progress.model_copy(
        update={
            "competency_index": updated_context.competency_index,
            "competency_question_counts": dict(progress.competency_question_counts),
            "low_score_counts": low_score_counts,
        }
    )
    return updated_context, updated_progress, coverage_complete, low_score_triggered


def _coverage_sufficient(criteria: Sequence[str], covered: Sequence[str]) -> bool:  # Determine if coverage meets rubric threshold
    total = len(criteria)
    if total == 0:
        return True
    unique = {item for item in covered if item in criteria}
    if total == 1:
        return len(unique) >= 1
    return len(unique) >= max(total - 1, 1)


def _extract_criteria_hits(
    plan: EvaluationPlan,
    criteria: Sequence[str],
    competency: str,
) -> List[str]:  # Pull criteria names from evaluator updates
    normalized = [item.lower() for item in criteria]
    hits: set[int] = set()
    sources: List[str] = list(plan.rubric_updates)
    target = competency.lower()
    for score in plan.scores:
        if score.competency.lower() != target:
            continue
        sources.extend(score.rubric_updates)
        sources.extend(score.notes)
        for name, level in score.criterion_levels.items():
            cleaned = " ".join(name.split()).lower()
            if not cleaned or level <= 0:
                continue
            for idx, candidate in enumerate(normalized):
                if candidate and candidate == cleaned:
                    hits.add(idx)
                    break
    for entry in sources:
        text = entry.lower()
        for idx, name in enumerate(normalized):
            if name and name in text:
                hits.add(idx)
    return [criteria[index] for index in sorted(hits)]


def _find_score(plan: EvaluationPlan, competency: str) -> CompetencyScore | None:  # Locate score entry for competency
    target = competency.lower()
    for score in plan.scores:
        if score.competency.lower() == target:
            return score
    return None


def _remaining_criteria(context: InterviewContext, competency: str) -> List[str]:  # Compute remaining rubric criteria
    criteria = context.competency_criteria.get(competency, [])
    covered = {item for item in context.competency_covered.get(competency, [])}
    return [item for item in criteria if item not in covered]


def _merge_levels(
    existing: Dict[str, int],
    updates: Dict[str, int],
    lookup: Dict[str, str],
) -> tuple[Dict[str, int], List[str]]:  # Merge evaluator criterion levels into existing map
    merged = dict(existing)
    hits: List[str] = []
    for raw_name, raw_level in updates.items():
        name = " ".join(str(raw_name).split()).strip()
        if not name:
            continue
        canonical = lookup.get(name.lower())
        if not canonical:
            continue
        level = _normalize_level(raw_level)
        merged[canonical] = level
        if level > 0:
            hits.append(canonical)
    return merged, hits


def _normalize_level(value: int | float) -> int:  # Clamp criterion level into rubric bounds
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0
    return int(max(0, min(5, round(numeric))))


def _should_advance_competency(
    context: InterviewContext,
    settings: FlowSettings,
    competency: str,
    coverage_complete: bool,
    low_score_triggered: bool,
) -> bool:  # Decide whether to move to the next competency pillar
    if coverage_complete:
        return True
    if not _remaining_criteria(context, competency):
        return True
    if context.question_index >= settings.max_competency_followups:
        return True
    if low_score_triggered:
        return True
    return False


def _advance_competency(
    context: InterviewContext,
    progress: FlowProgress,
) -> tuple[InterviewContext, FlowProgress]:  # Move to the next competency or wrap up
    pillars = list(context.competency_pillars)
    next_index = context.competency_index + 1
    if next_index >= len(pillars):
        new_context = context.model_copy(
            update={
                "competency_index": next_index,
                "competency": None,
                "stage": "wrap_up",
                "question_index": 0,
                "targeted_criteria": [],
                "project_anchor": "",
                "competency_criterion_levels": {
                    name: dict(values)
                    for name, values in context.competency_criterion_levels.items()
                },
            }
        )
        new_progress = progress.model_copy(update={"competency_index": next_index})
        return new_context, new_progress
    next_competency = pillars[next_index]
    question_counts = dict(context.competency_question_counts)
    low_scores = dict(context.competency_low_scores)
    covered = dict(context.competency_covered)
    levels = {
        name: dict(values)
        for name, values in context.competency_criterion_levels.items()
    }
    question_counts.setdefault(next_competency, 0)
    low_scores.setdefault(next_competency, 0)
    covered.setdefault(next_competency, [])
    levels.setdefault(next_competency, dict(levels.get(next_competency, {})))
    new_context = context.model_copy(
        update={
            "competency_index": next_index,
            "competency": next_competency,
            "question_index": 0,
            "targeted_criteria": [],
            "project_anchor": context.competency_projects.get(next_competency, ""),
            "competency_question_counts": question_counts,
            "competency_low_scores": low_scores,
            "competency_covered": covered,
            "competency_criterion_levels": levels,
        }
    )
    new_progress = progress.model_copy(
        update={
            "competency_index": next_index,
            "competency_question_counts": question_counts,
            "low_score_counts": low_scores,
        }
    )
    return new_context, new_progress


def _seed_competency_context(context: InterviewContext) -> InterviewContext:  # Ensure competency metadata is initialized
    pillars = list(context.competency_pillars)
    if not pillars:
        return context
    index = min(context.competency_index, max(len(pillars) - 1, 0))
    name = context.competency or pillars[index]
    projects = dict(context.competency_projects)
    question_counts = dict(context.competency_question_counts)
    low_scores = dict(context.competency_low_scores)
    covered = dict(context.competency_covered)
    levels = {
        name: dict(values)
        for name, values in context.competency_criterion_levels.items()
    }
    question_counts.setdefault(name, context.question_index)
    low_scores.setdefault(name, low_scores.get(name, 0))
    covered.setdefault(name, covered.get(name, []))
    levels.setdefault(name, dict(levels.get(name, {})))
    anchor = projects.get(name, context.project_anchor)
    return context.model_copy(
        update={
            "competency_index": index,
            "competency": name,
            "project_anchor": anchor,
            "competency_projects": projects,
            "competency_question_counts": question_counts,
            "competency_low_scores": low_scores,
            "competency_covered": covered,
            "competency_criterion_levels": levels,
        }
    )


def _current_project(context: InterviewContext) -> str:  # Fetch current competency project anchor
    if not context.competency:
        return ""
    return context.competency_projects.get(context.competency, context.project_anchor)


def _latest_exchange(history: Sequence[ChatTurn]) -> tuple[ChatTurn, ChatTurn, int] | None:  # Find latest Q&A pair
    interviewer_count = 0
    last_question: ChatTurn | None = None
    last_answer: ChatTurn | None = None
    last_index = 0
    for turn in history:
        if turn.speaker.strip().lower() == "interviewer":
            interviewer_count += 1
            last_question = turn
            last_answer = None
            last_index = interviewer_count
        elif turn.speaker.strip().lower() == "candidate" and last_question is not None:
            last_answer = turn
    if last_question is None or last_answer is None:
        return None
    return last_question, last_answer, last_index


def _stage_for_question(question_number: int, warmup_limit: int) -> str:  # Determine stage for question index
    if warmup_limit <= 0:
        return "competency"
    return "warmup" if question_number <= warmup_limit else "competency"


def _count_interviewer_questions(history: Sequence[ChatTurn]) -> int:  # Count interviewer prompts so far
    return sum(1 for turn in history if turn.speaker.strip().lower() == "interviewer")


def _route_start(state: FlowState) -> str:  # Route state to warmup or end nodes
    if state.progress.warmup_limit <= 0:
        return "end"
    if state.context.stage.lower() == "warmup" and state.progress.warmup_asked < state.progress.warmup_limit:
        return "warmup"
    return "end"


def _warmup_agent(registry: Dict[str, Tuple[LlmRoute, Type[BaseModel]]]) -> WarmupAgent:  # Build warmup agent from registry
    if WARMUP_AGENT_KEY not in registry:
        raise KeyError(f"Registry missing {WARMUP_AGENT_KEY}")
    route, schema = registry[WARMUP_AGENT_KEY]
    if not issubclass(schema, WarmupPlan):
        raise TypeError("Warmup agent schema must extend WarmupPlan")
    return WarmupAgent(route, schema)  # type: ignore[arg-type]


def _competency_agent(
    registry: Dict[str, Tuple[LlmRoute, Type[BaseModel]]]
) -> CompetencyAgent:  # Build competency agent from registry
    if COMPETENCY_AGENT_KEY not in registry:
        raise KeyError(f"Registry missing {COMPETENCY_AGENT_KEY}")
    route, schema = registry[COMPETENCY_AGENT_KEY]
    if not issubclass(schema, CompetencyPlan):
        raise TypeError("Competency agent schema must extend CompetencyPlan")
    return CompetencyAgent(route, schema)  # type: ignore[arg-type]


def _evaluator_agent(
    registry: Dict[str, Tuple[LlmRoute, Type[BaseModel]]]
) -> EvaluatorAgent:  # Build evaluator agent from registry
    if EVALUATOR_AGENT_KEY not in registry:
        raise KeyError(f"Registry missing {EVALUATOR_AGENT_KEY}")
    route, schema = registry[EVALUATOR_AGENT_KEY]
    if not issubclass(schema, EvaluationPlan):
        raise TypeError("Evaluator agent schema must extend EvaluationPlan")
    return EvaluatorAgent(route, schema)  # type: ignore[arg-type]


def _dedupe(items: Sequence[str]) -> List[str]:  # Preserve order while removing duplicates
    seen: set[str] = set()
    result: List[str] = []
    for item in items:
        text = " ".join(item.split())
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _identity(payload: Dict[str, Any]) -> Dict[str, Any]:  # Identity node required by LangGraph entry
    return payload


def _ensure_state(payload: FlowState | Dict[str, Any]) -> FlowState:  # Normalize payload into FlowState
    if isinstance(payload, FlowState):
        return payload
    if isinstance(payload, dict):
        return FlowState.model_validate(payload)
    raise TypeError("Unsupported state payload")


__all__ = [
    "CompetencyPlan",
    "EvaluationPlan",
    "advance_session",
    "advance_session_with_config",
    "ChatTurn",
    "InterviewContext",
    "SessionLaunch",
    "WarmupPlan",
    "start_session",
    "start_session_with_config",
]
