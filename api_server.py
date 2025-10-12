from __future__ import annotations  # FastAPI server exposing competency analysis

import logging
import sqlite3
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from jd_analysis import CompetencyMatrix, JobProfile, analyze_with_config
from llm_gateway import LlmGatewayError

from candidate_management import CandidateRecord, CandidateStore
from flow_manager import InterviewContext as FlowContext, start_session_with_config
from candidate_agent import QuestionAnswer, auto_reply_with_config
from rubric_design import (
    InterviewRubricSnapshot,
    RubricStore,
    design_with_config as design_rubrics_with_config,
    load_rubrics,
)


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


class StartSessionRequest(BaseModel):  # Start interview session payload
    candidate_id: str
    auto_answer_enabled: bool = False
    candidate_level: int = Field(default=3, ge=1, le=5)
    qa_history: List[QuestionAnswer] = Field(default_factory=list)


class SessionContext(BaseModel):  # Session context returned to UI
    stage: str
    interview_id: str
    candidate_name: str
    job_title: str
    resume_summary: str
    auto_answer_enabled: bool
    candidate_level: int
    qa_history: List[QuestionAnswer] = Field(default_factory=list)


class SessionMessage(BaseModel):  # Chat message returned to UI
    speaker: str
    content: str
    tone: str


class StartSessionResponse(BaseModel):  # Combined context payload and rubric
    context: SessionContext
    messages: List[SessionMessage]
    rubric: InterviewRubricSnapshot


class SessionAdvanceResponse(BaseModel):  # Warmup payload returned after start
    context: SessionContext
    messages: List[SessionMessage]


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


@app.get("/api/interviews/{interview_id}/rubric", response_model=InterviewRubricSnapshot)
def fetch_interview_rubric(interview_id: str) -> InterviewRubricSnapshot:  # Retrieve stored interview rubric
    try:
        return load_rubrics(interview_id, db_path=DATA_PATH)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Interview not found") from exc


@app.post("/api/interviews/{interview_id}/session", response_model=StartSessionResponse)
def start_interview_session(
    interview_id: str,
    payload: StartSessionRequest,
) -> StartSessionResponse:  # Launch interview session warmup
    snapshot, candidate, resume_summary, highlighted = _load_session_resources(
        interview_id, payload.candidate_id
    )
    context = FlowContext(
        interview_id=interview_id,
        stage="warmup",
        candidate_name=candidate.full_name,
        job_title=snapshot.job_title,
        resume_summary=resume_summary,
        highlighted_experiences=highlighted,
    )
    response_context = SessionContext(
        stage=context.stage,
        interview_id=context.interview_id,
        candidate_name=context.candidate_name,
        job_title=context.job_title,
        resume_summary=context.resume_summary,
        auto_answer_enabled=payload.auto_answer_enabled,
        candidate_level=payload.candidate_level,
        qa_history=list(payload.qa_history),
    )
    return StartSessionResponse(
        context=response_context,
        messages=[],
        rubric=snapshot,
    )


@app.post("/api/interviews/{interview_id}/session/start", response_model=SessionAdvanceResponse)
def begin_interview_warmup(
    interview_id: str,
    payload: StartSessionRequest,
) -> SessionAdvanceResponse:  # Trigger warmup agent when interviewer presses start
    snapshot, candidate, resume_summary, highlighted = _load_session_resources(
        interview_id, payload.candidate_id
    )
    context = FlowContext(
        interview_id=interview_id,
        stage="warmup",
        candidate_name=candidate.full_name,
        job_title=snapshot.job_title,
        resume_summary=resume_summary,
        highlighted_experiences=highlighted,
    )
    try:
        launch = start_session_with_config(context, config_path=CONFIG_PATH)
    except LlmGatewayError as exc:
        logger.exception("Warmup agent failed")
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unable to start warmup stage")
        raise HTTPException(status_code=500, detail="Unable to start warmup stage") from exc

    response_messages = [
        SessionMessage(
            speaker=message.speaker,
            content=message.content,
            tone=message.tone,
        )
        for message in launch.messages
    ]
    updated_history: List[QuestionAnswer] = list(payload.qa_history)
    if payload.auto_answer_enabled:
        interviewer_turn = next(
            (
                turn
                for turn in reversed(launch.messages)
                if turn.speaker.lower() == "interviewer" and turn.content.strip()
            ),
            None,
        )
        if interviewer_turn is not None:
            try:
                outcome = auto_reply_with_config(
                    interviewer_turn.content,
                    resume_summary=resume_summary,
                    history=updated_history,
                    level=payload.candidate_level,
                    config_path=CONFIG_PATH,
                )
            except LlmGatewayError as exc:
                logger.exception("Candidate auto-answer failed")
                raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc
            except Exception as exc:  # noqa: BLE001
                logger.exception("Unexpected error during candidate auto-answer")
                raise HTTPException(status_code=500, detail="Unable to generate candidate reply") from exc
            updated_history = outcome.history
            response_messages.append(
                SessionMessage(
                    speaker="Candidate",
                    content=outcome.message.answer,
                    tone=outcome.tone,
                )
            )
    response_context = SessionContext(
        stage=launch.context.stage,
        interview_id=launch.context.interview_id,
        candidate_name=launch.context.candidate_name,
        job_title=launch.context.job_title,
        resume_summary=launch.context.resume_summary,
        auto_answer_enabled=payload.auto_answer_enabled,
        candidate_level=payload.candidate_level,
        qa_history=updated_history,
    )
    return SessionAdvanceResponse(
        context=response_context,
        messages=response_messages,
    )


def _collect_highlights(snapshot: InterviewRubricSnapshot, limit: int = 6) -> List[str]:  # Pull notable evidence lines
    highlights: List[str] = []
    for rubric in snapshot.rubrics:
        highlights.extend(_trim_evidence(rubric.evidence, limit - len(highlights)))
        if len(highlights) >= limit:
            break
    return highlights


def _load_session_resources(
    interview_id: str,
    candidate_id: str,
) -> tuple[InterviewRubricSnapshot, CandidateRecord, str, List[str]]:  # Load rubric, candidate, and prompts
    rubric_store = RubricStore(DATA_PATH)
    try:
        snapshot = rubric_store.load(interview_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Interview not found") from exc
    candidate_store = CandidateStore(DATA_PATH)
    try:
        candidate = candidate_store.get(candidate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Candidate not found") from exc
    highlighted = _collect_highlights(snapshot)
    resume_summary = _summarize_resume(candidate.resume)
    return snapshot, candidate, resume_summary, highlighted


def _trim_evidence(evidence: List[str], remaining: int) -> List[str]:  # Trim evidence list respecting remaining slots
    entries: List[str] = []
    for item in evidence:
        if remaining <= 0:
            break
        text = item.strip()
        if text:
            entries.append(text)
            remaining -= 1
    return entries


def _summarize_resume(resume: str, limit: int = 600) -> str:  # Compact resume text for flow context
    compact = " ".join(resume.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"
