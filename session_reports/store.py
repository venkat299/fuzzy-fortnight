from __future__ import annotations  # Session report persistence layer

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Sequence

from flow_manager.models import EvaluatorState
from rubric_design import InterviewRubricSnapshot

from .models import SessionExchange, SessionReport


class SessionReportStore:  # SQLite-backed persistence for interview sessions
    def __init__(self, path: Path) -> None:  # Initialize store with database path
        self._path = path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:  # Open SQLite connection with schema settings
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:  # Create persistence tables if missing
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_reports (
                    session_id TEXT PRIMARY KEY,
                    interview_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    candidate_name TEXT NOT NULL,
                    job_title TEXT NOT NULL,
                    rubric_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_exchanges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    stage TEXT NOT NULL,
                    competency TEXT,
                    criteria_json TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    system_message TEXT,
                    evaluator_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES session_reports(session_id) ON DELETE CASCADE
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def initialize_session(
        self,
        interview_id: str,
        candidate_id: str,
        *,
        candidate_name: str,
        job_title: str,
        rubric: InterviewRubricSnapshot,
        reset: bool = False,
    ) -> None:  # Insert or refresh session header and optionally reset transcript
        session_id = self._session_id(interview_id, candidate_id)
        now = datetime.utcnow().isoformat(timespec="seconds")
        payload = rubric.model_dump_json()
        conn = self._connect()
        try:
            if reset:
                conn.execute(
                    "DELETE FROM session_exchanges WHERE session_id = ?",
                    (session_id,),
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO session_reports (
                        session_id,
                        interview_id,
                        candidate_id,
                        candidate_name,
                        job_title,
                        rubric_json,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        interview_id,
                        candidate_id,
                        candidate_name,
                        job_title,
                        payload,
                        now,
                        now,
                    ),
                )
                conn.commit()
                return
            conn.execute(
                """
                INSERT OR IGNORE INTO session_reports (
                    session_id,
                    interview_id,
                    candidate_id,
                    candidate_name,
                    job_title,
                    rubric_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    interview_id,
                    candidate_id,
                    candidate_name,
                    job_title,
                    payload,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE session_reports
                SET candidate_name = ?,
                    job_title = ?,
                    rubric_json = ?,
                    updated_at = ?,
                    created_at = COALESCE(created_at, ?)
                WHERE session_id = ?
                """,
                (
                    candidate_name,
                    job_title,
                    payload,
                    now,
                    now,
                    session_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def record_exchange(
        self,
        interview_id: str,
        candidate_id: str,
        *,
        stage: str,
        question: str,
        answer: str,
        competency: str | None,
        criteria: Sequence[str],
        system_message: str,
        evaluator: EvaluatorState,
    ) -> None:  # Append a transcript exchange for the session
        session_id = self._session_id(interview_id, candidate_id)
        now = datetime.utcnow().isoformat(timespec="seconds")
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM session_reports WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Session '{session_id}' not initialized")
            next_sequence = conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM session_exchanges WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
            conn.execute(
                """
                INSERT INTO session_exchanges (
                    session_id,
                    sequence,
                    stage,
                    competency,
                    criteria_json,
                    question,
                    answer,
                    system_message,
                    evaluator_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    int(next_sequence),
                    stage,
                    competency,
                    json.dumps([item for item in criteria]),
                    question,
                    answer,
                    system_message,
                    evaluator.model_dump_json(),
                    now,
                ),
            )
            conn.execute(
                "UPDATE session_reports SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            conn.commit()
        finally:
            conn.close()

    def load_report(self, interview_id: str, candidate_id: str) -> SessionReport:  # Load full report with transcript
        session_id = self._session_id(interview_id, candidate_id)
        conn = self._connect()
        try:
            header = conn.execute(
                """
                SELECT interview_id, candidate_id, candidate_name, job_title, rubric_json, created_at, updated_at
                FROM session_reports
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if header is None:
                raise KeyError(f"Session '{session_id}' not found")
            rows = conn.execute(
                """
                SELECT sequence, stage, competency, criteria_json, question, answer, system_message, evaluator_json, created_at
                FROM session_exchanges
                WHERE session_id = ?
                ORDER BY sequence ASC
                """,
                (session_id,),
            ).fetchall()
        finally:
            conn.close()
        exchanges: List[SessionExchange] = []
        for row in rows:
            criteria = json.loads(row["criteria_json"]) if row["criteria_json"] else []
            evaluator = EvaluatorState.model_validate_json(row["evaluator_json"])
            exchanges.append(
                SessionExchange(
                    sequence=row["sequence"],
                    stage=row["stage"],
                    question=row["question"],
                    answer=row["answer"],
                    competency=row["competency"],
                    criteria=[str(item) for item in criteria],
                    system_message=row["system_message"] or "",
                    evaluator=evaluator,
                )
            )
        rubric = InterviewRubricSnapshot.model_validate_json(header["rubric_json"])
        return SessionReport(
            session_id=session_id,
            interview_id=header["interview_id"],
            candidate_id=header["candidate_id"],
            candidate_name=header["candidate_name"],
            job_title=header["job_title"],
            rubric=rubric,
            exchanges=exchanges,
            created_at=header["created_at"],
            updated_at=header["updated_at"],
        )

    def _session_id(self, interview_id: str, candidate_id: str) -> str:  # Deterministic session identifier helper
        return f"{interview_id}:{candidate_id}"


__all__ = ["SessionReportStore"]
