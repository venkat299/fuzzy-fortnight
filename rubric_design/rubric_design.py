from __future__ import annotations  # Rubric design and persistence module

from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import Dict, Iterable, List, Literal
from uuid import uuid4
import sqlite3

from pydantic import BaseModel, Field, field_validator

from config import LlmRoute, load_app_registry
from jd_analysis import CompetencyArea, CompetencyMatrix
from llm_gateway import call

BandLiteral = Literal["0-1", "2-3", "4-6", "7-10", "10+"]


class RubricAnchor(BaseModel):  # Anchor description for a proficiency level
    level: int = Field(ge=1, le=5)
    text: str


class RubricCriterion(BaseModel):  # Criterion entry with anchors
    name: str
    weight: int = Field(default=1, ge=1, le=1)
    anchors: List[RubricAnchor] = Field(min_length=5, max_length=5)

    @field_validator("weight", mode="before")
    @classmethod
    def _force_weight(cls, value: object) -> int:  # Ensure weight stays at 1
        return 1

class Rubric(BaseModel):  # Rubric payload returned by LLM
    competency: str
    band: BandLiteral
    band_notes: List[str] = Field(min_length=1)
    criteria: List[RubricCriterion] = Field(min_length=3)
    red_flags: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(min_length=3)
    min_pass_score: int = Field(ge=1, le=5)

    @field_validator("min_pass_score", mode="before")
    @classmethod
    def _normalize_min_pass(cls, value: object) -> int:  # Clamp pass score into 1-5 integers
        try:
            numeric = int(round(float(value)))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 3
        return max(1, min(5, numeric))


class CompetencyDefaultsEntry(BaseModel):  # Competency-specific rubric defaults
    competency: str
    criteria: List[str] = Field(min_length=3, max_length=3)
    note: str = ""

    @field_validator("competency", "note", mode="before")
    @classmethod
    def _strip_text(cls, value: object) -> str:
        return str(value).strip() if value is not None else ""

    @field_validator("criteria", mode="after")
    @classmethod
    def _clean_criteria(cls, value: List[str]) -> List[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]  # type: ignore[arg-type]
        return cleaned[:3]


class CompetencyDefaultsPlan(BaseModel):  # LLM response describing competency defaults
    overview: str = ""
    competencies: List[CompetencyDefaultsEntry] = Field(default_factory=list)


class InterviewRubricSnapshot(BaseModel):  # Stored interview rubric response
    interview_id: str
    job_title: str
    experience_years: str
    job_description: str = ""
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
                """
                SELECT job_title, experience_years, status, job_description
                FROM interview_ready
                WHERE interview_id = ?
                """,
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
                job_description=interview["job_description"],
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
    defaults_route: LlmRoute | None = None,
) -> str:  # Generate rubrics and persist
    band = _infer_band(matrix.experience_years)
    rubrics: List[Rubric] = []
    areas = list(matrix.competency_areas)
    defaults_cfg = defaults_route or route
    defaults_plan = _safe_competency_defaults(
        job_title=matrix.job_title,
        experience_years=matrix.experience_years,
        job_description=job_description,
        route=defaults_cfg,
    )
    defaults_block = _render_defaults_block(defaults_plan)
    for index, raw_area in enumerate(areas):
        if isinstance(raw_area, CompetencyArea):
            area = raw_area
        elif isinstance(raw_area, dict):
            area = CompetencyArea.model_validate(raw_area)
        else:
            name, skills = _coerce_area_tuple(raw_area)
            area = CompetencyArea(name=name, skills=skills)
        task = _build_task(area, band, defaults_block)
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
    schemas = {
        "rubric_design.generate_rubric": Rubric,
        "rubric_design.generate_defaults": CompetencyDefaultsPlan,
    }
    registry = load_app_registry(config_path, schemas)
    route, _ = registry["rubric_design.generate_rubric"]
    defaults_route, _ = registry["rubric_design.generate_defaults"]
    store = RubricStore(db_path)
    return design_rubrics(
        matrix,
        route=route,
        store=store,
        job_description=job_description,
        defaults_route=defaults_route,
    )


def load_rubrics(interview_id: str, *, db_path: Path) -> InterviewRubricSnapshot:  # Load stored rubrics
    store = RubricStore(db_path)
    return store.load(interview_id)


def _build_task(area: CompetencyArea, band: BandLiteral, defaults_block: str) -> str:  # Build rubric design prompt
    prompt = dedent(
        """
        You are a rubric generator for verbal-only technical interviews. No coding, no drawing. Judge explanation quality, correctness, trade-offs, edge-case reasoning, and concrete experience.

        Input:
        {"competency": "%(competency)s", "band": "%(band)s"}

        Band scale (integers 1-5):
        1 = guided task or feature ownership.
        2 = component delivery with light guidance.
        3 = service or major feature ownership independently.
        4 = multi-service or cross-team leadership.
        5 = organization or platform direction setting.

        Use the integer band level to choose the output label:
        1 -> "0-1", 2 -> "2-3", 3 -> "4-6", 4 -> "7-10", 5 -> "10+".
        Mention the integer level in the first band_note to keep the scale explicit.

        {defaults_block}
        Anchor semantics: level integers 1-5 must align with increasing mastery.
        1 = incorrect or purely theoretical.
        2 = surface recall with limited depth.
        3 = correct for the band with concrete examples.
        4 = structured reasoning, balanced trade-offs, anticipates risks.
        5 = teaches others, covers edge cases, proactive mitigation.

        Minimum passing score: choose an integer 1-5, typically matching the band level. Never use decimals.

        Output strict JSON only

        {
          "competency": string,
          "band": "0-1" | "2-3" | "4-6" | "7-10" | "10+",
          "band_notes": ["Level 3: ...", "Scope: ...", "Autonomy: ..."],
          "criteria": [
            {
              "name": string,
              "weight": 1,
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
        - Provide exactly three criteria per competency.
        - Set weight to the integer 1 for every criterion.
        - For every criterion, return exactly five anchors covering levels 1 through 5. Do not omit any level.
        - Supply three "evidence" probes and three "red_flags" item (use [] only if none exist).
        - Use plain ASCII quotes and characters.
        - Ensure every anchor description names the level integer directly.
        - Set min_pass_score as an integer between 1 and 5.

        Guidance for anchors: tailor to the band's autonomy expectations; emphasize definitions, when-to-use, trade-offs, failure modes, and concrete experience.
        """
    ).strip()
    return prompt % {
        "competency": area.name,
        "band": band,
        "defaults_block": defaults_block,
    }


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


def _safe_competency_defaults(
    *,
    job_title: str,
    experience_years: str,
    job_description: str,
    route: LlmRoute,
) -> CompetencyDefaultsPlan:  # Query LLM for competency defaults with fallback
    try:
        return generate_competency_defaults(
            job_title=job_title,
            experience_years=experience_years,
            job_description=job_description,
            route=route,
        )
    except Exception:
        return CompetencyDefaultsPlan()


def generate_competency_defaults(
    *,
    job_title: str,
    experience_years: str,
    job_description: str,
    route: LlmRoute,
) -> CompetencyDefaultsPlan:  # Fetch competency default criteria guidance
    task = _build_defaults_task(job_title, experience_years, job_description)
    return call(task, CompetencyDefaultsPlan, cfg=route)


def _build_defaults_task(job_title: str, experience_years: str, job_description: str) -> str:  # Assemble defaults prompt
    prompt = dedent(
        """
        You analyze job descriptions and summarize competency defaults for verbal interview rubrics.
        Return JSON only.

        Schema:
        {
          "overview": string,
          "competencies": [
            {
              "competency": string,
              "criteria": [string, string, string],
              "note": string
            }
          ]
        }

        Rules:
        - Focus on the job's core competencies.
        - Criteria must be short verbal skills or behaviours.
        - Always produce exactly four competency entries.
        - Use exactly three criteria per competency.
        - Keep "note" empty when nothing important stands out.
        - Overview should mention the interview focus.
        - Reply with a single JSON object matching the schema.

        Input:
        {"job_title": "%(job_title)s", "experience_years": "%(experience_years)s", "job_description": "%(job_description)s"}
        """
    ).strip()
    return prompt % {
        "job_title": job_title.strip(),
        "experience_years": experience_years.strip(),
        "job_description": _truncate(job_description),
    }


def _render_defaults_block(plan: CompetencyDefaultsPlan) -> str:  # Render defaults heading for rubric prompt
    lines: List[str] = ["Defaults by competency (verbal, 3 criteria):", ""]
    entries = plan.competencies or []
    seen: Dict[str, bool] = {}
    for entry in entries:
        key = entry.competency.lower()
        if not entry.competency or key in seen:
            continue
        seen[key] = True
        details = "; ".join(entry.criteria) if entry.criteria else ""
        note = f"; {entry.note}" if entry.note else ""
        lines.append(f"* {entry.competency}: {details}{note}")
    if len(lines) == 2:
        lines.extend(_STATIC_DEFAULTS)
    lines.append("* If competency unrecognized, create exactly three verbal criteria with weight 1 each.")
    return "\n".join(lines)


def _truncate(value: str, limit: int = 2000) -> str:  # Trim long descriptions for prompt safety
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


_STATIC_DEFAULTS = [
    "* Backend Development: API Concepts & Contracts; Resilience; Data Flow; Security & Compliance",
    "* Front-End Engineering: Web Platform Fundamentals; State Management; Performance; Quality Mindset",
    "* Cloud & DevOps Practices: CI/CD; Infrastructure as Code; Observability; Reliability",
]


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
