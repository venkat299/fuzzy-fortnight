from __future__ import annotations  # FastAPI server exposing competency analysis

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from jd_analysis import CompetencyMatrix, JobProfile, analyze_with_config
from llm_gateway import LlmGatewayError

CONFIG_PATH = Path(__file__).resolve().parent / "app_config.json"

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


@app.post("/api/competency-matrix", response_model=CompetencyMatrix)
def create_competency_matrix(payload: AnalyzeRequest) -> CompetencyMatrix:  # Generate competency matrix response
    profile = JobProfile(
        job_title=payload.jobTitle,
        job_description=payload.jobDescription,
        experience_years=payload.experienceYears
    )
    try:
        return analyze_with_config(profile, config_path=CONFIG_PATH)
    except LlmGatewayError as exc:
        raise HTTPException(status_code=502, detail="LLM request failed") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="Unable to analyze job description") from exc
