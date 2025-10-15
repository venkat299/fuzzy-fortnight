from __future__ import annotations  # FastAPI server exposing competency analysis

import logging
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from jd_analysis import CompetencyMatrix, JobProfile, analyze_with_config
from llm_gateway import LlmGatewayError

from candidate_management import CandidateRecord, CandidateStore
from config import load_config
from flow_manager import (
    ChatTurn,
    InterviewContext as FlowContext,
    advance_session_with_config,
    start_session_with_config,
)
from flow_manager.agents import prime_competencies_with_config
from flow_manager.models import EvaluatorState
from candidate_agent import AutoReplyOutcome, QuestionAnswer, auto_reply_with_config
from rubric_design import (
    InterviewRubricSnapshot,
    RubricStore,
    design_with_config as design_rubrics_with_config,
    load_rubrics,
)
from session_reports import SessionReport, SessionReportStore, generate_session_report_pdf


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
    auto_answer_enabled: bool = True
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
    competency: Optional[str] = None
    competency_index: int = Field(default=0, ge=0)
    question_index: int = Field(default=0, ge=0)
    project_anchor: str = ""
    competency_projects: Dict[str, str] = Field(default_factory=dict)
    competency_criteria: Dict[str, List[str]] = Field(default_factory=dict)
    competency_covered: Dict[str, List[str]] = Field(default_factory=dict)
    competency_criterion_levels: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    competency_question_counts: Dict[str, int] = Field(default_factory=dict)
    competency_low_scores: Dict[str, int] = Field(default_factory=dict)
    targeted_criteria: List[str] = Field(default_factory=list)
    qa_history: List[QuestionAnswer] = Field(default_factory=list)
    evaluator: EvaluatorState = Field(default_factory=EvaluatorState)


class SessionMessage(BaseModel):  # Chat message returned to UI
    speaker: str
    content: str
    tone: str
    competency: Optional[str] = None
    targeted_criteria: List[str] = Field(default_factory=list)
    project_anchor: str = ""


class StartSessionResponse(BaseModel):  # Combined context payload and rubric
    context: SessionContext
    messages: List[SessionMessage]
    rubric: InterviewRubricSnapshot


class SessionAdvanceResponse(BaseModel):  # Warmup payload returned after start
    context: SessionContext
    messages: List[SessionMessage]


class CriterionScoreSummary(BaseModel):  # Criterion-level score snapshot for reports
    competency: str
    criterion: str
    level: int


class CompetencyScoreSummary(BaseModel):  # Competency score snapshot for reports
    competency: str
    score: float
    notes: List[str] = Field(default_factory=list)
    rubric_updates: List[str] = Field(default_factory=list)


class SessionReportExchangeResponse(BaseModel):  # Transcript entry returned in report
    sequence: int
    stage: str
    question: str
    answer: str
    competency: Optional[str] = None
    criteria: List[str] = Field(default_factory=list)
    system_message: str = ""
    anchors: List[str] = Field(default_factory=list)
    criterion_levels: Dict[str, int] = Field(default_factory=dict)


class SessionReportResponse(BaseModel):  # Report payload returned to clients
    interview_id: str
    candidate_id: str
    candidate_name: str
    job_title: str
    overall_score: Optional[float] = None
    competency_scores: List[CompetencyScoreSummary] = Field(default_factory=list)
    criterion_scores: List[CriterionScoreSummary] = Field(default_factory=list)
    exchanges: List[SessionReportExchangeResponse] = Field(default_factory=list)
    rubric: InterviewRubricSnapshot


class AutoReplyRequest(BaseModel):  # Candidate auto-reply generation payload
    candidate_id: str
    question: str
    candidate_level: int = Field(default=3, ge=1, le=5)
    qa_history: List[QuestionAnswer] = Field(default_factory=list)
    competency: Optional[str] = None
    project_anchor: str = ""
    targeted_criteria: List[str] = Field(default_factory=list)


class CandidateReplyRequest(BaseModel):  # Candidate reply submission payload
    candidate_id: str
    question: str
    answer: str
    tone: str = "neutral"
    stage: str = "warmup"
    auto_answer_enabled: bool = True
    candidate_level: int = Field(default=3, ge=1, le=5)
    qa_history: List[QuestionAnswer] = Field(default_factory=list)
    evaluator: EvaluatorState = Field(default_factory=EvaluatorState)
    competency: Optional[str] = None
    competency_index: int = Field(default=0, ge=0)
    question_index: int = Field(default=0, ge=0)
    project_anchor: str = ""
    competency_projects: Dict[str, str] = Field(default_factory=dict)
    competency_criteria: Dict[str, List[str]] = Field(default_factory=dict)
    competency_covered: Dict[str, List[str]] = Field(default_factory=dict)
    competency_criterion_levels: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    competency_question_counts: Dict[str, int] = Field(default_factory=dict)
    competency_low_scores: Dict[str, int] = Field(default_factory=dict)
    targeted_criteria: List[str] = Field(default_factory=list)


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
    projects = _prime_competency_projects(snapshot, resume_summary, highlighted)
    flow_context = _build_flow_context(
        interview_id,
        snapshot,
        candidate.full_name,
        resume_summary,
        highlighted,
        projects,
    )
    response_context = _session_context_from_flow(
        flow_context,
        auto_answer_enabled=payload.auto_answer_enabled,
        candidate_level=payload.candidate_level,
        qa_history=payload.qa_history,
    )
    report_store = _session_report_store()
    report_store.initialize_session(
        interview_id,
        payload.candidate_id,
        candidate_name=candidate.full_name,
        job_title=snapshot.job_title,
        rubric=snapshot,
        reset=True,
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
    projects = _prime_competency_projects(snapshot, resume_summary, highlighted)
    context = _build_flow_context(
        interview_id,
        snapshot,
        candidate.full_name,
        resume_summary,
        highlighted,
        projects,
    )
    try:
        launch = start_session_with_config(context, config_path=CONFIG_PATH)
    except LlmGatewayError as exc:
        logger.exception("Warmup agent failed")
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unable to start warmup stage")
        raise HTTPException(status_code=500, detail="Unable to start warmup stage") from exc

    response_messages = _convert_chat_turns(
        launch.messages,
        launch.context,
        stage_hint="warmup",
    )
    updated_history: List[QuestionAnswer] = list(payload.qa_history)
    response_context = _session_context_from_flow(
        launch.context,
        auto_answer_enabled=payload.auto_answer_enabled,
        candidate_level=payload.candidate_level,
        qa_history=updated_history,
    )
    return SessionAdvanceResponse(
        context=response_context,
        messages=response_messages,
    )


@app.post("/api/interviews/{interview_id}/session/auto-reply", response_model=AutoReplyOutcome)
def generate_candidate_auto_reply(
    interview_id: str,
    payload: AutoReplyRequest,
) -> AutoReplyOutcome:  # Generate draft candidate reply for the latest interviewer question
    _, _, resume_summary, _ = _load_session_resources(interview_id, payload.candidate_id)
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question text is required.")
    try:
        return auto_reply_with_config(
            question,
            resume_summary=resume_summary,
            history=payload.qa_history,
            level=payload.candidate_level,
            competency=payload.competency,
            project_anchor=payload.project_anchor,
            targeted_criteria=payload.targeted_criteria,
            config_path=CONFIG_PATH,
        )
    except LlmGatewayError as exc:
        logger.exception("Candidate auto-reply generation failed")
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error during candidate auto-reply generation")
        raise HTTPException(status_code=500, detail="Unable to generate candidate reply") from exc


@app.post("/api/interviews/{interview_id}/session/reply", response_model=SessionAdvanceResponse)
def submit_candidate_reply(
    interview_id: str,
    payload: CandidateReplyRequest,
) -> SessionAdvanceResponse:  # Persist candidate reply and advance the flow
    snapshot, candidate, resume_summary, highlighted = _load_session_resources(
        interview_id, payload.candidate_id
    )
    question = payload.question.strip()
    answer = payload.answer.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question text is required.")
    if not answer:
        raise HTTPException(status_code=400, detail="Candidate answer is required.")
    stage_value = payload.stage.strip() if isinstance(payload.stage, str) else ""
    stage = stage_value or ("competency" if payload.competency else "warmup")
    updated_history: List[QuestionAnswer] = list(payload.qa_history) + [
        QuestionAnswer(
            question=question,
            answer=answer,
            competency=payload.competency,
            criteria=list(payload.targeted_criteria),
            stage=stage,
        )
    ]
    candidate_message = SessionMessage(
        speaker="Candidate",
        content=answer,
        tone=_normalize_tone(payload.tone),
        competency=payload.competency,
        targeted_criteria=list(payload.targeted_criteria),
        project_anchor=payload.project_anchor,
    )
    report_store = _session_report_store()
    report_store.initialize_session(
        interview_id,
        payload.candidate_id,
        candidate_name=candidate.full_name,
        job_title=snapshot.job_title,
        rubric=snapshot,
        reset=False,
    )
    flow_context = _flow_context_from_payload(
        interview_id,
        snapshot,
        candidate.full_name,
        resume_summary,
        highlighted,
        payload,
    )
    history_turns = _qa_to_chat_turns(updated_history)
    try:
        flow_launch = advance_session_with_config(
            flow_context,
            history_turns,
            config_path=CONFIG_PATH,
        )
    except LlmGatewayError as exc:
        logger.exception("Flow agent failed after candidate reply")
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error while advancing session")
        raise HTTPException(status_code=500, detail="Unable to advance session") from exc
    follow_up_messages = _convert_chat_turns(
        flow_launch.messages,
        flow_launch.context,
        stage_hint=flow_launch.context.stage,
    )
    system_message = _build_system_message(
        flow_launch.context,
        stage,
        competency=payload.competency,
        targeted=payload.targeted_criteria,
    )
    try:
        report_store.record_exchange(
            interview_id,
            payload.candidate_id,
            stage=stage,
            question=question,
            answer=answer,
            competency=payload.competency,
            criteria=list(payload.targeted_criteria),
            system_message=system_message,
            evaluator=flow_launch.context.evaluator,
        )
    except KeyError:
        logger.warning(
            "Session report store not initialized for interview %s candidate %s",
            interview_id,
            payload.candidate_id,
        )
    response_context = _session_context_from_flow(
        flow_launch.context,
        auto_answer_enabled=payload.auto_answer_enabled,
        candidate_level=payload.candidate_level,
        qa_history=updated_history,
    )
    return SessionAdvanceResponse(
        context=response_context,
        messages=[candidate_message, *follow_up_messages],
    )


@app.get(
    "/api/interviews/{interview_id}/sessions/{candidate_id}/report",
    response_model=SessionReportResponse,
)
def fetch_session_report(interview_id: str, candidate_id: str) -> SessionReportResponse:
    store = _session_report_store()
    try:
        report = store.load_report(interview_id, candidate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session report not found") from exc
    return _format_session_report(report)


@app.get("/api/interviews/{interview_id}/sessions/{candidate_id}/report.pdf")
def fetch_session_report_pdf(interview_id: str, candidate_id: str) -> Response:
    store = _session_report_store()
    try:
        report = store.load_report(interview_id, candidate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session report not found") from exc
    llms = _session_llm_routes()
    payload = generate_session_report_pdf(report, llms)
    safe_candidate = _safe_slug(report.candidate_name)
    safe_role = _safe_slug(report.job_title)
    filename = f"{report.interview_id}-{safe_candidate or report.candidate_id}-{safe_role or 'report'}.pdf"
    headers = {"Content-Disposition": f"attachment; filename=\"{filename}\""}
    return Response(content=payload, media_type="application/pdf", headers=headers)


def _session_report_store() -> SessionReportStore:  # Construct session report store
    return SessionReportStore(DATA_PATH)


def _session_llm_routes() -> List[Tuple[str, str, str]]:  # Collect LLM routes used across modules
    try:
        cfg = load_config(CONFIG_PATH)
    except FileNotFoundError:
        return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load LLM config: %s", exc)
        return []
    details: List[Tuple[str, str, str]] = []
    seen: set[str] = set()
    for module in sorted(cfg.registry.keys()):
        route_id = cfg.registry[module]
        if route_id in seen:
            continue
        route = cfg.llm_routes.get(route_id)
        if not route:
            continue
        seen.add(route_id)
        details.append((module, route.name, route.model))
    return details


def _safe_slug(value: str) -> str:  # Sanitize value for filenames
    if not value:
        return ""
    lowered = value.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def _prime_competency_projects(
    snapshot: InterviewRubricSnapshot,
    resume_summary: str,
    highlighted: List[str],
) -> Dict[str, str]:  # Prepare competency-to-project anchors
    competencies = [rubric.competency for rubric in snapshot.rubrics]
    if not competencies:
        return {}
    try:
        return prime_competencies_with_config(
            job_title=snapshot.job_title,
            job_description=snapshot.job_description,
            resume_summary=resume_summary,
            experiences=highlighted,
            competencies=competencies,
            config_path=CONFIG_PATH,
        )
    except LlmGatewayError as exc:
        logger.warning("Unable to prime competency projects, using defaults: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error while priming competency projects")
    return {competency: "" for competency in competencies}


def _build_flow_context(
    interview_id: str,
    snapshot: InterviewRubricSnapshot,
    candidate_name: str,
    resume_summary: str,
    highlighted: List[str],
    projects: Dict[str, str],
) -> FlowContext:  # Construct initial flow context with competency metadata
    competencies = [rubric.competency for rubric in snapshot.rubrics]
    criteria_map = {
        rubric.competency: [criterion.name for criterion in rubric.criteria]
        for rubric in snapshot.rubrics
    }
    normalized_projects = {name: projects.get(name, "") for name in competencies}
    coverage = {name: [] for name in competencies}
    counts = {name: 0 for name in competencies}
    low_scores = {name: 0 for name in competencies}
    levels = {name: {} for name in competencies}
    current = competencies[0] if competencies else None
    anchor = normalized_projects.get(current, "") if current else ""
    return FlowContext(
        interview_id=interview_id,
        stage="warmup",
        candidate_name=candidate_name,
        job_title=snapshot.job_title,
        job_description=snapshot.job_description,
        resume_summary=resume_summary,
        highlighted_experiences=highlighted,
        competency_pillars=competencies,
        competency=current,
        competency_index=0,
        question_index=0,
        project_anchor=anchor,
        competency_projects=normalized_projects,
        competency_criteria=criteria_map,
        competency_covered=coverage,
        competency_criterion_levels=levels,
        competency_question_counts=counts,
        competency_low_scores=low_scores,
        targeted_criteria=[],
        evaluator=EvaluatorState(),
    )


def _session_context_from_flow(
    context: FlowContext,
    *,
    auto_answer_enabled: bool,
    candidate_level: int,
    qa_history: List[QuestionAnswer],
) -> SessionContext:  # Convert flow context to API session context
    def _normalize_level_map(source: Dict[str, int]) -> Dict[str, int]:
        result: Dict[str, int] = {}
        for name, raw in source.items():
            key = str(name).strip()
            if not key:
                continue
            try:
                result[key] = int(raw)
            except (TypeError, ValueError):
                result[key] = 0
        return result

    return SessionContext(
        stage=context.stage,
        interview_id=context.interview_id,
        candidate_name=context.candidate_name,
        job_title=context.job_title,
        resume_summary=context.resume_summary,
        auto_answer_enabled=auto_answer_enabled,
        candidate_level=candidate_level,
        competency=context.competency,
        competency_index=context.competency_index,
        question_index=context.question_index,
        project_anchor=context.project_anchor,
        competency_projects=dict(context.competency_projects),
        competency_criteria={key: list(value) for key, value in context.competency_criteria.items()},
        competency_covered={key: list(value) for key, value in context.competency_covered.items()},
        competency_criterion_levels={
            key: _normalize_level_map(value) for key, value in context.competency_criterion_levels.items()
        },
        competency_question_counts=dict(context.competency_question_counts),
        competency_low_scores=dict(context.competency_low_scores),
        targeted_criteria=list(context.targeted_criteria),
        qa_history=list(qa_history),
        evaluator=context.evaluator,
    )


def _flow_context_from_payload(
    interview_id: str,
    snapshot: InterviewRubricSnapshot,
    candidate_name: str,
    resume_summary: str,
    highlighted: List[str],
    payload: CandidateReplyRequest,
) -> FlowContext:  # Rebuild flow context from client payload
    competencies = [rubric.competency for rubric in snapshot.rubrics]
    criteria_map = {
        rubric.competency: [criterion.name for criterion in rubric.criteria]
        for rubric in snapshot.rubrics
    }
    projects = {name: "" for name in competencies}
    projects.update(payload.competency_projects)
    coverage = {name: list(payload.competency_covered.get(name, [])) for name in competencies}
    counts = {name: payload.competency_question_counts.get(name, 0) for name in competencies}
    low_scores = {name: payload.competency_low_scores.get(name, 0) for name in competencies}
    levels: Dict[str, Dict[str, int]] = {}
    for name in competencies:
        source = payload.competency_criterion_levels.get(name, {}) or {}
        mapped: Dict[str, int] = {}
        for inner_name, raw_value in source.items():
            key = str(inner_name).strip()
            if not key:
                continue
            try:
                mapped[key] = int(raw_value)
            except (TypeError, ValueError):
                mapped[key] = 0
        levels[name] = mapped
    index = min(payload.competency_index, max(len(competencies) - 1, 0)) if competencies else 0
    current = payload.competency or (competencies[index] if competencies else None)
    if current is not None:
        projects[current] = payload.project_anchor or projects.get(current, "")
        coverage.setdefault(current, list(payload.competency_covered.get(current, [])))
        counts.setdefault(current, payload.question_index)
        low_scores.setdefault(current, payload.competency_low_scores.get(current, 0))
        if current not in levels:
            source = payload.competency_criterion_levels.get(current, {}) or {}
            mapped: Dict[str, int] = {}
            for key, raw_value in source.items():
                name_key = str(key).strip()
                if not name_key:
                    continue
                try:
                    mapped[name_key] = int(raw_value)
                except (TypeError, ValueError):
                    mapped[name_key] = 0
            levels[current] = mapped
    anchor = payload.project_anchor or (projects.get(current, "") if current else "")
    return FlowContext(
        interview_id=interview_id,
        stage=payload.stage,
        candidate_name=candidate_name,
        job_title=snapshot.job_title,
        job_description=snapshot.job_description,
        resume_summary=resume_summary,
        highlighted_experiences=highlighted,
        competency_pillars=competencies,
        competency=current,
        competency_index=index,
        question_index=payload.question_index,
        project_anchor=anchor,
        competency_projects=projects,
        competency_criteria=criteria_map,
        competency_covered=coverage,
        competency_criterion_levels=levels,
        competency_question_counts=counts,
        competency_low_scores=low_scores,
        targeted_criteria=list(payload.targeted_criteria),
        evaluator=payload.evaluator,
    )


def _collect_highlights(snapshot: InterviewRubricSnapshot, limit: int = 6) -> List[str]:  # Pull notable evidence lines
    highlights: List[str] = []
    for rubric in snapshot.rubrics:
        highlights.extend(_trim_evidence(rubric.evidence, limit - len(highlights)))
        if len(highlights) >= limit:
            break
    return highlights


def _qa_to_chat_turns(history: List[QuestionAnswer]) -> List[ChatTurn]:  # Convert QA history into flow chat turns
    turns: List[ChatTurn] = []
    for entry in history:
        question = entry.question.strip()
        answer = entry.answer.strip()
        competency = entry.competency
        criteria = list(entry.criteria)
        if question:
            turns.append(
                ChatTurn(
                    speaker="Interviewer",
                    content=question,
                    tone="neutral",
                    competency=competency,
                    targeted_criteria=criteria,
                )
            )
        if answer:
            turns.append(
                ChatTurn(
                    speaker="Candidate",
                    content=answer,
                    tone="neutral",
                    competency=competency,
                    targeted_criteria=criteria,
                )
            )
    return turns


def _build_system_message(
    context: FlowContext,
    stage: str,
    *,
    competency: Optional[str],
    targeted: Sequence[str],
) -> str:  # Build system message summarizing anchors and criteria
    stage_key = stage or "warmup"
    anchors = [item.strip() for item in context.evaluator.anchors.get(stage_key, []) if item.strip()]
    criteria = [" ".join(str(item).split()) for item in targeted if str(item).strip()]
    levels: Dict[str, int] = {}
    if competency:
        raw_levels = context.competency_criterion_levels.get(competency, {})
        levels = {
            str(name): int(value)
            for name, value in raw_levels.items()
            if str(name).strip()
        }
    lines: List[str] = []
    if anchors:
        lines.append("Anchor points:")
        lines.extend(f"- {anchor}" for anchor in anchors)
    if criteria:
        lines.append("Targeted criteria:")
        lines.extend(f"- {criterion}" for criterion in criteria)
    if levels:
        lines.append("Criterion levels:")
        for name, level in sorted(levels.items()):
            lines.append(f"- {name}: Level {level}")
    return "\n".join(lines)


def _convert_chat_turns(
    messages: Sequence[ChatTurn],
    context: FlowContext,
    *,
    stage_hint: str | None = None,
) -> List[SessionMessage]:  # Convert flow turns into API messages with system notes
    results: List[SessionMessage] = []
    for turn in messages:
        message = SessionMessage(
            speaker=turn.speaker,
            content=turn.content,
            tone=_normalize_tone(turn.tone),
            competency=turn.competency,
            targeted_criteria=list(turn.targeted_criteria),
            project_anchor=turn.project_anchor,
        )
        results.append(message)
        speaker = (turn.speaker or "").strip().lower()
        if speaker.startswith("interviewer"):
            stage_value = stage_hint or context.stage
            stage = stage_value or "warmup"
            if turn.competency:
                stage = "competency"
            system_text = _build_system_message(
                context,
                stage,
                competency=turn.competency,
                targeted=turn.targeted_criteria,
            )
            if system_text:
                results.append(
                    SessionMessage(
                        speaker="System",
                        content=system_text,
                        tone="neutral",
                        competency=turn.competency,
                        targeted_criteria=[],
                        project_anchor="",
                    )
                )
    return results


def _format_session_report(report: SessionReport) -> SessionReportResponse:  # Map stored report to response payload
    exchanges: List[SessionReportExchangeResponse] = []
    latest: EvaluatorState | None = None
    for exchange in report.exchanges:
        evaluator = exchange.evaluator
        latest = evaluator
        stage = exchange.stage or "warmup"
        anchors = [item.strip() for item in evaluator.anchors.get(stage, []) if item.strip()]
        criterion_levels: Dict[str, int] = {}
        if exchange.competency:
            score_entry = evaluator.scores.get(exchange.competency)
            if score_entry:
                criterion_levels = {
                    str(name): int(value)
                    for name, value in score_entry.criterion_levels.items()
                    if str(name).strip()
                }
        exchanges.append(
            SessionReportExchangeResponse(
                sequence=exchange.sequence,
                stage=stage,
                question=exchange.question,
                answer=exchange.answer,
                competency=exchange.competency,
                criteria=list(exchange.criteria),
                system_message=exchange.system_message,
                anchors=anchors,
                criterion_levels=criterion_levels,
            )
        )
    competency_scores: List[CompetencyScoreSummary] = []
    criterion_scores: List[CriterionScoreSummary] = []
    overall: List[float] = []
    if latest:
        for name, score in latest.scores.items():
            competency_scores.append(
                CompetencyScoreSummary(
                    competency=name,
                    score=score.score,
                    notes=list(score.notes),
                    rubric_updates=list(score.rubric_updates),
                )
            )
            for criterion, level in score.criterion_levels.items():
                try:
                    numeric = int(level)
                except (TypeError, ValueError):
                    numeric = 0
                criterion_scores.append(
                    CriterionScoreSummary(
                        competency=name,
                        criterion=criterion,
                        level=numeric,
                    )
                )
            if score.score > 0:
                overall.append(score.score)
    overall_score = None
    if overall:
        overall_score = sum(overall) / len(overall)
    return SessionReportResponse(
        interview_id=report.interview_id,
        candidate_id=report.candidate_id,
        candidate_name=report.candidate_name,
        job_title=report.job_title,
        overall_score=overall_score,
        competency_scores=competency_scores,
        criterion_scores=criterion_scores,
        exchanges=exchanges,
        rubric=report.rubric,
    )


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


def _normalize_tone(value: str) -> str:  # Clamp tone metadata for chat messages
    normalized = (value or "").strip().lower()
    return "positive" if normalized == "positive" else "neutral"
