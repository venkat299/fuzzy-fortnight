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
                    created_at TEXT NOT NULL,
                    job_description TEXT DEFAULT ''
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
            self._ensure_column(
                conn,
                "interview_ready",
                "job_description",
                "TEXT DEFAULT ''",
            )
        finally:
            conn.close()

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:  # Ensure column exists
        existing = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            conn.commit()

    def save(
        self,
        interview_id: str,
        job_title: str,
        experience_years: str,
        job_description: str,
        rubrics: Iterable[Rubric],
    ) -> None:  # Persist rubrics
        now = datetime.utcnow().isoformat(timespec="seconds")
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO interview_ready (interview_id, job_title, experience_years, status, created_at, job_description)
                VALUES (?, ?, ?, 'ready', ?, ?)
                """,
                (interview_id, job_title, experience_years, now, job_description)
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

    def list_interviews(self) -> List[sqlite3.Row]:  # List stored interviews ordered by recency
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT interview_id, job_title, experience_years, status, created_at, job_description
                FROM interview_ready
                ORDER BY datetime(created_at) DESC, interview_id DESC
                """
            ).fetchall()
            return list(rows)
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


def design_rubrics(
    matrix: CompetencyMatrix,
    *,
    route: LlmRoute,
    store: RubricStore,
    job_description: str,
) -> str:  # Generate rubrics and persist
    band = _infer_band(matrix.experience_years)
    rubrics: List[Rubric] = []
    areas = list(matrix.competency_areas)
    for index, raw_area in enumerate(areas):
        if isinstance(raw_area, CompetencyArea):
            area = raw_area
        elif isinstance(raw_area, dict):
            area = CompetencyArea.model_validate(raw_area)
        else:
            name, skills = _coerce_area_tuple(raw_area)
            area = CompetencyArea(name=name, skills=skills)
        task = _build_task(area, band)
        rubric = call(task, Rubric, cfg=route)
        rubrics.append(rubric)
        # if index < len(areas) - 1:
        #     time.sleep(3)
    interview_id = uuid4().hex
    store.save(
        interview_id,
        matrix.job_title,
        matrix.experience_years,
        job_description,
        rubrics,
    )
    return interview_id


def design_with_config(
    matrix: CompetencyMatrix,
    *,
    config_path: Path,
    db_path: Path,
    job_description: str,
) -> str:  # Generate rubrics using config
    registry = load_app_registry(config_path, {"rubric_design.generate_rubric": Rubric})
    route, _ = registry["rubric_design.generate_rubric"]
    store = RubricStore(db_path)
    return design_rubrics(matrix, route=route, store=store, job_description=job_description)


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

        Strict requirements:
        - Return a single JSON object only (no markdown fences, no prose).
        - Populate every field exactly as shown above; never omit required keys.
        - Provide 3 criteria per competency. Weights must sum to 1.0, use decimals.
        - For every criterion, return exactly five anchors covering levels 1 through 5. Do not omit any level.
        - Supply 3-5 "evidence" probes and at least one "red_flags" item (use [] only if none exist).
        - Use plain ASCII quotes and characters.

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


def _coerce_area_tuple(raw_area: object) -> tuple[str, List[str]]:  # Normalize tuple/list competency data
    if isinstance(raw_area, (list, tuple)) and len(raw_area) == 2:
        name = str(raw_area[0])
        skills_raw = raw_area[1]
        if isinstance(skills_raw, (list, tuple)):
            skills = [str(skill) for skill in skills_raw]
        else:
            skills = [str(skills_raw)] if skills_raw is not None else []
        return name, skills
    raise TypeError(f"Unsupported competency area format: {raw_area!r}")
