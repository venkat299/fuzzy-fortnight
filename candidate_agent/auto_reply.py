from __future__ import annotations  # Candidate auto-answer agent implementation

from textwrap import dedent
from pathlib import Path
from typing import List, Sequence, Type

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from config import LlmRoute, load_app_registry
from llm_gateway import call

AUTO_REPLY_AGENT_KEY = "candidate_agent.auto_reply"  # Registry key for candidate auto replies


class QuestionAnswer(BaseModel):  # Single interview exchange stored in memory
    question: str
    answer: str


class AutoReplyContext(BaseModel):  # Candidate memory comprising resume and prior exchanges
    resume_summary: str
    history: List[QuestionAnswer] = Field(default_factory=list)


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
                        Keep answers grounded in the resume summary and prior exchanges.
                        Do not invent new qualifications beyond that context.
                        Reference concrete experiences when helpful, matching the requested depth level.
                        """
                    ).strip(),
                ),
                (
                    "human",
                    (
                        "Resume Summary:\n{resume_summary}\n\n"
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
        task = self._prompt.format(
            resume_summary=_clamp(memory.resume_summary),
            conversation=conversation,
            question=question.strip(),
            level=str(level),
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
    config_path: Path,
) -> AutoReplyOutcome:  # Convenience wrapper that loads configuration and dispatches the agent
    schemas = {AUTO_REPLY_AGENT_KEY: AutoReplyPlan}
    registry = load_app_registry(config_path, schemas)
    route, schema = registry[AUTO_REPLY_AGENT_KEY]
    agent = AutoReplyAgent(route, schema)
    context = AutoReplyContext(resume_summary=resume_summary, history=list(history))
    return agent.invoke(question, memory=context, level=level)


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
