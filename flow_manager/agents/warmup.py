from __future__ import annotations  # Warmup agent generating rapport-building prompts

from textwrap import dedent
from typing import Iterable, List, Type

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from config import LlmRoute
from llm_gateway import call
from ..models import ChatTurn, FlowState


WARMUP_AGENT_KEY = "flow_manager.warmup_agent"  # Registry key for warmup agent configuration

WARMUP_GUIDANCE = dedent(  # Interviewer guidance supplied to the warmup agent
    """
    Build rapport while surfacing concrete experiences that map to later competencies.
    Use the resume summary and highlighted experiences to find shared context and establish a comfortable tone.
    Keep questions open and conversational; no rubric scoring yet, but capture anchors for future reference.
    """
).strip()


class WarmupPlan(BaseModel):  # Warmup agent output schema enforced on the LLM
    question: str
    tone: str = "positive"
    notes: List[str] = Field(default_factory=list)


class WarmupAgent:  # Agent responsible for producing the warmup prompt
    def __init__(self, route: LlmRoute, schema: Type[WarmupPlan]) -> None:  # Configure LLM route and schema
        self._route = route
        self._schema = schema
        self._prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "{instructions}"),
                (
                    "human",
                    (
                        "Interview Stage: {stage}\n"
                        "Job Title: {job_title}\n"
                        "Candidate: {candidate_name}\n"
                        "Resume Summary:\n{resume_summary}\n"
                        "Highlighted Experiences:\n{highlighted_experiences}\n\n"
                        "Produce a single conversational warmup question and set tone metadata."
                    ),
                ),
            ]
        )

    def invoke(self, state: FlowState) -> FlowState:  # Run the warmup agent against flow state
        context = state.context
        task = self._prompt.format(
            instructions=WARMUP_GUIDANCE,
            stage=context.stage,
            job_title=context.job_title,
            candidate_name=context.candidate_name,
            resume_summary=_format_resume(context.resume_summary),
            highlighted_experiences=_format_highlights(context.highlighted_experiences),
        )
        result = call(task, self._schema, cfg=self._route)
        tone = (result.tone or "positive").strip().lower()
        if tone not in {"neutral", "positive"}:
            tone = "neutral"
        message = ChatTurn(
            speaker="Interviewer",
            content=result.question.strip(),
            tone=tone,
        )
        return FlowState(context=context, messages=state.messages + [message])


def _format_highlights(entries: Iterable[str]) -> str:  # Format highlighted experiences as bullet list
    lines = [entry.strip() for entry in entries if entry and entry.strip()]
    if not lines:
        return "None provided."
    return "\n".join(f"- {line}" for line in lines)


def _format_resume(summary: str, limit: int = 600) -> str:  # Clamp resume summary for prompt hygiene
    compact = " ".join(summary.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


__all__ = [
    "WARMUP_AGENT_KEY",
    "WARMUP_GUIDANCE",
    "WarmupAgent",
    "WarmupPlan",
]
