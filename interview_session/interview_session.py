from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from textwrap import dedent
from threading import RLock
from typing import Any, Callable, Dict, List, Literal, Optional, Protocol, Sequence, Tuple
from uuid import uuid4

from langchain.memory import ConversationEntityMemory
from langchain.memory.chat_memory import BaseChatMemory
from pydantic import BaseModel, Field

from config import LlmRoute, load_app_registry
from interview_evaluation import CandidateAnswer, EvaluationResult, evaluate_response
from llm_gateway import call
from rubric_design import Rubric, RubricAnchor

StageLiteral = Literal["warmup", "competency", "wrapup", "complete"]
EventTypeLiteral = Literal[
    "stage_entered",
    "question",
    "answer",
    "evaluation",
    "hint",
    "follow_up",
    "checkpoint",
]


class PersonaConfig(BaseModel):  # Persona tone configuration
    name: str
    probing_style: str
    hint_style: str
    encouragement: str


class CandidateProfile(BaseModel):  # Candidate resume snapshot
    candidate_name: str
    resume_summary: str
    experience_years: str
    highlighted_experiences: List[str] = Field(default_factory=list)


class GeneratedQuestion(BaseModel):  # Question emitted by the LLM
    question: str
    reasoning: str
    follow_up_prompt: str
    escalation: Literal["broad", "why", "how", "challenge", "hint", "edge"]


class QuestionContext(BaseModel):  # Input context for question generator
    interview_id: str
    stage: StageLiteral
    persona: PersonaConfig
    competency: Optional[str]
    resume_summary: str
    experiences: List[str]
    candidate_name: str = ""
    rubric: Optional[Rubric]
    asked_questions: List[str]
    rubric_progress: float = 0.0
    last_evaluation: Optional[EvaluationResult] = None
    memory_entities: List[str] = Field(default_factory=list)
    criterion_status: List["CriterionProgress"] = Field(default_factory=list)
    question_index: int = 0


class CriterionProgress(BaseModel):  # Track criterion scoring progress
    criterion: str
    weight: float = 0.0
    latest_score: float = 0.0
    rationale: str = ""

    def coverage_label(self) -> str:
        if self.latest_score >= 4.0:
            return "robust"
        if self.latest_score >= 3.0:
            return "developing"
        if self.latest_score > 0:
            return "emerging"
        return "unexplored"


class CompetencyRuntimeState(BaseModel):  # Runtime data for competency
    rubric: Rubric
    total_score: float = 0.0
    rubric_filled: bool = False
    questions: List[str] = Field(default_factory=list)
    evaluations: List[EvaluationResult] = Field(default_factory=list)
    criteria: Dict[str, CriterionProgress] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if not self.criteria:
            self.criteria = {
                criterion.name: CriterionProgress(
                    criterion=criterion.name,
                    weight=criterion.weight,
                )
                for criterion in self.rubric.criteria
            }

    def apply_evaluation(self, result: EvaluationResult) -> None:
        self.total_score = result.total_score
        self.rubric_filled = result.rubric_filled
        self.evaluations.append(result)
        for item in result.criterion_scores:
            weight = next(
                (criterion.weight for criterion in self.rubric.criteria if criterion.name == item.criterion),
                0.0,
            )
            self.criteria[item.criterion] = CriterionProgress(
                criterion=item.criterion,
                weight=weight,
                latest_score=item.score,
                rationale=item.rationale,
            )


class InterviewCheckpoint(BaseModel):  # Persisted checkpoint snapshot
    checkpoint_id: str
    saved_at: datetime
    transcript: List["InterviewTurn"]
    competency_scores: Dict[str, float]


class InterviewTurn(BaseModel):  # Single dialogue turn
    role: Literal["interviewer", "candidate", "system"]
    stage: StageLiteral
    competency: Optional[str]
    content: str


class InterviewEvent(BaseModel):  # Timeline event emitted by the flow
    event_id: int
    created_at: datetime
    stage: StageLiteral
    competency: Optional[str]
    event_type: EventTypeLiteral
    payload: Dict[str, Any] = Field(default_factory=dict)


class PendingQuestion(BaseModel):  # Question awaiting candidate response
    question: GeneratedQuestion
    stage: StageLiteral
    competency: Optional[str]
    asked_at: datetime


class InterviewSessionState(BaseModel):  # Graph session state
    interview_id: str
    session_id: str = Field(default_factory=lambda: uuid4().hex)
    stage: StageLiteral = "warmup"
    persona: PersonaConfig
    profile: CandidateProfile
    competencies: Dict[str, CompetencyRuntimeState]
    competency_order: List[str]
    active_index: int = 0
    transcript: List[InterviewTurn] = Field(default_factory=list)
    checkpoints: List[InterviewCheckpoint] = Field(default_factory=list)
    last_checkpoint: Optional[datetime] = None
    events: List["InterviewEvent"] = Field(default_factory=list)
    next_event_id: int = 1
    started_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    pending_question: Optional[PendingQuestion] = None
    warmup_questions_asked: int = 0
    wrapup_questions_asked: int = 0
    questions_asked: int = 0

    def active_competency(self) -> Optional[Tuple[str, CompetencyRuntimeState]]:
        if 0 <= self.active_index < len(self.competency_order):
            name = self.competency_order[self.active_index]
            return name, self.competencies[name]
        return None


class InterviewPlan(BaseModel):  # Input payload to start interview
    interview_id: str
    persona: PersonaConfig
    profile: CandidateProfile
    rubrics: Sequence[Rubric]

    def build_state(self) -> InterviewSessionState:
        competencies = {
            rubric.competency: CompetencyRuntimeState(rubric=rubric)
            for rubric in self.rubrics
        }
        order = [rubric.competency for rubric in self.rubrics]
        return InterviewSessionState(
            interview_id=self.interview_id,
            persona=self.persona,
            profile=self.profile,
            competencies=competencies,
            competency_order=order,
        )


class InterviewFlowConfig(BaseModel):  # Flow tuning parameters
    checkpoint_interval_minutes: int = Field(default=3, ge=1)
    max_questions_per_competency: int = Field(default=4, ge=1)
    warmup_question_count: int = Field(default=1, ge=1)


class InterviewTranscript(BaseModel):  # Output session summary
    interview_id: str
    persona: PersonaConfig
    profile: CandidateProfile
    turns: List[InterviewTurn]
    checkpoints: List[InterviewCheckpoint]
    competencies: Dict[str, CompetencyRuntimeState]
    events: List["InterviewEvent"]


class CheckpointMemory:  # Simple checkpoint persistence wrapper
    def __init__(self) -> None:
        self._store: Dict[str, InterviewCheckpoint] = {}

    def save(self, state: InterviewSessionState) -> InterviewCheckpoint:
        checkpoint = InterviewCheckpoint(
            checkpoint_id=str(uuid4()),
            saved_at=datetime.utcnow(),
            transcript=list(state.transcript),
            competency_scores={name: data.total_score for name, data in state.competencies.items()},
        )
        self._store[checkpoint.checkpoint_id] = checkpoint
        return checkpoint

    def latest(self) -> Optional[InterviewCheckpoint]:
        if not self._store:
            return None
        return max(self._store.values(), key=lambda item: item.saved_at)


class CandidateResponder(Protocol):  # Response provider interface
    def respond(self, question: GeneratedQuestion, *, competency: Optional[str], stage: StageLiteral) -> str:
        ...


class QuestionGeneratorTool:  # Wrapper for question generator LLM
    def __init__(self, route: LlmRoute) -> None:
        self._route = route

    def generate(self, context: QuestionContext) -> GeneratedQuestion:
        task = _build_question_task(context)
        logger.info("Question generation prompt:\n%s", task)
        result = call(task, GeneratedQuestion, cfg=self._route)
        logger.info(
            "Question generation result:\n%s",
            result.model_dump_json(indent=2),
        )
        return result


class RubricEvaluatorTool:  # Wrapper around evaluation module
    def __init__(self, route: LlmRoute) -> None:
        self._route = route

    def evaluate(self, answer: CandidateAnswer) -> EvaluationResult:
        return evaluate_response(answer, route=self._route)


class InterviewMemoryManager:  # Manage LangChain memory + checkpoints
    def __init__(self, entity_memory: Optional[BaseChatMemory], checkpoints: CheckpointMemory) -> None:
        self.entity_memory = entity_memory
        self.checkpoints = checkpoints

    def remember(self, question: str, answer: str) -> None:
        if self.entity_memory is None:
            return
        self.entity_memory.save_context(
            {"role": "interviewer", "content": question},
            {"role": "candidate", "content": answer},
        )

    def entities(self) -> List[str]:
        if self.entity_memory is None:
            return []
        data = self.entity_memory.load_memory_variables({})
        entities = data.get("entities")
        if isinstance(entities, list):
            return [str(item) for item in entities]
        if isinstance(entities, str):
            return [entities]
        return []


class EngineStartResult(BaseModel):  # Start session snapshot
    state: InterviewSessionState
    events: List[InterviewEvent]
    question: Optional[PendingQuestion]


class EngineTurnResult(BaseModel):  # Turn processing bundle
    state: InterviewSessionState
    events: List[InterviewEvent]
    question: Optional[PendingQuestion]
    evaluation: Optional[EvaluationResult]
    completed: bool


@dataclass
class SessionRuntime:  # Stored session bundle
    engine: "InterviewSessionEngine"
    state: InterviewSessionState


class SessionStore(Protocol):  # Session persistence interface
    def create(self, session: SessionRuntime) -> None: ...

    def get(self, session_id: str) -> SessionRuntime: ...

    def save(self, session: SessionRuntime) -> None: ...

    def delete(self, session_id: str) -> None: ...


class InMemorySessionStore(SessionStore):  # Thread-safe in-memory store
    def __init__(self) -> None:
        self._sessions: Dict[str, SessionRuntime] = {}
        self._lock = RLock()

    def create(self, session: SessionRuntime) -> None:  # Persist new session
        with self._lock:
            self._sessions[session.state.session_id] = session

    def get(self, session_id: str) -> SessionRuntime:  # Load session
        with self._lock:
            stored = self._sessions.get(session_id)
        if stored is None:
            raise KeyError(session_id)
        return stored

    def save(self, session: SessionRuntime) -> None:  # Update session bundle
        with self._lock:
            self._sessions[session.state.session_id] = session

    def delete(self, session_id: str) -> None:  # Drop session state
        with self._lock:
            self._sessions.pop(session_id, None)


class SessionNotFoundError(KeyError):  # Raised when session missing
    pass


class SessionExpiredError(RuntimeError):  # Raised when session expired
    def __init__(self, session_id: str) -> None:
        super().__init__(session_id)
        self.session_id = session_id


class SessionLifecycleConfig(BaseModel):  # Session timeout tuning
    timeout_minutes: int = Field(default=30, ge=1)


class InterviewSessionEngine:  # Interactive interview driver
    def __init__(
        self,
        question_tool: QuestionGeneratorTool,
        evaluator: RubricEvaluatorTool,
        memory: InterviewMemoryManager,
        config: InterviewFlowConfig,
    ) -> None:
        self._question_tool = question_tool
        self._evaluator = evaluator
        self._memory = memory
        self._config = config

    def start(self, plan: InterviewPlan) -> EngineStartResult:  # Begin interactive session
        state = plan.build_state()
        state.stage = "warmup"
        state.events = []
        state.transcript = []
        state.checkpoints = []
        state.next_event_id = 1
        now = datetime.utcnow()
        state.started_at = now
        state.last_activity = now
        start_id = state.next_event_id
        self._record_event(state, stage="warmup", event_type="stage_entered")
        question = self._begin_warmup(state)
        events = self._collect_events(state, start_id)
        return EngineStartResult(state=state, events=events, question=question)

    def answer(self, state: InterviewSessionState, answer: str) -> EngineTurnResult:  # Apply candidate answer
        pending = state.pending_question
        if pending is None:
            raise ValueError("No pending question to answer")
        state.pending_question = None
        state.last_activity = datetime.utcnow()
        start_id = state.next_event_id
        stage = pending.stage
        competency = pending.competency
        self._record_event(
            state,
            stage=stage,
            event_type="answer",
            competency=competency,
            payload={"answer": answer},
        )
        state.transcript.append(
            InterviewTurn(role="candidate", stage=stage, competency=competency, content=answer)
        )
        self._memory.remember(pending.question.question, answer)
        evaluation: Optional[EvaluationResult] = None
        next_question: Optional[PendingQuestion]
        if stage == "warmup":
            next_question = self._after_warmup_answer(state)
        elif stage == "competency":
            evaluation = self._evaluate_competency_answer(state, pending, answer)
            next_question = self._after_competency_answer(state)
        elif stage == "wrapup":
            next_question = self._after_wrapup_answer(state)
        else:
            raise ValueError(f"Unsupported stage {stage}")
        events = self._collect_events(state, start_id)
        completed = state.stage == "complete"
        return EngineTurnResult(
            state=state,
            events=events,
            question=next_question,
            evaluation=evaluation,
            completed=completed,
        )

    def _begin_warmup(self, state: InterviewSessionState) -> Optional[PendingQuestion]:
        if self._config.warmup_question_count <= 0:
            return self._advance_after_warmup(state)
        return self._generate_warmup_question(state)

    def _after_warmup_answer(self, state: InterviewSessionState) -> Optional[PendingQuestion]:
        checkpoint = self._maybe_checkpoint(state)
        if checkpoint is not None:
            self._record_checkpoint_event(state, "warmup", None, checkpoint)
        if state.warmup_questions_asked < self._config.warmup_question_count:
            return self._generate_warmup_question(state)
        return self._advance_after_warmup(state)

    def _advance_after_warmup(self, state: InterviewSessionState) -> Optional[PendingQuestion]:
        if state.competency_order:
            return self._enter_competency(state)
        return self._enter_wrapup(state)

    def _enter_competency(self, state: InterviewSessionState) -> Optional[PendingQuestion]:
        active = state.active_competency()
        if active is None:
            return self._enter_wrapup(state)
        name, runtime = active
        state.stage = "competency"
        if not runtime.questions:
            self._record_event(
                state,
                stage="competency",
                event_type="stage_entered",
                competency=name,
            )
        return self._generate_competency_question(state, name, runtime)

    def _after_competency_answer(self, state: InterviewSessionState) -> Optional[PendingQuestion]:
        active = state.active_competency()
        if active is None:
            return self._enter_wrapup(state)
        name, runtime = active
        if runtime.rubric_filled or len(runtime.questions) >= self._config.max_questions_per_competency:
            state.active_index += 1
            return self._enter_competency(state)
        return self._generate_competency_question(state, name, runtime)

    def _after_wrapup_answer(self, state: InterviewSessionState) -> Optional[PendingQuestion]:
        checkpoint = self._maybe_checkpoint(state, force=True)
        if checkpoint is not None:
            self._record_checkpoint_event(state, "wrapup", None, checkpoint)
        state.stage = "complete"
        return None

    def _generate_warmup_question(self, state: InterviewSessionState) -> PendingQuestion:
        context = QuestionContext(
            interview_id=state.interview_id,
            stage="warmup",
            persona=state.persona,
            competency=None,
            resume_summary=state.profile.resume_summary,
            experiences=state.profile.highlighted_experiences,
            candidate_name=state.profile.candidate_name,
            rubric=None,
            asked_questions=[
                turn.content for turn in state.transcript if turn.stage == "warmup" and turn.role == "interviewer"
            ],
            memory_entities=self._memory.entities(),
        )
        question = self._question_tool.generate(context)
        return self._record_question(state, question, "warmup", None)

    def _generate_competency_question(
        self,
        state: InterviewSessionState,
        competency: str,
        runtime: CompetencyRuntimeState,
    ) -> PendingQuestion:
        context = QuestionContext(
            interview_id=state.interview_id,
            stage="competency",
            persona=state.persona,
            competency=competency,
            resume_summary=state.profile.resume_summary,
            experiences=state.profile.highlighted_experiences,
            candidate_name=state.profile.candidate_name,
            rubric=runtime.rubric,
            asked_questions=runtime.questions,
            rubric_progress=runtime.total_score,
            last_evaluation=runtime.evaluations[-1] if runtime.evaluations else None,
            memory_entities=self._memory.entities(),
            criterion_status=[
                runtime.criteria.get(
                    criterion.name,
                    CriterionProgress(criterion=criterion.name, weight=criterion.weight),
                )
                for criterion in runtime.rubric.criteria
            ],
            question_index=len(runtime.questions),
        )
        question = self._question_tool.generate(context)
        runtime.questions.append(question.question)
        return self._record_question(state, question, "competency", competency)

    def _generate_wrapup_question(self, state: InterviewSessionState) -> PendingQuestion:
        context = QuestionContext(
            interview_id=state.interview_id,
            stage="wrapup",
            persona=state.persona,
            competency=None,
            resume_summary=state.profile.resume_summary,
            experiences=state.profile.highlighted_experiences,
            candidate_name=state.profile.candidate_name,
            rubric=None,
            asked_questions=[
                turn.content for turn in state.transcript if turn.stage == "wrapup" and turn.role == "interviewer"
            ],
            memory_entities=self._memory.entities(),
        )
        question = self._question_tool.generate(context)
        return self._record_question(state, question, "wrapup", None)

    def _enter_wrapup(self, state: InterviewSessionState) -> Optional[PendingQuestion]:
        if state.stage != "wrapup":
            state.stage = "wrapup"
            self._record_event(state, stage="wrapup", event_type="stage_entered")
        if state.wrapup_questions_asked > 0:
            return None
        return self._generate_wrapup_question(state)

    def _record_question(
        self,
        state: InterviewSessionState,
        question: GeneratedQuestion,
        stage: StageLiteral,
        competency: Optional[str],
    ) -> PendingQuestion:
        self._record_event(
            state,
            stage=stage,
            event_type="question",
            competency=competency,
            payload=question.model_dump(),
        )
        state.transcript.append(
            InterviewTurn(role="interviewer", stage=stage, competency=competency, content=question.question)
        )
        if stage == "warmup":
            state.warmup_questions_asked += 1
        elif stage == "wrapup":
            state.wrapup_questions_asked += 1
        state.questions_asked += 1
        pending = PendingQuestion(
            question=question,
            stage=stage,
            competency=competency,
            asked_at=datetime.utcnow(),
        )
        state.pending_question = pending
        return pending

    def _evaluate_competency_answer(
        self,
        state: InterviewSessionState,
        pending: PendingQuestion,
        answer: str,
    ) -> EvaluationResult:
        competency = pending.competency
        if competency is None:
            raise ValueError("Competency answer missing competency name")
        runtime = state.competencies[competency]
        evaluation = self._evaluator.evaluate(
            CandidateAnswer(
                interview_id=state.interview_id,
                competency=competency,
                question=pending.question.question,
                answer=answer,
                rubric=runtime.rubric,
                persona=state.persona.name,
                stage="competency",
                asked_follow_ups=runtime.questions,
            )
        )
        runtime.apply_evaluation(evaluation)
        self._record_event(
            state,
            stage="competency",
            event_type="evaluation",
            competency=competency,
            payload=evaluation.model_dump(),
        )
        if evaluation.follow_up_needed and not runtime.rubric_filled:
            self._record_event(
                state,
                stage="competency",
                event_type="follow_up",
                competency=competency,
                payload={"message": "Evaluator suggests a probing follow-up."},
            )
            state.transcript.append(
                InterviewTurn(
                    role="system",
                    stage="competency",
                    competency=competency,
                    content="Evaluator suggests a probing follow-up.",
                )
            )
        if evaluation.hints:
            for hint in evaluation.hints:
                self._record_event(
                    state,
                    stage="competency",
                    event_type="hint",
                    competency=competency,
                    payload={"hint": hint},
                )
                state.transcript.append(
                    InterviewTurn(
                        role="system",
                        stage="competency",
                        competency=competency,
                        content=f"Hint: {hint}",
                    )
                )
        checkpoint = self._maybe_checkpoint(state)
        if checkpoint is not None:
            self._record_checkpoint_event(state, "competency", competency, checkpoint)
        return evaluation

    def _record_checkpoint_event(
        self,
        state: InterviewSessionState,
        stage: StageLiteral,
        competency: Optional[str],
        checkpoint: InterviewCheckpoint,
    ) -> None:
        self._record_event(
            state,
            stage=stage,
            event_type="checkpoint",
            competency=competency,
            payload={
                "checkpoint_id": checkpoint.checkpoint_id,
                "saved_at": checkpoint.saved_at.isoformat(),
                "competency_scores": checkpoint.competency_scores,
            },
        )

    def _collect_events(self, state: InterviewSessionState, start_id: int) -> List[InterviewEvent]:
        return [event for event in state.events if event.event_id >= start_id]

    def _record_event(
        self,
        state: InterviewSessionState,
        *,
        stage: StageLiteral,
        event_type: EventTypeLiteral,
        competency: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        event = InterviewEvent(
            event_id=state.next_event_id,
            created_at=datetime.utcnow(),
            stage=stage,
            competency=competency,
            event_type=event_type,
            payload=payload or {},
        )
        state.events.append(event)
        state.next_event_id += 1

    def _maybe_checkpoint(
        self,
        state: InterviewSessionState,
        *,
        force: bool = False,
    ) -> Optional[InterviewCheckpoint]:
        now = datetime.utcnow()
        if force or state.last_checkpoint is None:
            checkpoint = self._memory.checkpoints.save(state)
            state.checkpoints.append(checkpoint)
            state.last_checkpoint = checkpoint.saved_at
            return checkpoint
        elapsed = now - state.last_checkpoint
        if elapsed >= timedelta(minutes=self._config.checkpoint_interval_minutes):
            checkpoint = self._memory.checkpoints.save(state)
            state.checkpoints.append(checkpoint)
            state.last_checkpoint = checkpoint.saved_at
            return checkpoint
        return None


class SessionStartResult(BaseModel):  # Managed session start payload
    session_id: str
    state: InterviewSessionState
    events: List[InterviewEvent]
    question: Optional[PendingQuestion]


class SessionTurnResult(BaseModel):  # Managed turn payload
    session_id: str
    state: InterviewSessionState
    events: List[InterviewEvent]
    question: Optional[PendingQuestion]
    evaluation: Optional[EvaluationResult]
    completed: bool


class InterviewSessionManager:  # Session lifecycle orchestrator
    def __init__(
        self,
        engine_factory: Callable[[], InterviewSessionEngine],
        store: SessionStore,
        lifecycle: SessionLifecycleConfig,
    ) -> None:
        self._engine_factory = engine_factory
        self._store = store
        self._lifecycle = lifecycle

    def start_session(self, plan: InterviewPlan) -> SessionStartResult:  # Start and persist session
        engine = self._engine_factory()
        result = engine.start(plan)
        runtime = SessionRuntime(engine=engine, state=result.state)
        self._store.create(runtime)
        return SessionStartResult(
            session_id=result.state.session_id,
            state=result.state,
            events=result.events,
            question=result.question,
        )

    def submit_answer(self, session_id: str, answer: str) -> SessionTurnResult:  # Process candidate turn
        try:
            runtime = self._store.get(session_id)
        except KeyError as exc:
            raise SessionNotFoundError(session_id) from exc
        state = runtime.state
        if self._is_expired(state):
            self._store.delete(session_id)
            raise SessionExpiredError(session_id)
        turn = runtime.engine.answer(state, answer)
        if turn.completed:
            self._store.delete(session_id)
        else:
            runtime.state = turn.state
            self._store.save(runtime)
        return SessionTurnResult(
            session_id=session_id,
            state=turn.state,
            events=turn.events,
            question=turn.question,
            evaluation=turn.evaluation,
            completed=turn.completed,
        )

    def _is_expired(self, state: InterviewSessionState) -> bool:  # Determine timeout
        age = datetime.utcnow() - state.last_activity
        limit = timedelta(minutes=self._lifecycle.timeout_minutes)
        return age > limit

def start_interview(
    plan: InterviewPlan,
    *,
    question_tool: QuestionGeneratorTool,
    evaluator: RubricEvaluatorTool,
    memory: Optional[InterviewMemoryManager] = None,
    responder: Optional[CandidateResponder] = None,
    config: Optional[InterviewFlowConfig] = None,
) -> InterviewTranscript:  # Entry point to execute interview
    if responder is None:
        raise ValueError("Candidate responder must be provided")
    if memory is None:
        entity_memory: Optional[BaseChatMemory]
        try:
            entity_memory = ConversationEntityMemory(llm=None)  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001
            entity_memory = None
        memory = InterviewMemoryManager(entity_memory, CheckpointMemory())
    if config is None:
        config = InterviewFlowConfig()
    engine = InterviewSessionEngine(question_tool, evaluator, memory, config)
    start_bundle = engine.start(plan)
    state = start_bundle.state
    pending = start_bundle.question
    while pending is not None:
        answer_text = responder.respond(
            pending.question,
            competency=pending.competency,
            stage=pending.stage,
        )
        turn_bundle = engine.answer(state, answer_text)
        pending = turn_bundle.question
    return InterviewTranscript(
        interview_id=state.interview_id,
        persona=state.persona,
        profile=state.profile,
        turns=state.transcript,
        checkpoints=state.checkpoints,
        competencies=state.competencies,
        events=state.events,
    )


def build_session_with_config(
    plan: InterviewPlan,
    responder: CandidateResponder,
    *,
    config_path: Path,
    entity_memory: Optional[BaseChatMemory] = None,
    checkpoint_memory: Optional[CheckpointMemory] = None,
    config: Optional[InterviewFlowConfig] = None,
) -> InterviewTranscript:  # Helper to load routes from config
    schemas = {
        "interview_session.generate_question": GeneratedQuestion,
        "interview_evaluation.evaluate_response": EvaluationResult,
    }
    registry = load_app_registry(config_path, schemas)
    question_route, _ = registry["interview_session.generate_question"]
    evaluation_route, _ = registry["interview_evaluation.evaluate_response"]
    if entity_memory is None:
        try:
            entity_memory = ConversationEntityMemory(llm=None)  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001
            entity_memory = None
    memory = InterviewMemoryManager(entity_memory, checkpoint_memory or CheckpointMemory())
    question_tool = QuestionGeneratorTool(question_route)
    evaluator = RubricEvaluatorTool(evaluation_route)
    return start_interview(
        plan,
        question_tool=question_tool,
        evaluator=evaluator,
        memory=memory,
        responder=responder,
        config=config,
    )


def _build_question_task(context: QuestionContext) -> str:  # Compose prompt for question generator
    persona = context.persona
    stage_objective = _stage_objective(context)
    asked = "\n".join(f"- {item}" for item in context.asked_questions) or "(none yet)"
    entities = "\n".join(f"- {item}" for item in context.memory_entities) or "(none captured)"
    evaluation_summary = _format_evaluation_summary(context)
    rubric_guidance = _format_rubric_guidance(context)
    adaptive_rules = _adaptive_rules_blurb()
    candidate_profile = _format_candidate_profile(context)
    return dedent(
        f"""
        You are orchestrating a structured interview as the persona "{persona.name}".
        Probing style: {persona.probing_style}
        Hint style: {persona.hint_style}
        Encouragement style: {persona.encouragement}

        {candidate_profile}

        Interview stage: {context.stage}
        Stage objective:
        {stage_objective}

        Conversation state:
        - Previously asked questions:\n{asked}
        - Memory entities:\n{entities}
        - Rubric progress score: {context.rubric_progress:.2f}
        {evaluation_summary}

        Rubric and competency guidance:
        {rubric_guidance}

        Adaptive questioning rules:
        {adaptive_rules}

        Produce the next interviewer question as JSON with fields:
        - question: persona-aligned prompt for the candidate.
        - reasoning: why this question advances the rubric coverage now.
        - follow_up_prompt: probing line to use if the answer is strong.
        - escalation: choose one of [broad, why, how, challenge, hint, edge] to signal intensity.
        Maintain a natural conversational tone that matches the persona while following the rubric-driven plan.
        """
    ).strip()


def _format_candidate_profile(context: QuestionContext) -> str:
    experiences = "\n".join(f"  - {item}" for item in context.experiences) or "  - (none listed)"
    return dedent(
        f"""
        Candidate profile:
          Candidate: {context.candidate_name or '(name unavailable)'}
          Interview ID: {context.interview_id}
        Resume summary: {context.resume_summary}
        Highlighted experiences:\n{experiences}
        """
    ).strip()


def _stage_objective(context: QuestionContext) -> str:
    if context.stage == "warmup":
        return dedent(
            """
            Build rapport while surfacing concrete experiences that map to later competencies.
            Use the resume summary and highlighted experiences to find shared context and establish a comfortable tone.
            Keep questions open and conversational; no rubric scoring yet, but capture anchors for future reference.
            """
        ).strip()
    if context.stage == "wrapup":
        return dedent(
            """
            Offer a graceful close: reflect on strengths observed, invite final clarifications, and confirm next steps.
            Provide a soft landing that acknowledges effort while avoiding new deep-dives into rubric criteria.
            """
        ).strip()
    competency_name = context.competency or "competency"
    if context.question_index == 0:
        intro = (
            "Begin this competency by linking a resume experience to the rubric. "
            "Ask a broad, competency-aligned question that identifies a concrete project or decision the candidate handled."
        )
    else:
        intro = (
            "Continue the loop by targeting uncovered rubric criteria. Reference previous answers, avoid repetition, "
            "and deepen evidence until the rubric can be confidently scored."
        )
    return dedent(
        f"""
        Competency focus: {competency_name}.
        {intro}
        Dwell on this competency until all criteria are satisfied or a future custom metric signals closure.
        Use evaluator feedback and rubric anchors to tune intensity, looping with follow-ups when evidence is incomplete.
        """
    ).strip()


def _format_evaluation_summary(context: QuestionContext) -> str:
    evaluation = context.last_evaluation
    if evaluation is None:
        return "- Last evaluation: (none yet)"
    lines = [
        f"- Last evaluation total score: {evaluation.total_score:.2f} (rubric filled: {evaluation.rubric_filled})",
        f"  Follow-up requested: {'yes' if evaluation.follow_up_needed else 'no'}",
    ]
    for item in evaluation.criterion_scores:
        lines.append(f"  • {item.criterion}: {item.score:.1f} — {item.rationale}")
    if evaluation.hints:
        lines.append("  Hints from evaluator:")
        lines.extend(f"    - {hint}" for hint in evaluation.hints)
    return "\n".join(lines)


def _format_rubric_guidance(context: QuestionContext) -> str:
    rubric = context.rubric
    if rubric is None:
        return dedent(
            """
            Warmup or wrapup stage: focus on rapport, context setting, or closure. Rubric-driven probing is paused.
            """
        ).strip()
    status_lookup = {item.criterion: item for item in context.criterion_status}
    lines: List[str] = [
        f"Competency: {rubric.competency} — band {rubric.band} (min pass score {rubric.min_pass_score:.2f}).",
    ]
    if rubric.band_notes:
        lines.append("Band guidance:")
        lines.extend(f"  - {note}" for note in rubric.band_notes)
    if rubric.red_flags:
        lines.append("Red flags to watch:")
        lines.extend(f"  - {flag}" for flag in rubric.red_flags)
    if rubric.evidence:
        lines.append("Evidence expectations:")
        lines.extend(f"  - {item}" for item in rubric.evidence)
    lines.append("Criterion focus:")
    for criterion in rubric.criteria:
        status = status_lookup.get(
            criterion.name,
            CriterionProgress(criterion=criterion.name, weight=criterion.weight),
        )
        coverage = status.coverage_label()
        lines.append(
            f"  - {criterion.name} (weight {criterion.weight:.2f}) — status: {coverage}, last score {status.latest_score:.1f}.")
        rationale = status.rationale or "No evidence captured yet; plan a question to elicit concrete examples."
        lines.append(f"    Evidence so far: {rationale}")
        lines.append(f"    Anchor highlights: {_anchor_highlights(criterion.anchors)}")
    priority = sorted(
        (status_lookup.get(criterion.name, CriterionProgress(criterion=criterion.name, weight=criterion.weight)) for criterion in rubric.criteria),
        key=lambda item: (item.latest_score, -item.weight),
    )
    lines.append("Priority order for upcoming questions (lowest evidence first):")
    for item in priority:
        lines.append(
            f"  • {item.criterion}: coverage {item.coverage_label()}, weight {item.weight:.2f}, score {item.latest_score:.1f}"
        )
    lines.append("Full rubric JSON for reference:")
    lines.append(rubric.model_dump_json(indent=2))
    return "\n".join(lines)


def _anchor_highlights(anchors: Sequence[RubricAnchor]) -> str:
    if not anchors:
        return "No anchors provided."
    target_levels = {1: "low", 3: "mid", 5: "high"}
    highlights: List[str] = []
    for level, label in target_levels.items():
        anchor = next((item for item in anchors if item.level == level), None)
        if anchor is not None:
            highlights.append(f"{label.capitalize()} (level {level}): {anchor.text}")
    if not highlights:
        highlights = [f"Level {anchor.level}: {anchor.text}" for anchor in anchors]
    return " | ".join(highlights)


def _adaptive_rules_blurb() -> str:
    return dedent(
        """
        - Start with broad, resume-linked questions when entering a new competency.
        - If prior evaluation flagged weak evidence (score < 3 or follow-up needed), reframe, offer hints, and guide towards fundamentals.
        - When answers are solid (score around 3), ask clarifying why/how questions to confirm reasoning depth.
        - For high-scoring responses (≥4), push to edge cases, challenges, and lessons learned before closing the criterion.
        - Weave in evaluator hints and avoid repeating previously logged questions; softly close once anchor-level expectations are satisfied.
        - Maintain interrupt readiness by ensuring each question could serve as a checkpoint boundary with recap-worthy context.
        """
    ).strip()
logger = logging.getLogger("uvicorn.error")
