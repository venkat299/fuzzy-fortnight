from __future__ import annotations  # Evaluator agent scoring answers and maintaining memory

from textwrap import dedent
from typing import Iterable, List, Sequence, Type

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from config import LlmRoute
from llm_gateway import call
from ..models import ChatTurn, CompetencyScore, FlowState


EVALUATOR_AGENT_KEY = "flow_manager.evaluator_agent"  # Registry key for evaluator agent configuration

EVALUATOR_GUIDANCE = dedent(  # Evaluation guardrails for rubric-aware scoring
    """
    You are the evaluator for a live technical interview.
    Maintain a conversation summary buffer while scoring candidate replies.
    Warmup stage: capture behavioral anchors only, no scores yet.
    Competency stage: update rubric scores, cite evidence, and refresh the running summary.
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
                (
                    "human",
                    (
                        "Interview Stage: {stage}\n"
                        "Job Title: {job_title}\n"
                        "Job Description:\n{job_description}\n\n"
                        "Resume Summary:\n{resume_summary}\n\n"
                        "Competency Pillars:\n{competencies}\n\n"
                        "Current Evaluator Summary:\n{summary}\n\n"
                        "Recent Conversation Window:\n{history}\n\n"
                        "Latest Question: {question}\n"
                        "Candidate Answer: {answer}\n\n"
                        "Return JSON with updated summary, anchors, rubric updates, and scores."
                    ),
                ),
            ]
        )

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
        task = self._prompt.format(
            instructions=EVALUATOR_GUIDANCE,
            stage=stage,
            job_title=state.context.job_title,
            job_description=_clamp(state.context.job_description),
            resume_summary=_clamp(state.context.resume_summary),
            competencies=_format_competencies(state.context.competency_pillars),
            summary=summary or "(no summary yet)",
            history=_format_history(history),
            question=question.content.strip(),
            answer=answer.content.strip(),
        )
        plan = call(task, self._schema, cfg=self._route)
        anchors = [_clean_line(item) for item in plan.anchors if _clean_line(item)]
        updates = [_clean_line(item) for item in plan.rubric_updates if _clean_line(item)]
        scores = [_normalize_score(score) for score in plan.scores]
        return plan.model_copy(update={"anchors": anchors, "rubric_updates": updates, "scores": scores})


def _normalize_score(score: CompetencyScore) -> CompetencyScore:  # Clamp evaluator score payload
    value = max(0.0, min(5.0, score.score))
    cleaned_notes = [_clean_line(note) for note in score.notes if _clean_line(note)]
    cleaned_updates = [_clean_line(note) for note in score.rubric_updates if _clean_line(note)]
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


def _recent_history(messages: Sequence[ChatTurn], window: int) -> List[ChatTurn]:  # Select last N turns
    if not messages:
        return []
    return list(messages[-window:])


def _format_history(messages: Iterable[ChatTurn]) -> str:  # Format transcript window for prompt context
    lines: List[str] = []
    for turn in messages:
        speaker = turn.speaker.strip() or "Unknown"
        content = turn.content.strip() or "(no content)"
        lines.append(f"{speaker}: {content}")
    return "\n".join(lines) if lines else "(no prior exchanges)"


def _format_competencies(items: Iterable[str]) -> str:  # Render competency pillars as bullet list
    values = [_clean_line(item) for item in items if _clean_line(item)]
    if not values:
        return "(no competencies provided)"
    return "\n".join(f"- {value}" for value in values)


def _clamp(text: str, limit: int = 900) -> str:  # Clamp long context strings for the evaluator prompt
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _clean_line(text: str) -> str:  # Normalize whitespace on evaluator outputs
    return " ".join(text.split())


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
