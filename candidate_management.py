from __future__ import annotations  # Candidate storage helpers

from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import uuid4
import sqlite3

from pydantic import BaseModel


class CandidateRecord(BaseModel):  # Stored candidate entry
    candidate_id: str
    full_name: str
    resume: str
    interview_id: Optional[str] = None
    status: str
    created_at: str


class CandidateStore:  # SQLite-backed candidate storage
    def __init__(self, path: Path) -> None:  # Initialize store and schema
        self._path = path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:  # Create SQLite connection
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:  # Ensure candidate table exists
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS interview_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    resume TEXT NOT NULL,
                    interview_id TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(interview_id) REFERENCES interview_ready(interview_id)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def list_candidates(self) -> List[CandidateRecord]:  # List candidates ordered by recency
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT candidate_id, full_name, resume, interview_id, status, created_at
                FROM interview_candidates
                ORDER BY datetime(created_at) DESC, candidate_id DESC
                """
            ).fetchall()
            return [
                CandidateRecord(
                    candidate_id=row["candidate_id"],
                    full_name=row["full_name"],
                    resume=row["resume"],
                    interview_id=row["interview_id"],
                    status=row["status"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]
        finally:
            conn.close()

    def create_candidate(
        self,
        *,
        full_name: str,
        resume: str,
        interview_id: Optional[str],
        status: str,
    ) -> CandidateRecord:  # Persist a new candidate
        candidate_id = uuid4().hex
        now = datetime.utcnow().isoformat(timespec="seconds")
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO interview_candidates (candidate_id, full_name, resume, interview_id, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (candidate_id, full_name, resume, interview_id, status, now),
            )
            conn.commit()
            return CandidateRecord(
                candidate_id=candidate_id,
                full_name=full_name,
                resume=resume,
                interview_id=interview_id,
                status=status,
                created_at=now,
            )
        finally:
            conn.close()


__all__ = ["CandidateRecord", "CandidateStore"]
