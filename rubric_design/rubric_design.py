from __future__ import annotations  # Rubric design and persistence module

from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import Iterable, List, Literal
from uuid import uuid4
import sqlite3

from pydantic import BaseModel, Field

from config import LlmRoute, load_app_registry
from jd_analysis import CompetencyArea, CompetencyMatrix
from llm_gateway import call

BandLiteral = Literal["0-1", "2-3", "4-6", "7-10", "10+"]


class RubricAnchor(BaseModel):  # Anchor description for a proficiency level
    level: int = Field(ge=1, le=5)
    text: str


class RubricCriterion(BaseModel):  # Criterion entry with anchors
    name: str
    weight: float = Field(ge=0.0)
    anchors: List[RubricAnchor] = Field(min_length=5, max_length=5)


class Rubric(BaseModel):  # Rubric payload returned by LLM
    competency: str
    band: BandLiteral
    band_notes: List[str] = Field(min_length=1)
    criteria: List[RubricCriterion] = Field(min_length=3)
    red_flags: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(min_length=3)
    min_pass_score: float = Field(ge=0.0)


class InterviewRubricSnapshot(BaseModel):  # Stored interview rubric response
    interview_id: str
    job_title: str
    experience_years: str
    rubrics: List[Rubric]
    status: str


class RubricStore:  # SQLite-backed rubric storage
    def __init__(self, path: Path) -> None:  # Initialize store and schema
        self._path = path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:  # Create SQLite connection
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:  # Ensure required tables exist
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS interview_ready (
                    interview_id TEXT PRIMARY KEY,
                    job_title TEXT NOT NULL,
                    experience_years TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS competency_rubrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    interview_id TEXT NOT NULL,
                    competency TEXT NOT NULL,
                    rubric_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(interview_id) REFERENCES interview_ready(interview_id)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def save(self, interview_id: str, job_title: str, experience_years: str, rubrics: Iterable[Rubric]) -> None:  # Persist rubrics
        now = datetime.utcnow().isoformat(timespec="seconds")
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO interview_ready (interview_id, job_title, experience_years, status, created_at)
                VALUES (?, ?, ?, 'ready', ?)
                """,
                (interview_id, job_title, experience_years, now)
            )
            conn.executemany(
                """
                INSERT INTO competency_rubrics (interview_id, competency, rubric_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        interview_id,
                        rubric.competency,
                        rubric.model_dump_json(),
                        now,
                    )
                    for rubric in rubrics
                ]
            )
            conn.commit()
        finally:
            conn.close()

    def load(self, interview_id: str) -> InterviewRubricSnapshot:  # Load rubrics for interview
        conn = self._connect()
        try:
            interview = conn.execute(
                "SELECT job_title, experience_years, status FROM interview_ready WHERE interview_id = ?",
                (interview_id,)
            ).fetchone()
            if interview is None:
                raise KeyError(f"Interview '{interview_id}' not found")
            rows = conn.execute(
                "SELECT rubric_json FROM competency_rubrics WHERE interview_id = ? ORDER BY id",
                (interview_id,)
            ).fetchall()
            rubrics = [Rubric.model_validate_json(row["rubric_json"]) for row in rows]
            return InterviewRubricSnapshot(
                interview_id=interview_id,
                job_title=interview["job_title"],
                experience_years=interview["experience_years"],
                rubrics=rubrics,
                status=interview["status"],
            )
        finally:
            conn.close()


def design_rubrics(matrix: CompetencyMatrix, *, route: LlmRoute, store: RubricStore) -> str:  # Generate rubrics and persist
    band = _infer_band(matrix.experience_years)
    rubrics: List[Rubric] = []
    for area in matrix.competency_areas:
        task = _build_task(area, band)
        rubric = call(task, Rubric, cfg=route)
        rubrics.append(rubric)
    interview_id = uuid4().hex
    store.save(interview_id, matrix.job_title, matrix.experience_years, rubrics)
    return interview_id


def design_with_config(matrix: CompetencyMatrix, *, config_path: Path, db_path: Path) -> str:  # Generate rubrics using config
    registry = load_app_registry(config_path, {"rubric_design.generate_rubric": Rubric})
    route, _ = registry["rubric_design.generate_rubric"]
    store = RubricStore(db_path)
    return design_rubrics(matrix, route=route, store=store)


def load_rubrics(interview_id: str, *, db_path: Path) -> InterviewRubricSnapshot:  # Load stored rubrics
    store = RubricStore(db_path)
    return store.load(interview_id)


def _build_task(area: CompetencyArea, band: BandLiteral) -> str:  # Build rubric design prompt
    prompt = dedent(
        """
        You are a rubric generator for verbal-only technical interviews. No coding, no drawing. Judge explanation quality, correctness, trade-offs, edge-case reasoning, and concrete experience.

        Input:
        {"competency": "%(competency)s", "band": "%(band)s"}

        Band scopes
        0–1=task/feature, guided; 2–3=component, some guidance; 4–6=service, independent; 7–10=multi-service, leads; 10+=org/system, sets direction.

        Defaults by competency (verbal, 4×0.25):

        * Backend Development: API Concepts & Contracts; State/Concurrency/Resilience; Performance & Data Flow; Security & Data Handling
        * Front-End Engineering: Web Platform Fundamentals; State & Data Flow; Performance Reasoning; Quality Mindset
        * Database & Query Optimization: Modeling & Keys; Query & Index Reasoning; Transactions & Consistency; Caching & Access Patterns
        * Cloud & DevOps Practices: CI/CD & Rollback; Infra Basics (Containers/IaC); Monitoring & Alerting; Cost & Security Posture
        * Software Quality & Maintenance: Test Strategy; Refactoring & Code Health; Docs & Change Management; Defect Prevention & RCA
        * If competency unrecognized, create 3–5 verbal criteria totaling 1.0.

        Anchor semantics (verbal):
        1=incorrect/hand-wavy; 2=surface recall; 3=correct for band with examples; 4=clear structure and trade-offs; 5=precise, anticipates pitfalls, teaches.

        Min pass score by band: 0–1:3.0, 2–3:3.2, 4–6:3.4, 7–10:3.6, 10+:3.8.

        Output strict JSON only

        {
          "competency": string,
          "band": "0-1" | "2-3" | "4-6" | "7-10" | "10+",
          "band_notes": ["Verbal-only signals", "Scope: ...", "Autonomy: ..."],
          "criteria": [
            {
              "name": string,
              "weight": number,
              "anchors": [
                {"level":1,"text":string},
                {"level":2,"text":string},
                {"level":3,"text":string},
                {"level":4,"text":string},
                {"level":5,"text":string}
              ]
            }
          ],
          "red_flags": [string],
          "evidence": [string],
          "min_pass_score": number
        }

        Guidance for anchors: tailor to band scope; emphasize definitions, when-to-use, trade-offs, failure modes, and concrete examples from experience.
        """
    ).strip()
    return prompt % {"competency": area.name, "band": band}


def _infer_band(experience_years: str) -> BandLiteral:  # Map experience text to band literal
    normalized = experience_years.strip().lower()
    for band in ("0-1", "2-3", "4-6", "7-10", "10+"):
        if band in normalized:
            return band  # type: ignore[return-value]
    digits = [int(part) for part in normalized.replace("+", " ").replace("-", " ").split() if part.isdigit()]
    if digits:
        value = max(digits)
    else:
        value = 5
    if value <= 1:
        return "0-1"
    if value <= 3:
        return "2-3"
    if value <= 6:
        return "4-6"
    if value <= 10:
        return "7-10"
    return "10+"
