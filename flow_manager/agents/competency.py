from __future__ import annotations  # Competency follow-up agent for interview loop

from textwrap import dedent
from typing import List, Sequence, Type

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel, Field

from config import LlmRoute
from llm_gateway import runnable as llm_runnable
from ..models import ChatTurn, FlowState
from .toolkit import bullet_list, clamp_text, transcript_messages
from .persona import PersonaAgent


COMPETENCY_AGENT_KEY = "flow_manager.competency_agent"  # Registry key for competency follow-up agent

COMPETENCY_GUIDANCE = dedent(  # Competency loop instructions shared with the LLM
    """
    You are the interviewer driving competency deep-dives.
    Link questions to concrete projects, probing criteria coverage without repeating yourself.
    Adjust intensity using evaluator feedback and remaining rubric criteria.
    Keep tone professional yet conversational.
    """
).strip()


class CompetencyPlan(BaseModel):  # LLM response schema for competency persona brief
    persona_brief: str
    draft_question: str
    tone: str = "neutral"
    targeted_criteria: List[str] = Field(default_factory=list)


class CompetencyAgent:  # Agent generating competency-focused interviewer prompts
    def __init__(
        self,
        route: LlmRoute,
        schema: Type[CompetencyPlan],
        persona: PersonaAgent | None,
    ) -> None:
        self._route = route
        self._schema = schema
        self._persona = persona
        self._prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "{instructions}"),
                MessagesPlaceholder("history"),
                (
                    "human",
                    (
                        "Stage: competency\n"
                        "Job Title: {job_title}\n"
                        "Candidate: {candidate_name}\n"
                        "Competency Focus: {competency}\n"
                        "Current Project Anchor: {project_anchor}\n"
                        "Remaining Criteria:\n{remaining_criteria}\n\n"
                        "Question Index: {question_index}\n"
                        "Instruction Block:\n{instruction_block}\n\n"
                        "Return JSON with persona_brief, draft_question, tone, and targeted_criteria"
                        " describing the interviewer plan."
                    ),
                ),
            ]
        )
        self._chain = self._prompt | llm_runnable(self._route, self._schema)

    def invoke(
        self,
        state: FlowState,
        *,
        competency: str,
        project_anchor: str,
        remaining_criteria: Sequence[str],
        use_persona: bool = True,
    ) -> FlowState:  # Run competency agent to append interviewer question
        intro = _intro_text(state.context.question_index, competency)
        plan = self._chain.invoke(
            {
                "instructions": COMPETENCY_GUIDANCE,
                "history": transcript_messages(state.messages),
                "job_title": state.context.job_title,
                "candidate_name": state.context.candidate_name,
                "competency": competency,
                "project_anchor": project_anchor or "(use a hypothetical if needed)",
                "remaining_criteria": _format_criteria(remaining_criteria),
                "question_index": str(state.context.question_index),
                "instruction_block": intro,
            }
        )
        tone = (plan.tone or "neutral").strip().lower()
        if tone not in {"neutral", "positive"}:
            tone = "neutral"
        targeted = [_clean_line(item) for item in plan.targeted_criteria if _clean_line(item)]
        brief = _build_persona_brief(
            state,
            plan,
            tone,
            competency,
            project_anchor,
            remaining_criteria,
            targeted,
        )
        question = _finalize_question(
            persona=self._persona,
            plan=plan,
            brief=brief,
            use_persona=use_persona,
            competency=competency,
            project_anchor=project_anchor,
            state=state,
        )
        message = ChatTurn(
            speaker="Interviewer",
            content=question.strip(),
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


def _format_conversation(messages: Sequence[ChatTurn]) -> str:  # Render transcript history for prompt
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


def _build_persona_brief(
    state: FlowState,
    plan: CompetencyPlan,
    tone: str,
    competency: str,
    project_anchor: str,
    remaining_criteria: Sequence[str],
    targeted: Sequence[str],
) -> str:  # Assemble persona brief for competency question
    context = state.context
    anchor = clamp_text(project_anchor.strip() or "Use a relevant project from the resume if possible.", limit=160)
    focus = clamp_text(plan.persona_brief.strip() or "Advance evidence for the competency.", limit=200)
    conversation = _format_conversation(state.messages)
    remaining = [_clean_line(item) for item in remaining_criteria if _clean_line(item)]
    lines = [
        "You are the interviewer persona crafting a competency follow-up question.",
        f"Competency: {competency}",
        f"Tone: {tone}.",
        f"Candidate: {context.candidate_name}",
        f"Job Title: {context.job_title}",
        f"Project anchor to reference: {anchor}",
        f"Persona brief: {focus}",
    ]
    if targeted:
        lines.append("Targeted criteria to probe:")
        lines.append(bullet_list(targeted))
    if remaining:
        lines.append("Remaining rubric criteria available:")
        lines.append(bullet_list(remaining))
    lines.extend(
        [
            "Conversation so far:",
            conversation if conversation else "(none)",
            "Write a single interviewer question that feels human and honors the persona brief.",
        ]
    )
    return "\n".join(lines)


def _finalize_question(
    *,
    persona: PersonaAgent | None,
    plan: CompetencyPlan,
    brief: str,
    use_persona: bool,
    competency: str,
    project_anchor: str,
    state: FlowState,
) -> str:  # Choose persona output or draft fallback
    draft = plan.draft_question.strip()
    if use_persona and persona is not None:
        return persona.generate(brief=brief, draft_question=plan.draft_question)
    if draft:
        return draft
    context = state.context
    anchor = project_anchor.strip() or "a recent project"
    focus = plan.persona_brief.strip()
    base = f"Can you walk me through {anchor} that showcases your {competency} skills?"
    if focus:
        suffix = focus.rstrip(".")
        if suffix:
            return f"{base[:-1]} with a focus on {suffix}?"
    return base


__all__ = [
    "COMPETENCY_AGENT_KEY",
    "COMPETENCY_GUIDANCE",
    "CompetencyAgent",
    "CompetencyPlan",
]
