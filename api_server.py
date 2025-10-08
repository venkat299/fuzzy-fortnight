from __future__ import annotations  # FastAPI server exposing competency analysis

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from config import load_app_registry
from jd_analysis import CompetencyMatrix, JobProfile, analyze_with_config
from llm_gateway import LlmGatewayError

from candidate_management import CandidateRecord, CandidateStore
from interview_evaluation import EvaluationResult
from rubric_design import (
    InterviewRubricSnapshot,
    RubricStore,
    design_with_config as design_rubrics_with_config,
    load_rubrics,
)
from interview_session import (
    CandidateProfile,
    CandidateResponder,
    CheckpointMemory,
    GeneratedQuestion,
    InMemorySessionStore,
    InterviewEvent,
    InterviewFlowConfig,
    InterviewMemoryManager,
    InterviewPlan,
    InterviewSessionEngine,
    InterviewSessionManager,
    PersonaConfig,
    PendingQuestion,
    QuestionGeneratorTool,
    RubricEvaluatorTool,
    SessionExpiredError,
    SessionLifecycleConfig,
    SessionNotFoundError,
    StageLiteral,
)
from interview_session.interview_session import EventTypeLiteral, InterviewSessionState


logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent / "app_config.json"
DATA_PATH = Path(__file__).resolve().parent / "data" / "interviews.db"

app = FastAPI(title="JD Analysis API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"]
)

_SESSION_SCHEMAS: Dict[str, type[BaseModel]] = {
    "interview_session.generate_question": GeneratedQuestion,
    "interview_evaluation.evaluate_response": EvaluationResult,
}
_SESSION_REGISTRY = load_app_registry(CONFIG_PATH, _SESSION_SCHEMAS)
_QUESTION_ROUTE, _ = _SESSION_REGISTRY["interview_session.generate_question"]
_EVALUATION_ROUTE, _ = _SESSION_REGISTRY["interview_evaluation.evaluate_response"]
_SESSION_STORE = InMemorySessionStore()

class AnalyzeRequest(BaseModel):  # Request payload from UI
    jobTitle: str
    jobDescription: str
    experienceYears: str


class CompetencyMatrixResponse(CompetencyMatrix):  # Matrix enriched with interview id
    interview_id: str


class InterviewSummary(BaseModel):  # Interview summary returned to dashboard
    interview_id: str
    job_title: str
    job_description: str
    experience_years: str
    status: str
    created_at: str


class CandidateSummary(BaseModel):  # Candidate summary returned to dashboard
    candidate_id: str
    full_name: str
    resume: str
    interview_id: Optional[str]
    status: str
    created_at: str


class CreateCandidateRequest(BaseModel):  # Candidate creation payload
    full_name: str
    resume: str
    interview_id: Optional[str] = None
    status: str


class SessionPersonaSettings(BaseModel):  # Persona config override from UI
    name: Optional[str] = None
    probing_style: Optional[str] = None
    hint_style: Optional[str] = None
    encouragement: Optional[str] = None


class StartSessionRequest(BaseModel):  # Start interview session payload
    interview_id: str
    candidate_id: str
    persona: Optional[SessionPersonaSettings] = None


class SessionCriterionState(BaseModel):  # Criterion progress entry
    competency: str
    criterion: str
    weight: float
    latest_score: float
    rationale: str


class SessionCompetencyState(BaseModel):  # Competency scoring summary
    competency: str
    total_score: float
    rubric_filled: bool
    criteria: List[SessionCriterionState]


class SessionEvent(BaseModel):  # Serialized event for UI playback
    event_id: int
    created_at: str
    stage: StageLiteral
    competency: Optional[str]
    event_type: EventTypeLiteral
    payload: Dict[str, Any]


class QuestionMetadata(BaseModel):  # Question context for UI
    model_config = ConfigDict(populate_by_name=True)

    stage: StageLiteral
    competency: Optional[str]
    reasoning: str
    escalation: str
    follow_up_prompt: str = Field(alias="followUpPrompt")


class QuestionPayload(BaseModel):  # Outgoing interviewer prompt
    model_config = ConfigDict(populate_by_name=True)

    content: str
    metadata: QuestionMetadata


class EvaluationCriterionPayload(BaseModel):  # Per-criterion evaluation summary
    model_config = ConfigDict(populate_by_name=True)

    criterion: str
    score: float
    weight: float
    rationale: str


class EvaluationPayload(BaseModel):  # Aggregated evaluation feedback
    model_config = ConfigDict(populate_by_name=True)

    summary: str
    total_score: float = Field(alias="totalScore")
    rubric_filled: bool = Field(alias="rubricFilled")
    criterion_scores: List[EvaluationCriterionPayload] = Field(alias="criterionScores")
    hints: List[str]
    follow_up_needed: bool = Field(alias="followUpNeeded")


class StartSessionResponse(BaseModel):  # Interactive session start payload
    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(alias="sessionId")
    stage: StageLiteral
    persona: PersonaConfig
    profile: CandidateProfile
    question: Optional[QuestionPayload]
    events: List[SessionEvent]
    competencies: List[SessionCompetencyState]
    overall_score: float = Field(alias="overallScore")
    questions_asked: int = Field(alias="questionsAsked")
    elapsed_ms: int = Field(alias="elapsedMs")


class TurnRequest(BaseModel):  # Candidate response payload
    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(alias="sessionId")
    answer: str
    auto_send: Optional[bool] = Field(default=None, alias="autoSend")
    auto_generate: Optional[bool] = Field(default=None, alias="autoGenerate")


class TurnResponse(BaseModel):  # Interactive turn response
    model_config = ConfigDict(populate_by_name=True)

    stage: StageLiteral
    question: Optional[QuestionPayload]
    evaluation: Optional[EvaluationPayload]
    events: List[SessionEvent]
    competencies: List[SessionCompetencyState]
    overall_score: float = Field(alias="overallScore")
    questions_asked: int = Field(alias="questionsAsked")
    elapsed_ms: int = Field(alias="elapsedMs")
    completed: bool


class ResumeEchoResponder:  # Simple candidate responder for demo playback
    def __init__(self, profile: CandidateProfile) -> None:
        self._profile = profile
        self._index = 0

    def respond(
        self,
        question: GeneratedQuestion,
        *,
        competency: Optional[str],
        stage: StageLiteral,
    ) -> str:
        experience = ""
        if self._profile.highlighted_experiences:
            experience = self._profile.highlighted_experiences[self._index % len(self._profile.highlighted_experiences)]
            self._index += 1
        persona_intro = "During warmup" if stage == "warmup" else "Focusing on the competency"
        if stage == "wrapup":
            persona_intro = "Wrapping up"
        focus = competency or "this topic"
        lead = (
            f"{persona_intro}, I'll ground my answer in {experience}"
            if experience
            else f"{persona_intro}, I'll reference a recent project"
        )
        rationale = (
            "I outlined the problem, defined metrics, partnered with stakeholders, and iterated using data to validate outcomes."
        )
        closing = (
            "The result was a measurable impact and clear lessons learned that I apply to new challenges."
        )
        if stage == "wrapup":
            closing = "Thanks for the conversation—those lessons continue to guide my growth."
        return " ".join([lead, f"Regarding {focus},", rationale, closing]).strip()


DEFAULT_PERSONA = PersonaConfig(  # Default persona for sessions
    name="Friendly Expert",
    probing_style="Curious, evidence-seeking, supportive",
    hint_style="Offers targeted nudges that reference rubric anchors",
    encouragement="Warm, celebrates progress, invites reflection",
)


def _build_engine() -> InterviewSessionEngine:  # Factory for interactive engines
    memory = InterviewMemoryManager(entity_memory=None, checkpoints=CheckpointMemory())
    question_tool = QuestionGeneratorTool(_QUESTION_ROUTE)
    evaluator = RubricEvaluatorTool(_EVALUATION_ROUTE)
    return InterviewSessionEngine(
        question_tool=question_tool,
        evaluator=evaluator,
        memory=memory,
        config=InterviewFlowConfig(),
    )


_SESSION_MANAGER = InterviewSessionManager(
    engine_factory=_build_engine,
    store=_SESSION_STORE,
    lifecycle=SessionLifecycleConfig(),
)

def _resolve_persona(settings: Optional[SessionPersonaSettings]) -> PersonaConfig:  # Merge persona overrides
    if settings is None:
        return DEFAULT_PERSONA.model_copy()
    return PersonaConfig(
        name=settings.name or DEFAULT_PERSONA.name,
        probing_style=settings.probing_style or DEFAULT_PERSONA.probing_style,
        hint_style=settings.hint_style or DEFAULT_PERSONA.hint_style,
        encouragement=settings.encouragement or DEFAULT_PERSONA.encouragement,
    )


def _summarize_resume(resume: str) -> Tuple[str, List[str]]:  # Extract summary and experiences
    lines = [segment.strip(" •\t-·") for segment in resume.splitlines() if segment.strip()]
    summary_source = " ".join(lines[:2]) or resume.strip()
    summary = summary_source[:360] + ("…" if len(summary_source) > 360 else "")
    experiences = [line for line in lines if len(line.split()) > 3][:6]
    if not experiences and summary:
        experiences = [summary[:120]]
    return summary or "Candidate resume not provided.", experiences


def _build_candidate_profile(record: CandidateRecord) -> CandidateProfile:  # Convert record to profile
    summary, experiences = _summarize_resume(record.resume)
    return CandidateProfile(
        candidate_name=record.full_name,
        resume_summary=summary,
        experience_years=record.status,
        highlighted_experiences=experiences,
    )


def _serialize_events(events: List[InterviewEvent]) -> List[SessionEvent]:  # Convert events for API
    return [
        SessionEvent(
            event_id=event.event_id,
            created_at=event.created_at.isoformat(),
            stage=event.stage,
            competency=event.competency,
            event_type=event.event_type,
            payload=event.payload,
        )
        for event in events
    ]


def _serialize_competencies(state: InterviewSessionState) -> List[SessionCompetencyState]:  # Convert scoring
    states: List[SessionCompetencyState] = []
    ordered = list(state.competency_order)
    for name in ordered:
        runtime = state.competencies[name]
        criteria = [
            SessionCriterionState(
                competency=name,
                criterion=progress.criterion,
                weight=progress.weight,
                latest_score=progress.latest_score,
                rationale=progress.rationale,
            )
            for progress in runtime.criteria.values()
        ]
        states.append(
            SessionCompetencyState(
                competency=name,
                total_score=runtime.total_score,
                rubric_filled=runtime.rubric_filled,
                criteria=criteria,
            )
        )
    for name, runtime in state.competencies.items():
        if name in ordered:
            continue
        criteria = [
            SessionCriterionState(
                competency=name,
                criterion=progress.criterion,
                weight=progress.weight,
                latest_score=progress.latest_score,
                rationale=progress.rationale,
            )
            for progress in runtime.criteria.values()
        ]
        states.append(
            SessionCompetencyState(
                competency=name,
                total_score=runtime.total_score,
                rubric_filled=runtime.rubric_filled,
                criteria=criteria,
            )
        )
    return states


def _serialize_question(pending: Optional[PendingQuestion]) -> Optional[QuestionPayload]:  # Convert pending question
    if pending is None:
        return None
    question = pending.question
    return QuestionPayload(
        content=question.question,
        metadata=QuestionMetadata(
            stage=pending.stage,
            competency=pending.competency,
            reasoning=question.reasoning,
            escalation=question.escalation,
            follow_up_prompt=question.follow_up_prompt,
        ),
    )


def _serialize_evaluation(
    state: InterviewSessionState,
    evaluation: Optional[EvaluationResult],
) -> Optional[EvaluationPayload]:  # Convert evaluation result
    if evaluation is None:
        return None
    runtime = state.competencies.get(evaluation.competency)
    criteria: List[EvaluationCriterionPayload] = []
    if runtime is not None:
        for item in evaluation.criterion_scores:
            weight = runtime.criteria.get(item.criterion, None)
            criteria.append(
                EvaluationCriterionPayload(
                    criterion=item.criterion,
                    score=item.score,
                    weight=(weight.weight if weight else 0.0),
                    rationale=item.rationale,
                )
            )
    return EvaluationPayload(
        summary=evaluation.summary,
        total_score=evaluation.total_score,
        rubric_filled=evaluation.rubric_filled,
        criterion_scores=criteria,
        hints=evaluation.hints,
        follow_up_needed=evaluation.follow_up_needed,
    )


def _compute_overall_score(state: InterviewSessionState) -> float:  # Aggregate overall score
    if not state.competencies:
        return 0.0
    total = sum(runtime.total_score for runtime in state.competencies.values())
    return total / max(len(state.competencies), 1)


def _elapsed_ms(state: InterviewSessionState) -> int:  # Compute elapsed session time
    baseline = state.started_at
    latest = state.last_activity or baseline
    delta = latest - baseline
    return max(0, int(delta.total_seconds() * 1000))

@app.post("/api/competency-matrix", response_model=CompetencyMatrixResponse)
def create_competency_matrix(payload: AnalyzeRequest) -> CompetencyMatrixResponse:  # Generate competency matrix response
    profile = JobProfile(
        job_title=payload.jobTitle,
        job_description=payload.jobDescription,
        experience_years=payload.experienceYears
    )
    try:
        matrix = analyze_with_config(profile, config_path=CONFIG_PATH)
        interview_id = design_rubrics_with_config(
            matrix,
            config_path=CONFIG_PATH,
            db_path=DATA_PATH,
            job_description=payload.jobDescription,
        )
        print(interview_id)
        return CompetencyMatrixResponse(
            job_title=matrix.job_title,
            experience_years=matrix.experience_years,
            competency_areas=matrix.competency_areas,
            interview_id=interview_id,
        )
    except LlmGatewayError as exc:
        logger.exception("LLM request failed")
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error during competency analysis")
        raise HTTPException(status_code=500, detail=f"Unable to analyze job description: {exc}") from exc


@app.get("/api/interviews", response_model=List[InterviewSummary])
def list_interviews() -> List[InterviewSummary]:  # Retrieve stored interviews
    store = RubricStore(DATA_PATH)
    rows = store.list_interviews()
    return [
        InterviewSummary(
            interview_id=row["interview_id"],
            job_title=row["job_title"],
            job_description=row["job_description"],
            experience_years=row["experience_years"],
            status=row["status"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


@app.get("/api/candidates", response_model=List[CandidateSummary])
def list_candidates() -> List[CandidateSummary]:  # Retrieve stored candidates
    store = CandidateStore(DATA_PATH)
    records = store.list_candidates()
    return [
        CandidateSummary(
            candidate_id=record.candidate_id,
            full_name=record.full_name,
            resume=record.resume,
            interview_id=record.interview_id,
            status=record.status,
            created_at=record.created_at,
        )
        for record in records
    ]


@app.post("/api/candidates", response_model=CandidateRecord, status_code=201)
def create_candidate(payload: CreateCandidateRequest) -> CandidateRecord:  # Persist a new candidate
    store = CandidateStore(DATA_PATH)
    try:
        return store.create_candidate(
            full_name=payload.full_name,
            resume=payload.resume,
            interview_id=payload.interview_id,
            status=payload.status,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=400, detail="Invalid interview reference") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unable to create candidate")
        raise HTTPException(status_code=500, detail="Unable to create candidate") from exc


@app.post("/api/interview-sessions/start", response_model=StartSessionResponse)
def start_interview_session(payload: StartSessionRequest) -> StartSessionResponse:  # Initialize interactive session
    candidate_store = CandidateStore(DATA_PATH)
    try:
        candidate = candidate_store.get_candidate(payload.candidate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Candidate not found") from exc
    try:
        snapshot = load_rubrics(payload.interview_id, db_path=DATA_PATH)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Interview not found") from exc
    persona = _resolve_persona(payload.persona)
    profile = _build_candidate_profile(candidate)
    plan = InterviewPlan(
        interview_id=payload.interview_id,
        persona=persona,
        profile=profile,
        rubrics=snapshot.rubrics,
    )
    try:
        start = _SESSION_MANAGER.start_session(plan)
    except LlmGatewayError as exc:
        logger.exception("LLM request failed during interactive session start")
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unable to start interview session")
        raise HTTPException(status_code=500, detail="Unable to start interview session") from exc
    state = start.state
    return StartSessionResponse(
        session_id=start.session_id,
        stage=state.stage,
        persona=state.persona,
        profile=state.profile,
        question=_serialize_question(start.question),
        events=_serialize_events(start.events),
        competencies=_serialize_competencies(state),
        overall_score=_compute_overall_score(state),
        questions_asked=state.questions_asked,
        elapsed_ms=_elapsed_ms(state),
    )


@app.post("/api/interview-sessions/turn", response_model=TurnResponse)
def advance_interview_session(payload: TurnRequest) -> TurnResponse:  # Process candidate answer
    answer = payload.answer.strip()
    if not answer:
        raise HTTPException(status_code=400, detail="Answer cannot be empty")
    try:
        turn = _SESSION_MANAGER.submit_answer(payload.session_id, answer)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=401, detail="Session not found") from exc
    except SessionExpiredError as exc:
        raise HTTPException(status_code=410, detail="Session expired") from exc
    except LlmGatewayError as exc:
        logger.exception("LLM request failed during interactive turn")
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Interactive session turn failed")
        raise HTTPException(status_code=500, detail="Unable to process answer") from exc
    state = turn.state
    return TurnResponse(
        stage=state.stage,
        question=_serialize_question(turn.question),
        evaluation=_serialize_evaluation(state, turn.evaluation),
        events=_serialize_events(turn.events),
        competencies=_serialize_competencies(state),
        overall_score=_compute_overall_score(state),
        questions_asked=state.questions_asked,
        elapsed_ms=_elapsed_ms(state),
        completed=turn.completed,
    )


@app.get("/api/interviews/{interview_id}/rubric", response_model=InterviewRubricSnapshot)
def fetch_interview_rubric(interview_id: str) -> InterviewRubricSnapshot:  # Retrieve stored interview rubric
    try:
        return load_rubrics(interview_id, db_path=DATA_PATH)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Interview not found") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="Unable to load interview rubric") from exc
