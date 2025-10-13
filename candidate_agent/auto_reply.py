from __future__ import annotations  # Candidate auto-answer agent implementation

import json
import random
import re
from functools import lru_cache
from pathlib import Path
from textwrap import dedent
from typing import Any, Callable, Dict, List, Mapping, Sequence, Tuple, Type

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field, model_validator

from config import AppConfig, LlmRoute, NoisySettings, load_config, resolve_registry, load_app_registry
from llm_gateway import call

AUTO_REPLY_AGENT_KEY = "candidate_agent.auto_reply"  # Registry key for candidate auto replies
NOISY_AGENT_KEY = "candidate_agent.noisy_candidate"  # Registry key for noisy candidate answers


class PromptLibrary:  # System prompts for noisy candidate levels
    _templates: Dict[int, str] = {
        1: dedent(
            """
            You are NoisyCandidate-L1, a rushed novice interviewee. Answer in one short paragraph with simple words.
            Provide only the final answer with no extra format.
            """
        ).strip(),
        2: dedent(
            """
            You are NoisyCandidate-L2, a nervous junior interviewee. Reply in one concise paragraph and give only the final answer.
            """
        ).strip(),
        3: dedent(
            """
            You are NoisyCandidate-L3, an average candidate. Respond with a tight paragraph containing the final answer only.
            """
        ).strip(),
        4: dedent(
            """
            You are NoisyCandidate-L4, a solid senior candidate. Deliver a clear sequence of points in one paragraph with the final answer only.
            """
        ).strip(),
        5: dedent(
            """
            You are NoisyCandidate-L5, a concise expert candidate. Use precise terms and provide the final answer only.
            """
        ).strip(),
    }

    @classmethod
    def get(cls, level: int) -> str:
        if level not in cls._templates:
            raise ValueError("Unsupported noisy level")
        return cls._templates[level]


NoisyLevel = Dict[str, Any]


NOISY_LEVELS: Dict[int, NoisyLevel] = {  # Configured noise parameters per level
    1: {
        "max_words": 50,
        "vocab_ceiling": "2-syllable",
        "hedging": 0.5,
        "filler": 0.4,
        "mistakes": (2, 3),
        "grammar_p": 0.3,
        "typo_p": 0.2,
        "miss_p": 0.25,
    },
    2: {
        "max_words": 70,
        "hedging": 0.35,
        "filler": 0.25,
        "mistakes": (1, 2),
        "grammar_p": 0.2,
        "typo_p": 0.12,
        "miss_p": 0.15,
    },
    3: {
        "max_words": 90,
        "hedging": 0.2,
        "filler": 0.1,
        "mistakes": (0, 1),
        "grammar_p": 0.1,
        "typo_p": 0.06,
        "miss_p": 0.05,
    },
    4: {
        "max_words": 110,
        "hedging": 0.1,
        "filler": 0.05,
        "mistakes": (0, 1),
        "grammar_p": 0.04,
        "typo_p": 0.03,
        "miss_p": 0.0,
    },
    5: {
        "max_words": 120,
        "hedging": 0.05,
        "filler": 0.0,
        "mistakes": (0, 0),
        "grammar_p": 0.0,
        "typo_p": 0.0,
        "miss_p": 0.0,
    },
}


_FACTUAL_SLIPS = {
    "database": "datastore",
    "cache": "cash",
    "latency": "lateness",
    "throughput": "through-flow",
    "queue": "stack",
    "python": "pythons",
    "java": "java-ish",
    "index": "pointer list",
}


_CONNECTORS = ["therefore", "so", "because", "thus", "hence", "consequently"]


_NOISY_PROCESSOR: NoisyPostProcessor | None = None
_NOISY_OPTIONS: Dict[str, float] = {"temperature": 0.9, "top_p": 0.8}
_CONFIG_PATH = Path(__file__).resolve().parents[1] / "app_config.json"


class NoisyPostProcessor:  # Applies noisy transformations to answers
    def __init__(self, *, seed: int | None = None, enable_spelling_mistakes: bool = True) -> None:
        self._rng = random.Random(seed)
        self._spelling_mistakes = enable_spelling_mistakes

    def apply(self, text: str, level: int) -> str:
        spec = NOISY_LEVELS[level]
        answer = text.strip()
        answer = self._maybe_prefix_hedge(answer, spec["hedging"])
        answer = self._insert_fillers(answer, spec["filler"])
        answer = self._maybe_apply_grammar(answer, spec["grammar_p"])
        answer = self._maybe_drop_word(answer, spec["miss_p"])
        answer = self._apply_typos(answer, spec["typo_p"])
        answer = self._apply_mistake_hooks(answer, level, spec["mistakes"])
        answer = self._truncate(answer, spec["max_words"])
        return answer

    def _maybe_prefix_hedge(self, text: str, probability: float) -> str:
        if not text or probability <= 0:
            return text
        if self._rng.random() < probability:
            hedge = self._rng.choice(["I think", "maybe", "I guess"])
            return f"{hedge} {text}"
        return text

    def _insert_fillers(self, text: str, probability: float) -> str:
        if probability <= 0 or not text:
            return text
        parts = re.split(r"([,.;])", text)
        if len(parts) == 1:
            return text
        inserts = 0
        result: List[str] = []
        for part in parts:
            if part in {",", ";", "."} and inserts < 3 and self._rng.random() < probability and result:
                filler = self._rng.choice(["uh", "um"])
                result[-1] = result[-1].rstrip() + f" {filler}"
                inserts += 1
            result.append(part)
        return "".join(result)

    def _apply_typos(self, text: str, probability: float) -> str:
        if not self._spelling_mistakes or probability <= 0:
            return text
        tokens = text.split()
        updated: List[str] = []
        for token in tokens:
            if len(token) >= 4 and self._rng.random() < probability:
                body = list(token)
                idx = self._rng.randint(0, len(body) - 2)
                body[idx], body[idx + 1] = body[idx + 1], body[idx]
                token = "".join(body)
            updated.append(token)
        return " ".join(updated)

    def _maybe_apply_grammar(self, text: str, probability: float) -> str:
        if probability <= 0 or not text:
            return text
        if self._rng.random() >= probability:
            return text
        replacements = [
            (r"\bis\b", "are"),
            (r"\bdoes\b", "do"),
            (r"\bhas\b", "have"),
        ]
        pattern, repl = self._rng.choice(replacements)
        return re.sub(pattern, repl, text, count=1)

    def _maybe_drop_word(self, text: str, probability: float) -> str:
        if probability <= 0:
            return text
        tokens = text.split()
        if len(tokens) <= 3 or self._rng.random() >= probability:
            return text
        index = self._rng.randrange(len(tokens))
        del tokens[index]
        return " ".join(tokens)

    def _apply_mistake_hooks(self, text: str, level: int, span: Tuple[int, int]) -> str:
        if level > 3:
            return text
        lower, upper = span
        count = self._rng.randint(lower, upper)
        if count <= 0:
            return text
        operations: List[Callable[[str], str]] = [
            self._factual_slip,
            self._calc_slip,
            self._logic_gap,
        ]
        self._rng.shuffle(operations)
        answer = text
        applied = 0
        for op in operations:
            if applied >= count:
                break
            updated = op(answer)
            if updated != answer:
                answer = updated
                applied += 1
        return answer

    def _factual_slip(self, text: str) -> str:
        for term, slip in _FACTUAL_SLIPS.items():
            pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            if pattern.search(text):
                return pattern.sub(slip, text, count=1)
        return text

    def _calc_slip(self, text: str) -> str:
        match = re.search(r"\b\d+(?:\.\d+)?\b", text)
        if not match:
            return text
        value = match.group(0)
        if "." in value:
            try:
                number = float(value)
            except ValueError:
                return text
            offset = -0.5 if self._rng.random() < 0.5 else 0.5
            new_value = f"{number + offset:.1f}"
        else:
            try:
                number = int(value)
            except ValueError:
                return text
            delta = -1 if self._rng.random() < 0.5 else 1
            new_value = str(number + delta)
        start, end = match.span()
        return text[:start] + new_value + text[end:]

    def _logic_gap(self, text: str) -> str:
        for connector in _CONNECTORS:
            pattern = re.compile(rf"\b{connector}\b", re.IGNORECASE)
            if pattern.search(text):
                return pattern.sub("", text, count=1).replace("  ", " ").strip()
        return text

    def _truncate(self, text: str, max_words: int) -> str:
        words = text.split()
        if len(words) <= max_words:
            return text
        return " ".join(words[:max_words])


class NoisyAnswerPlan(BaseModel):  # LLM-enforced noisy answer payload
    answer: str

    @classmethod
    def from_raw_content(cls, content: str) -> "NoisyAnswerPlan":  # Allow raw text fallbacks
        text = content.strip()
        if not text:
            return cls(answer="")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return cls(answer=text)
        if isinstance(parsed, str):
            return cls(answer=parsed)
        if isinstance(parsed, dict):
            answer = _first_string(parsed, ["answer", "content", "message"]) or text
            return cls(answer=answer)
        return cls(answer=text)


@lru_cache(maxsize=1)
def _load_app_config() -> AppConfig:  # Cached configuration loader
    return load_config(_CONFIG_PATH)


@lru_cache(maxsize=1)
def _load_noisy_settings() -> NoisySettings:  # Access noisy candidate settings
    return _load_app_config().noisy


def set_noisy_seed(seed: int | None) -> None:  # Configure deterministic noise for testing
    global _NOISY_PROCESSOR
    settings = _load_noisy_settings()
    _NOISY_PROCESSOR = NoisyPostProcessor(
        seed=seed, enable_spelling_mistakes=settings.enable_spelling_mistakes
    )


def configure_noisy_generation(*, temperature: float | None = None, top_p: float | None = None) -> None:  # Adjust sampling options
    if temperature is not None:
        _NOISY_OPTIONS["temperature"] = float(temperature)
    if top_p is not None:
        _NOISY_OPTIONS["top_p"] = float(top_p)


def generate_noisy_answer(question: str, level: int) -> str:  # Public API to produce noisy answers
    if level not in NOISY_LEVELS:
        raise ValueError("Unsupported noisy level")
    system_prompt = PromptLibrary.get(level)
    prompt = ChatPromptTemplate.from_messages([("system", "{system}"), ("human", "{question}")])
    task = prompt.format(system=system_prompt, question=question.strip())
    route = _load_noisy_route()
    options = _generation_options()
    plan = call(task, NoisyAnswerPlan, cfg=route, options=options)
    processor = _get_noisy_processor()
    return processor.apply(plan.answer, level)


@lru_cache(maxsize=1)
def _load_noisy_route() -> LlmRoute:  # Load noisy candidate route from config
    cfg = _load_app_config()
    registry = resolve_registry(cfg, {NOISY_AGENT_KEY: NoisyAnswerPlan})
    route, _ = registry[NOISY_AGENT_KEY]
    return route


def _get_noisy_processor() -> NoisyPostProcessor:  # Lazy-create noisy post processor
    global _NOISY_PROCESSOR
    if _NOISY_PROCESSOR is None:
        settings = _load_noisy_settings()
        _NOISY_PROCESSOR = NoisyPostProcessor(
            enable_spelling_mistakes=settings.enable_spelling_mistakes
        )
    return _NOISY_PROCESSOR


def _generation_options() -> Dict[str, float]:  # Clone generation sampling options
    return {key: value for key, value in _NOISY_OPTIONS.items() if value is not None}

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

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy(cls, value: Any) -> Dict[str, Any]:  # Accept legacy dict or raw string formats
        if isinstance(value, str):
            return {"answer": value, "tone": "neutral"}
        if isinstance(value, dict):
            if "answer" in value or "tone" in value:
                return value
            content = value.get("content")
            if isinstance(content, str):
                tone = value.get("tone") or value.get("style") or value.get("mood")
                return {"answer": content, "tone": tone or "neutral"}
        return value

    @classmethod
    def from_raw_content(cls, content: str) -> "AutoReplyPlan":  # Build plan from non-JSON LLM content
        text = content.strip()
        if not text:
            return cls(answer="", tone="neutral")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return cls(answer=text, tone="neutral")
        if isinstance(parsed, str):
            return cls(answer=parsed, tone="neutral")
        if isinstance(parsed, dict):
            answer = _first_string(parsed, ["answer", "content", "message"]) or text
            tone = _canonical_tone(_first_string(parsed, ["tone", "style", "mood"]))
            return cls(answer=answer, tone=tone)
        return cls(answer=text, tone="neutral")


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
                        Follow this noisy persona guide:\n{noisy_style}
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
        normalized_level = _normalized_level(level)
        noisy_style = PromptLibrary.get(normalized_level)
        task = self._prompt.format(
            resume_summary=_clamp(memory.resume_summary),
            conversation=conversation,
            question=question.strip(),
            noisy_style=noisy_style,
            level=str(normalized_level),
            competency=competency,
            project_anchor=anchor,
            targeted=_format_targets(memory.targeted_criteria),
        )
        plan = call(task, self._schema, cfg=self._route)
        processor = _get_noisy_processor()
        answer = processor.apply(plan.answer.strip(), normalized_level)
        qa = QuestionAnswer(question=question.strip(), answer=answer)
        updated_history = list(memory.history) + [qa]
        tone = _canonical_tone(plan.tone)
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


def _normalized_level(level: int) -> int:  # Clamp noisy level to supported range
    try:
        numeric = int(level)
    except Exception:  # noqa: BLE001
        numeric = 3
    return max(1, min(5, numeric))


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


def _first_string(data: Mapping[str, Any], keys: Sequence[str]) -> str:  # Fetch first non-empty string from mapping
    for key in keys:
        value = data.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return ""


def _canonical_tone(value: str | None) -> str:  # Normalize tone metadata with neutral fallback
    normalized = (value or "").strip().lower()
    return "positive" if normalized == "positive" else "neutral"


__all__ = [
    "AUTO_REPLY_AGENT_KEY",
    "NOISY_AGENT_KEY",
    "AutoReplyAgent",
    "AutoReplyContext",
    "AutoReplyOutcome",
    "AutoReplyPlan",
    "PromptLibrary",
    "NoisyPostProcessor",
    "NoisyAnswerPlan",
    "QuestionAnswer",
    "configure_noisy_generation",
    "generate_noisy_answer",
    "set_noisy_seed",
    "auto_reply_with_config",
]
