from __future__ import annotations  # Competency follow-up agent for interview loop

from textwrap import dedent
from typing import Iterable, List, Sequence, Type

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from config import LlmRoute
from llm_gateway import call
from ..models import ChatTurn, FlowState


COMPETENCY_AGENT_KEY = "flow_manager.competency_agent"  # Registry key for competency follow-up agent

COMPETENCY_GUIDANCE = dedent(  # Competency loop instructions shared with the LLM
    """
    You are the interviewer driving competency deep-dives.
    Link questions to concrete projects, probing criteria coverage without repeating yourself.
    Adjust intensity using evaluator feedback and remaining rubric criteria.
    Keep tone professional yet conversational.
    """
).strip()


class CompetencyPlan(BaseModel):  # LLM response schema for competency questions
    question: str
    tone: str = "neutral"
    targeted_criteria: List[str] = Field(default_factory=list)


class CompetencyAgent:  # Agent generating competency-focused interviewer prompts
    def __init__(self, route: LlmRoute, schema: Type[CompetencyPlan]) -> None:
        self._route = route
        self._schema = schema
        self._prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "{instructions}"),
                (
                    "human",
                    (
                        "Stage: competency\n"
                        "Job Title: {job_title}\n"
                        "Candidate: {candidate_name}\n"
                        "Competency Focus: {competency}\n"
                        "Current Project Anchor: {project_anchor}\n"
                        "Remaining Criteria:\n{remaining_criteria}\n\n"
                        "Conversation so far:\n{conversation}\n\n"
                        "Question Index: {question_index}\n"
                        "{instruction_block}"
                    ),
                ),
            ]
        )

    def invoke(
        self,
        state: FlowState,
        *,
        competency: str,
        project_anchor: str,
        remaining_criteria: Sequence[str],
    ) -> FlowState:  # Run competency agent to append interviewer question
        intro = _intro_text(state.context.question_index, competency)
        task = self._prompt.format(
            instructions=COMPETENCY_GUIDANCE,
            job_title=state.context.job_title,
            candidate_name=state.context.candidate_name,
            competency=competency,
            project_anchor=project_anchor or "(use a hypothetical if needed)",
            remaining_criteria=_format_criteria(remaining_criteria),
            conversation=_format_conversation(state.messages),
            question_index=str(state.context.question_index),
            instruction_block=intro,
        )
        plan = call(task, self._schema, cfg=self._route)
        tone = (plan.tone or "neutral").strip().lower()
        if tone not in {"neutral", "positive"}:
            tone = "neutral"
        targeted = [_clean_line(item) for item in plan.targeted_criteria if _clean_line(item)]
        message = ChatTurn(
            speaker="Interviewer",
            content=plan.question.strip(),
            tone=tone,
            competency=competency,
            targeted_criteria=targeted,
            project_anchor=project_anchor.strip(),
        )
        context = state.context.model_copy(update={"targeted_criteria": targeted})
        return state.model_copy(update={"context": context, "messages": state.messages + [message]})


def _intro_text(question_index: int, competency: str) -> str:  # Build instruction block depending on question index
    if question_index == 0:
        intro = (
            "Begin this competency by linking a resume experience to the rubric. "
            "Ask a broad, competency-aligned question that identifies a concrete project or decision the candidate handled."
        )
    else:
        intro = (
            "Continue the loop by targeting uncovered rubric criteria. Reference previous answers, avoid repetition, "
            "and deepen evidence until the rubric can be confidently scored."
        )
    header = (
        "Competency focus: {name}.\n"
        "Dwell on this competency until all criteria are satisfied or a future custom metric signals closure.\n"
        "Use evaluator feedback and rubric anchors to tune intensity, looping with follow-ups when evidence is incomplete."
    ).format(name=competency)
    return header + "\n" + intro


def _format_conversation(messages: Iterable[ChatTurn]) -> str:  # Render transcript history for prompt
    lines: List[str] = []
    for turn in messages:
        speaker = turn.speaker.strip() or "Unknown"
        content = turn.content.strip() or "(no content)"
        lines.append(f"{speaker}: {content}")
    return "\n".join(lines) if lines else "(none)"


def _format_criteria(criteria: Sequence[str]) -> str:  # Format remaining criteria list for prompt
    items = [_clean_line(item) for item in criteria if _clean_line(item)]
    if not items:
        return "(all criteria addressed)"
    return "\n".join(f"- {item}" for item in items)


def _clean_line(text: str) -> str:  # Normalize whitespace for plan outputs
    return " ".join(text.split())


__all__ = [
    "COMPETENCY_AGENT_KEY",
    "COMPETENCY_GUIDANCE",
    "CompetencyAgent",
    "CompetencyPlan",
]
