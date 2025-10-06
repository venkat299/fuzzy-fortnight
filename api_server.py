from __future__ import annotations  # FastAPI server exposing competency analysis

import logging
import sqlite3
from pathlib import Path
from typing import List, Optional

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
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="Unable to load interview rubric") from exc
