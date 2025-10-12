"""Lightweight CLI helpers for inspecting interview telemetry tables."""
from __future__ import annotations

import argparse
import sqlite3

from config.settings import settings


def tail_flags(limit: int = 20) -> None:
    conn = sqlite3.connect(settings.DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT timestamp, interview_id, candidate_id, stage, question_id, action, severity, reason_codes
            FROM interview_flags
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        for row in cursor.fetchall():
            ts, interview_id, candidate_id, stage, question_id, action, severity, reasons = row
            print(
                f"[{ts}] {interview_id}/{candidate_id} {stage}:{question_id} -> {action}/{severity} reasons={reasons}"
            )
    finally:
        conn.close()


def tail_actions(limit: int = 20) -> None:
    conn = sqlite3.connect(settings.DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT timestamp, interview_id, candidate_id, stage, question_id, action_id, source, metadata
            FROM quick_actions
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        for row in cursor.fetchall():
            ts, interview_id, candidate_id, stage, question_id, action_id, source, metadata = row
            print(
                f"[{ts}] {interview_id}/{candidate_id} {stage}:{question_id} action={action_id} source={source} meta={metadata}"
            )
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tail-flags", type=int, help="Show the latest behavior monitor flags")
    parser.add_argument("--tail-actions", type=int, help="Show the latest quick actions")
    args = parser.parse_args()

    if args.tail_flags:
        tail_flags(args.tail_flags)
    if args.tail_actions:
        tail_actions(args.tail_actions)


if __name__ == "__main__":
    main()
