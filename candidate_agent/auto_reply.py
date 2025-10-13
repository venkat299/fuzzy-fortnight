from __future__ import annotations  # Candidate auto-answer agent implementation

from textwrap import dedent
from pathlib import Path
from typing import Dict, List, Sequence, Tuple, Type

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from config import LlmRoute, load_app_registry
from llm_gateway import call

AUTO_REPLY_AGENT_KEY = "candidate_agent.auto_reply"  # Registry key for candidate auto replies

PERSONA_MAP: Dict[int, str] = {
    1: dedent(
        """
        Level 1 – The Name-Dropper.
        Speak in vague buzzwords, cite trendy tools without detail, and avoid explaining trade-offs or edge cases.
        Provide superficial answers that stall when pressed on real-world execution.
        """
    ).strip(),
    2: dedent(
        """
        Level 2 – The Practitioner.
        Describe tasks you carried out, list tools or steps, but struggle to justify decisions.
        Keep solutions tactical and local without highlighting broader implications.
        """
    ).strip(),
    3: dedent(
        """
        Level 3 – The Problem Solver.
        Offer grounded solutions for clear problems, justify choices with practical trade-offs, and cover common failure modes.
        Sound like a dependable executor following an established plan.
        """
    ).strip(),
    4: dedent(
        """
        Level 4 – The Architect.
        Evaluate multiple approaches, explain trade-offs in cost, risk, and lifecycle, and think beyond day-one delivery.
        Discuss scalability, monitoring, and long-term evolution of the solution.
        """
    ).strip(),
    5: dedent(
        """
        Level 5 – The Strategist.
        Anticipate systemic risks, shape organization-wide direction, and frame answers around resilient, scalable strategies.
        Highlight governance, cross-team standards, and business impact.
        """
    ).strip(),
}


class QuestionAnswer(BaseModel):  # Single interview exchange stored in memory
    question: str
    answer: str


class AutoReplyContext(BaseModel):  # Candidate memory comprising resume and prior exchanges
    resume_summary: str
    history: List[QuestionAnswer] = Field(default_factory=list)
    competency: str | None = None
    project_anchor: str = ""
    targeted_criteria: List[str] = Field(default_factory=list)


class AutoReplyPlan(BaseModel):  # LLM-enforced candidate reply payload
    answer: str
    tone: str = "neutral"


class AutoReplyOutcome(BaseModel):  # Result returned to API callers with updated memory
    message: QuestionAnswer
    tone: str
    history: List[QuestionAnswer]


class AutoReplyAgent:  # Agent generating candidate responses from memory context
    def __init__(self, route: LlmRoute, schema: Type[AutoReplyPlan]) -> None:
        self._route = route
        self._schema = schema
        self._prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    dedent(
                        """
                        You are roleplaying the candidate in a job interview.
                        Only respond with how the candidate would naturally reply.
                        Strictly embody the provided persona without breaking character.
                        Keep answers grounded in the resume summary and prior exchanges.
                        Do not invent new qualifications beyond that context.
                        Reference concrete experiences when helpful, matching the requested depth level.
                        Candidate persona:\n{persona}
                        """
                    ).strip(),
                ),
                (
                    "human",
                    (
                        "Resume Summary:\n{resume_summary}\n\n"
                        "Active Competency: {competency}\n"
                        "Project Anchor: {project_anchor}\n"
                        "Targeted Criteria:\n{targeted}\n\n"
                        "Conversation Memory:\n{conversation}\n\n"
                        "Interviewer Prompt: {question}\n"
                        "Candidate reply depth level: {level}\n"
                        "Respond as the candidate with a concise, human answer."
                    ),
                ),
            ]
        )

    def invoke(
        self,
        question: str,
        *,
        memory: AutoReplyContext,
        level: int,
    ) -> AutoReplyOutcome:  # Run the auto-reply agent and update memory
        history = _build_history(memory.history)
        conversation = _format_history(history)
        competency = memory.competency or "general competency focus"
        anchor = memory.project_anchor.strip() or "(no shared project anchor)"
        persona, normalized_level = _persona_for_level(level)
        task = self._prompt.format(
            resume_summary=_clamp(memory.resume_summary),
            conversation=conversation,
            question=question.strip(),
            persona=persona,
            level=str(normalized_level),
            competency=competency,
            project_anchor=anchor,
            targeted=_format_targets(memory.targeted_criteria),
        )
        plan = call(task, self._schema, cfg=self._route)
        answer = plan.answer.strip()
        qa = QuestionAnswer(question=question.strip(), answer=answer)
        updated_history = list(memory.history) + [qa]
        tone = (plan.tone or "neutral").strip().lower()
        if tone not in {"neutral", "positive"}:
            tone = "neutral"
        return AutoReplyOutcome(message=qa, tone=tone, history=updated_history)


def auto_reply_with_config(
    question: str,
    *,
    resume_summary: str,
    history: Sequence[QuestionAnswer],
    level: int,
    competency: str | None = None,
    project_anchor: str = "",
    targeted_criteria: Sequence[str] | None = None,
    config_path: Path,
) -> AutoReplyOutcome:  # Convenience wrapper that loads configuration and dispatches the agent
    schemas = {AUTO_REPLY_AGENT_KEY: AutoReplyPlan}
    registry = load_app_registry(config_path, schemas)
    route, schema = registry[AUTO_REPLY_AGENT_KEY]
    agent = AutoReplyAgent(route, schema)
    context = AutoReplyContext(
        resume_summary=resume_summary,
        history=list(history),
        competency=competency,
        project_anchor=project_anchor,
        targeted_criteria=list(targeted_criteria or []),
    )
    return agent.invoke(question, memory=context, level=level)


def _persona_for_level(level: int) -> Tuple[str, int]:  # Map UI level to persona text and clamp bounds
    try:
        numeric = int(level)
    except Exception:  # noqa: BLE001
        numeric = 3
    clamped = max(1, min(5, numeric))
    persona = PERSONA_MAP.get(clamped, PERSONA_MAP[3])
    return persona, clamped


def _build_history(history: Sequence[QuestionAnswer]) -> InMemoryChatMessageHistory:  # Build LangChain memory from history
    chat_history = InMemoryChatMessageHistory()
    for turn in history:
        question = turn.question.strip()
        answer = turn.answer.strip()
        if question:
            chat_history.add_user_message(question)
        if answer:
            chat_history.add_ai_message(answer)
    return chat_history


def _format_history(history: InMemoryChatMessageHistory) -> str:  # Serialize memory into prompt text
    messages = history.messages
    if not messages:
        return "(none)"
    lines: List[str] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            lines.append(f"Interviewer: {message.content}")
        elif isinstance(message, AIMessage):
            lines.append(f"Candidate: {message.content}")
    return "\n".join(lines) if lines else "(none)"


def _format_targets(criteria: Sequence[str]) -> str:  # Format targeted criteria list for prompt context
    cleaned = [" ".join(item.split()) for item in criteria if item and item.strip()]
    if not cleaned:
        return "(no specific criteria)"
    return "\n".join(f"- {item}" for item in cleaned)


def _clamp(summary: str, limit: int = 600) -> str:  # Clamp resume summary for prompt hygiene
    compact = " ".join(summary.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


__all__ = [
    "AUTO_REPLY_AGENT_KEY",
    "AutoReplyAgent",
    "AutoReplyContext",
    "AutoReplyOutcome",
    "AutoReplyPlan",
    "QuestionAnswer",
    "auto_reply_with_config",
]
