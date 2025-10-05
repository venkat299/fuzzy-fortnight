from __future__ import annotations  # Job description competency analysis module

from pathlib import Path
from textwrap import dedent
from typing import List

from pydantic import BaseModel, Field

from config import LlmRoute, load_app_registry
from llm_gateway import call


class JobProfile(BaseModel):  # Input profile from UI
    job_title: str
    job_description: str
    experience_years: str


class CompetencyArea(BaseModel):  # Competency area with skills
    name: str
    skills: List[str] = Field(min_length=1)


class CompetencyMatrix(BaseModel):  # Output competency matrix for UI
    job_title: str
    experience_years: str
    competency_areas: List[CompetencyArea] = Field(min_length=5)


def generate_competency_matrix(profile: JobProfile, *, route: LlmRoute) -> CompetencyMatrix:  # Analyze JD via LLM
    task = _build_task(profile)
    result = call(task, CompetencyMatrix, cfg=route)
    return result


def analyze_with_config(profile: JobProfile, *, config_path: Path) -> CompetencyMatrix:  # Convenience helper using app config
    registry = load_app_registry(config_path, {"jd_analysis.generate_competency_matrix": CompetencyMatrix})
    route, _ = registry["jd_analysis.generate_competency_matrix"]
    return generate_competency_matrix(profile, route=route)


def _build_task(profile: JobProfile) -> str:  # Build task prompt for LLM
    return dedent(
        f"""
        Analyze the job description and identify competency areas for interviewer focus.
        Job title: {profile.job_title}
        Required years of experience: {profile.experience_years}
        Job description:
        {profile.job_description}

        Respond with a JSON object following this contract:
        - job_title: copy of the provided title.
        - experience_years: copy of the provided experience range.
        - competency_areas: array with at least five items.
            Each item must contain:
              - name: concise competency area name.
              - skills: list of three to six concrete skills, written as short phrases.
        Return only JSON without markdown fences, text, or commentary.
        """
    ).strip()
