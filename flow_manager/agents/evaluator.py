from __future__ import annotations  # Evaluator agent scoring answers and maintaining memory

from textwrap import dedent
from typing import Dict, List, Mapping, Sequence, Type

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel, Field

from config import LlmRoute
from llm_gateway import runnable as llm_runnable
from ..models import ChatTurn, CompetencyScore, FlowState
from .toolkit import bullet_list, clamp_text, transcript_messages


EVALUATOR_AGENT_KEY = "flow_manager.evaluator_agent"  # Registry key for evaluator agent configuration

EVALUATOR_GUIDANCE = dedent(  # Evaluation guardrails for rubric-aware scoring
    """
    You are the evaluator for a live technical interview.
    Maintain a conversation summary buffer while scoring candidate replies.
    Warmup stage: capture behavioral anchors only, no scores yet.
    Competency stage: update rubric scores, cite evidence, and refresh the running summary.
    Never lower previously achieved rubric levels or competency scores; maintain or improve them.
    Always reply with calibrated anchors and concise rubric updates.
    """
).strip()


class EvaluationPlan(BaseModel):  # LLM-enforced evaluator payload
    stage: str
    updated_summary: str
    anchors: List[str] = Field(default_factory=list)
    scores: List[CompetencyScore] = Field(default_factory=list)
    rubric_updates: List[str] = Field(default_factory=list)


class EvaluatorAgent:  # Agent evaluating candidate answers against rubric context
    def __init__(self, route: LlmRoute, schema: Type[EvaluationPlan], *, window: int = 6) -> None:
        self._route = route
        self._schema = schema
        self._window = max(1, window)
        self._prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "{instructions}"),
                MessagesPlaceholder("history"),
                (
                    "human",
                    (
                        "Interview Stage: {stage}\n"
                        "Active Competency: {active_competency}\n"
                        "Job Title: {job_title}\n"
                        "Job Description:\n{job_description}\n\n"
                        "Resume Summary:\n{resume_summary}\n\n"
                        "Competency Pillars:\n{competencies}\n\n"
                        "Current Evaluator Summary:\n{summary}\n\n"
                        "Rubric Criteria:\n{rubric}\n\n"
                        "Historical Criterion Levels:\n{levels}\n"
                        "Historical Competency Score: {existing_score}\n\n"
                        "Latest Question: {question}\n"
                        "Candidate Answer: {answer}\n\n"
                        "Return JSON with updated_summary, anchors, rubric_updates, and scores respecting the schema."
                    ),
                ),
            ]
        )
        self._chain = self._prompt | llm_runnable(self._route, self._schema)

    def invoke(
        self,
        state: FlowState,
        *,
        stage: str,
        question: ChatTurn,
        answer: ChatTurn,
    ) -> EvaluationPlan:  # Run evaluator against the latest exchange
        summary = state.context.evaluator.summary.strip()
        history = _recent_history(state.messages, self._window)
        competency = _resolve_competency(state, question)
        criteria = state.context.competency_criteria.get(competency, [])
        baseline_levels = state.context.competency_criterion_levels.get(competency, {})
        prior_score = state.context.evaluator.scores.get(competency)
        plan = self._chain.invoke(
            {
                "instructions": EVALUATOR_GUIDANCE,
                "history": transcript_messages(history),
                "stage": stage,
                "active_competency": competency or "(not set)",
                "job_title": state.context.job_title,
                "job_description": clamp_text(state.context.job_description, limit=900),
                "resume_summary": clamp_text(state.context.resume_summary, limit=900),
                "competencies": bullet_list(state.context.competency_pillars),
                "summary": summary or "(no summary yet)",
                "rubric": _format_rubric(criteria),
                "levels": _format_levels(criteria, baseline_levels, prior_score),
                "existing_score": _format_score(prior_score),
                "question": question.content.strip(),
                "answer": answer.content.strip(),
            }
        )
        anchors = [_clean_line(item) for item in plan.anchors if _clean_line(item)]
        updates = [_clean_line(item) for item in plan.rubric_updates if _clean_line(item)]
        scores: List[CompetencyScore] = []
        criteria_map = state.context.competency_criteria
        prior_scores = state.context.evaluator.scores
        level_map = state.context.competency_criterion_levels
        for raw in plan.scores:
            rubric = criteria_map.get(raw.competency, [])
            previous = prior_scores.get(raw.competency)
            baseline = level_map.get(raw.competency, {})
            scores.append(_normalize_score(raw, rubric, previous, baseline))
        return plan.model_copy(update={"anchors": anchors, "rubric_updates": updates, "scores": scores})


def _normalize_score(
    score: CompetencyScore,
    rubric: Sequence[str],
    existing: CompetencyScore | None,
    baseline: Mapping[str, int],
) -> CompetencyScore:  # Clamp evaluator score payload with rubric alignment
    value = max(0.0, min(5.0, score.score))
    if existing:
        value = max(existing.score, value)
    cleaned_notes = [_clean_line(note) for note in score.notes if _clean_line(note)]
    cleaned_updates = [_clean_line(note) for note in score.rubric_updates if _clean_line(note)]
    lookup = _build_lookup(rubric)
    if lookup:
        baseline_levels: Dict[str, int] = {name: 0 for name in lookup.values()}
        if existing:
            for raw, amount in existing.criterion_levels.items():
                canonical = lookup.get(_clean_line(raw).lower())
                if canonical:
                    baseline_levels[canonical] = max(baseline_levels[canonical], _clamp_level(amount))
        for raw, amount in baseline.items():
            canonical = lookup.get(_clean_line(raw).lower())
            if canonical:
                baseline_levels[canonical] = max(baseline_levels[canonical], _clamp_level(amount))
        incoming: Dict[str, int] = {}
        for raw, amount in score.criterion_levels.items():
            canonical = lookup.get(_clean_line(raw).lower())
            if canonical:
                incoming[canonical] = _clamp_level(amount)
        normalized_levels: Dict[str, int] = {}
        for label in rubric:
            canonical = lookup.get(_clean_line(label).lower())
            if not canonical:
                continue
            prior = baseline_levels.get(canonical, 0)
            candidate = incoming.get(canonical, prior)
            normalized_levels[canonical] = max(prior, candidate)
    else:
        normalized_levels = {
            key: _clamp_level(amount)
            for key, amount in score.criterion_levels.items()
            if _clean_line(key)
        }
    return score.model_copy(
        update={
            "score": value,
            "notes": cleaned_notes,
            "rubric_updates": cleaned_updates,
            "criterion_levels": normalized_levels,
        }
    )


def _resolve_competency(state: FlowState, question: ChatTurn) -> str:  # Determine active competency for the evaluator
    if question.competency:
        return question.competency
    if state.context.competency:
        return state.context.competency
    return ""


def _recent_history(messages: Sequence[ChatTurn], window: int) -> List[ChatTurn]:  # Select last N turns
    if not messages:
        return []
    return list(messages[-window:])


def _format_rubric(criteria: Sequence[str]) -> str:  # Format rubric criteria for evaluator context
    items = [_clean_line(item) for item in criteria if _clean_line(item)]
    if not items:
        return "(no rubric criteria available)"
    return "\n".join(f"- {item}" for item in items)


def _format_levels(
    criteria: Sequence[str],
    baseline: Mapping[str, int],
    existing: CompetencyScore | None,
) -> str:  # Format historical criterion levels for prompt context
    lookup = _build_lookup(criteria)
    if not lookup:
        return "(no rubric criteria available)"
    levels: Dict[str, int] = {name: 0 for name in lookup.values()}
    if existing:
        for raw, amount in existing.criterion_levels.items():
            canonical = lookup.get(_clean_line(raw).lower())
            if canonical:
                levels[canonical] = max(levels[canonical], _clamp_level(amount))
    for raw, amount in baseline.items():
        canonical = lookup.get(_clean_line(raw).lower())
        if canonical:
            levels[canonical] = max(levels[canonical], _clamp_level(amount))
    lines: List[str] = []
    for item in criteria:
        canonical = lookup.get(_clean_line(item).lower())
        if not canonical:
            continue
        lines.append(f"- {_clean_line(canonical)}: level {levels.get(canonical, 0)}")
    return "\n".join(lines) if lines else "(no rubric criteria available)"


def _format_score(existing: CompetencyScore | None) -> str:  # Describe prior competency score
    if not existing:
        return "No prior competency score recorded."
    return f"{existing.score:.2f} / 5.00"


def _clean_line(text: str) -> str:  # Normalize whitespace on evaluator outputs
    return " ".join(text.split())


def _build_lookup(criteria: Sequence[str]) -> Dict[str, str]:  # Map normalized criterion names to canonical labels
    lookup: Dict[str, str] = {}
    for item in criteria:
        cleaned = _clean_line(item)
        if cleaned:
            lookup[cleaned.lower()] = item
    return lookup


def _clamp_level(raw: int | float) -> int:  # Clamp criterion level into rubric bounds
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0
    return int(max(0, min(5, round(value))))


__all__ = [
    "EVALUATOR_AGENT_KEY",
    "EVALUATOR_GUIDANCE",
    "EvaluationPlan",
    "EvaluatorAgent",
]
