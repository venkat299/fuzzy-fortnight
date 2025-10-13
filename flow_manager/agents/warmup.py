from __future__ import annotations  # Warmup agent generating rapport-building prompts

from textwrap import dedent
from typing import Iterable, List, Sequence, Type

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from config import LlmRoute
from llm_gateway import call
from ..models import ChatTurn, FlowState
from .persona import PersonaAgent


WARMUP_AGENT_KEY = "flow_manager.warmup_agent"  # Registry key for warmup agent configuration

WARMUP_GUIDANCE = dedent(  # Interviewer guidance supplied to the warmup agent
    """
    Build rapport while surfacing concrete experiences that map to later competencies.
    Use the resume summary and highlighted experiences to find shared context and establish a comfortable tone.
    Keep questions open and conversational; no rubric scoring yet, but capture anchors for future reference.
    """
).strip()


class WarmupPlan(BaseModel):  # Warmup agent output schema enforced on the LLM
    persona_brief: str
    draft_question: str
    tone: str = "positive"
    notes: List[str] = Field(default_factory=list)


class WarmupAgent:  # Agent coordinating warmup plan and persona delivery
    def __init__(
        self,
        route: LlmRoute,
        schema: Type[WarmupPlan],
        persona: PersonaAgent | None,
    ) -> None:  # Configure LLM route, schema, and persona bridge
        self._route = route
        self._schema = schema
        self._persona = persona
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
                        "Conversation so far:\n{conversation_history}\n\n"
                        "Describe the warmup objective for a persona question writer."
                        " Provide an intermediate interviewer question that captures the intent"
                        " so the persona agent can humanize it."
                    ),
                ),
            ]
        )

    def invoke(self, state: FlowState, *, use_persona: bool = True) -> FlowState:  # Run the warmup agent against flow state
        context = state.context
        task = self._prompt.format(
            instructions=WARMUP_GUIDANCE,
            stage=context.stage,
            job_title=context.job_title,
            candidate_name=context.candidate_name,
            resume_summary=_format_resume(context.resume_summary),
            highlighted_experiences=_format_highlights(context.highlighted_experiences),
            conversation_history=_format_conversation(state.messages),
        )
        plan = call(task, self._schema, cfg=self._route)
        tone = (plan.tone or "positive").strip().lower()
        if tone not in {"neutral", "positive"}:
            tone = "neutral"
        brief = _build_persona_brief(state, plan, tone)
        question = _finalize_question(
            persona=self._persona,
            plan=plan,
            brief=brief,
            use_persona=use_persona,
            state=state,
        )
        message = ChatTurn(
            speaker="Interviewer",
            content=question.strip(),
            tone=tone,
        )
        return state.model_copy(
            update={
                "context": context,
                "messages": state.messages + [message],
            }
        )


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


def _format_conversation(messages: Sequence[ChatTurn]) -> str:  # Summarize existing conversation for warmup agent
    if not messages:
        return "(none)"
    lines: List[str] = []
    for turn in messages:
        speaker = turn.speaker.strip() or "Unknown"
        content = turn.content.strip() or "(no content)"
        lines.append(f"{speaker}: {content}")
    return "\n".join(lines)


def _build_persona_brief(state: FlowState, plan: WarmupPlan, tone: str) -> str:  # Assemble persona brief for warmup question
    context = state.context
    notes = [note.strip() for note in plan.notes if note.strip()]
    highlighted = _format_highlights(context.highlighted_experiences)
    conversation = _format_conversation(state.messages)
    summary = _format_resume(context.resume_summary)
    focus = plan.persona_brief.strip() or "Build rapport while referencing the candidate background."
    lines = [
        "You are the interviewer persona crafting a natural warmup prompt.",
        "Stage: warmup rapport building.",
        f"Tone: {tone}.",
        f"Candidate: {context.candidate_name}",
        f"Job Title: {context.job_title}",
        f"Warmup focus: {focus}",
        "Resume summary:",
        summary,
        "Highlighted experiences:",
        highlighted,
        "Conversation so far:",
        conversation,
    ]
    if notes:
        lines.append("Important considerations:")
        lines.extend(f"- {note}" for note in notes)
    lines.append("Write a single interviewer question that sounds human and honors the focus.")
    return "\n".join(lines)


def _finalize_question(
    *,
    persona: PersonaAgent | None,
    plan: WarmupPlan,
    brief: str,
    use_persona: bool,
    state: FlowState,
) -> str:  # Choose between persona polish or draft fallback
    draft = plan.draft_question.strip()
    if use_persona and persona is not None:
        return persona.generate(brief=brief, draft_question=plan.draft_question)
    if draft:
        return draft
    context = state.context
    focus = plan.persona_brief.strip()
    base = (
        "I'd love to hear about a recent experience that highlights your fit for"
        f" {context.job_title}."
    )
    if focus:
        return f"{base} Specifically, {focus.rstrip('.')}?"
    return base.rstrip(".") + "?"


__all__ = [
    "WARMUP_AGENT_KEY",
    "WARMUP_GUIDANCE",
    "WarmupAgent",
    "WarmupPlan",
]
