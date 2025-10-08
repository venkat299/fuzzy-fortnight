from __future__ import annotations  # FastAPI server exposing competency analysis

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from jd_analysis import CompetencyMatrix, JobProfile, analyze_with_config
from llm_gateway import LlmGatewayError

from candidate_management import CandidateRecord, CandidateStore
from rubric_design import (
    InterviewRubricSnapshot,
    RubricStore,
    design_with_config as design_rubrics_with_config,
    load_rubrics,
)
from interview_session import (
    CandidateProfile,
    CandidateResponder,
    GeneratedQuestion,
    InterviewEvent,
    InterviewPlan,
    InterviewTranscript,
    PersonaConfig,
    StageLiteral,
    build_session_with_config,
)
from interview_session.interview_session import EventTypeLiteral


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


class SessionPersonaSettings(BaseModel):  # Persona config override from UI
    name: Optional[str] = None
    probing_style: Optional[str] = None
    hint_style: Optional[str] = None
    encouragement: Optional[str] = None


class StartSessionRequest(BaseModel):  # Start interview session payload
    interview_id: str
    candidate_id: str
    persona: Optional[SessionPersonaSettings] = None


class SessionTurn(BaseModel):  # Transcript turn returned to UI
    role: str
    stage: StageLiteral
    competency: Optional[str]
    content: str


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


class InterviewSessionResponse(BaseModel):  # Session run response for UI
    interview_id: str
    persona: PersonaConfig
    profile: CandidateProfile
    turns: List[SessionTurn]
    events: List[SessionEvent]
    competencies: List[SessionCompetencyState]


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


def _serialize_turns(transcript: InterviewTranscript) -> List[SessionTurn]:  # Convert turns for API
    return [
        SessionTurn(
            role=turn.role,
            stage=turn.stage,
            competency=turn.competency,
            content=turn.content,
        )
        for turn in transcript.turns
    ]


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


def _serialize_competencies(transcript: InterviewTranscript) -> List[SessionCompetencyState]:  # Convert scoring
    states: List[SessionCompetencyState] = []
    for name, runtime in transcript.competencies.items():
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


@app.post("/api/interview-sessions/run", response_model=InterviewSessionResponse)
def run_interview_session(payload: StartSessionRequest) -> InterviewSessionResponse:  # Execute interview flow
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
    responder: CandidateResponder = ResumeEchoResponder(profile)
    try:
        transcript = build_session_with_config(
            plan,
            responder,
            config_path=CONFIG_PATH,
        )
    except LlmGatewayError as exc:
        logger.exception("LLM request failed during interview session")
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unable to run interview session")
        raise HTTPException(status_code=500, detail="Unable to run interview session") from exc
    return InterviewSessionResponse(
        interview_id=transcript.interview_id,
        persona=transcript.persona,
        profile=transcript.profile,
        turns=_serialize_turns(transcript),
        events=_serialize_events(transcript.events),
        competencies=_serialize_competencies(transcript),
    )


@app.get("/api/interviews/{interview_id}/rubric", response_model=InterviewRubricSnapshot)
def fetch_interview_rubric(interview_id: str) -> InterviewRubricSnapshot:  # Retrieve stored interview rubric
    try:
        return load_rubrics(interview_id, db_path=DATA_PATH)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Interview not found") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="Unable to load interview rubric") from exc
