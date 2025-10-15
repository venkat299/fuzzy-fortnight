from __future__ import annotations  # Competency primer agent for project anchors

from pathlib import Path
from textwrap import dedent
from typing import Dict, Sequence, Type

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from config import LlmRoute, load_app_registry
from llm_gateway import runnable as llm_runnable
from .toolkit import bullet_list, clamp_text


COMPETENCY_PRIMER_AGENT_KEY = "flow_manager.competency_primer"  # Registry key for primer agent configuration


class CompetencyPrimerPlan(BaseModel):  # Primer agent JSON payload for competency projects
    projects: Dict[str, str] = Field(default_factory=dict)


class CompetencyPrimerAgent:  # Agent that maps competencies to project anchors
    def __init__(self, route: LlmRoute, schema: Type[CompetencyPrimerPlan]) -> None:
        self._route = route
        self._schema = schema
        self._prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    dedent(
                        """
                        You select anchor projects for each competency pillar before the interview starts.
                        Prefer resume experiences that align with the competency focus.
                        When no resume match exists, propose a hypothetical but realistic project or use case.
                        Return concise anchors for downstream agents.
                        """
                    ).strip(),
                ),
                (
                    "human",
                    (
                        "Job Title: {job_title}\n"
                        "Job Description:\n{job_description}\n\n"
                        "Resume Summary:\n{resume_summary}\n\n"
                        "Highlighted Experiences:\n{highlighted}\n\n"
                        "Competency Pillars:\n{competencies}\n\n"
                        "Respond with JSON mapping each competency to a single project anchor or hypothetical scenario."
                    ),
                ),
            ]
        )
        self._chain = self._prompt | llm_runnable(self._route, self._schema)

    def invoke(
        self,
        *,
        job_title: str,
        job_description: str,
        resume_summary: str,
        experiences: Sequence[str],
        competencies: Sequence[str],
    ) -> Dict[str, str]:  # Generate competency to project anchor mapping
        plan = self._chain.invoke(
            {
                "job_title": job_title,
                "job_description": clamp_text(job_description, limit=900),
                "resume_summary": clamp_text(resume_summary, limit=900),
                "highlighted": bullet_list(experiences),
                "competencies": bullet_list(competencies),
            }
        )
        return {key: value.strip() for key, value in plan.projects.items() if value and value.strip()}


def prime_competencies_with_config(
    *,
    job_title: str,
    job_description: str,
    resume_summary: str,
    experiences: Sequence[str],
    competencies: Sequence[str],
    config_path: Path,
) -> Dict[str, str]:  # Convenience helper loading registry from config file
    schemas = {COMPETENCY_PRIMER_AGENT_KEY: CompetencyPrimerPlan}
    registry = load_app_registry(config_path, schemas)
    route, schema = registry[COMPETENCY_PRIMER_AGENT_KEY]
    agent = CompetencyPrimerAgent(route, schema)
    return agent.invoke(
        job_title=job_title,
        job_description=job_description,
        resume_summary=resume_summary,
        experiences=experiences,
        competencies=competencies,
    )


__all__ = [
    "COMPETENCY_PRIMER_AGENT_KEY",
    "CompetencyPrimerAgent",
    "CompetencyPrimerPlan",
    "prime_competencies_with_config",
]
