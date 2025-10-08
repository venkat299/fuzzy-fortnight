from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import List

from pydantic import BaseModel, Field

from config import LlmRoute, load_app_registry
from llm_gateway import call
from rubric_design import Rubric


class CriterionScore(BaseModel):  # Scored rubric criterion entry
    criterion: str
    score: float = Field(ge=0.0, le=5.0)
    rationale: str


class EvaluationResult(BaseModel):  # Aggregated evaluation for a response
    competency: str
    rubric_filled: bool
    total_score: float = Field(ge=0.0)
    criterion_scores: List[CriterionScore]
    hints: List[str] = Field(default_factory=list)
    follow_up_needed: bool = False
    summary: str


class CandidateAnswer(BaseModel):  # Candidate response with rubric context
    interview_id: str
    competency: str
    question: str
    answer: str
    rubric: Rubric
    persona: str
    stage: str
    asked_follow_ups: List[str] = Field(default_factory=list)


def evaluate_response(payload: CandidateAnswer, *, route: LlmRoute) -> EvaluationResult:  # Call LLM evaluator
    task = _build_task(payload)
    return call(task, EvaluationResult, cfg=route)


def evaluate_with_config(payload: CandidateAnswer, *, config_path: Path) -> EvaluationResult:  # Convenience helper
    registry = load_app_registry(
        config_path,
        {"interview_evaluation.evaluate_response": EvaluationResult},
    )
    route, _ = registry["interview_evaluation.evaluate_response"]
    return evaluate_response(payload, route=route)


def _build_task(payload: CandidateAnswer) -> str:  # Compose evaluation prompt
    rubric_json = payload.rubric.model_dump_json(indent=2)
    follow_ups = "\n".join(f"- {item}" for item in payload.asked_follow_ups) or "(none yet)"
    return dedent(
        f"""
        You are the rubric evaluator for a structured interview. Persona tone: {payload.persona}.

        Interview stage: {payload.stage}
        Competency under review: {payload.competency}
        Question asked: {payload.question}
        Candidate answer:
        {payload.answer}

        Follow-ups already used:
        {follow_ups}

        Rubric definition (JSON):
        {rubric_json}

        Evaluate the answer using the rubric. Return a JSON object that matches this contract:
        - competency: copy the competency name.
        - rubric_filled: true when the rubric has enough evidence to finalize scores.
        - total_score: aggregate numeric score using rubric weights.
        - criterion_scores: array mirroring rubric criteria order with fields criterion, score (0-5), rationale.
        - hints: optional coaching prompts to steer the next question when performance is weak.
        - follow_up_needed: true if another probing question is recommended.
        - summary: concise evaluation summary for interviewer memory.
        Scoring guidance:
        - Map evidence directly to the level anchors (1-5) defined in the rubric. Level 1 mirrors minimal capability; level 5 reflects mastery.
        - Use the criterion weights to compute total_score, noting the rubric minimum passing score of {payload.rubric.min_pass_score}.
        - Reference band notes, red flags, and evidence expectations when composing rationales and hints.
        - Provide targeted hints that address missing anchor elements (e.g., model selection trade-offs, data quality handling, validation rigor).
        - Mark rubric_filled only when each criterion has sufficient evidence to justify an anchor-aligned score.
        """
    ).strip()
