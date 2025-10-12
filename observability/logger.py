"""Structured logging utilities for interview orchestration."""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
import time
import uuid
from typing import Any

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
ENABLE_FILE_LOGS = os.getenv("ENABLE_FILE_LOGS", "1") in ("1", "true", "True")
LOG_FILE = os.getenv("LOG_FILE", "logs/interview.log")
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", "5242880"))
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))

_logger = logging.getLogger("interview")
_logger.setLevel(LOG_LEVEL)
_logger.propagate = False


def _ensure_handlers() -> None:
    if _logger.handlers:
        return

    # Console: human-readable lines only (stdout)
    human_console = logging.StreamHandler(stream=sys.stdout)
    human_console.setLevel(LOG_LEVEL)
    human_console.setFormatter(
        logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s :: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    human_console.addFilter(lambda record: True)
    _logger.addHandler(human_console)

    if not ENABLE_FILE_LOGS:
        return

    log_dir = os.path.dirname(LOG_FILE)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    # JSON file handler
    json_file = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
    )
    json_file.setLevel(LOG_LEVEL)
    json_file.setFormatter(logging.Formatter("%(message)s"))
    json_file.addFilter(lambda record: getattr(record, "is_json", False) is True)
    _logger.addHandler(json_file)

    # Human-readable file handler
    human_file_name = LOG_FILE if LOG_FILE.endswith(".log") else f"{LOG_FILE}.log"
    human_file_name = human_file_name.replace(".log", "-human.log")
    human_file = logging.handlers.RotatingFileHandler(
        human_file_name,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
    )
    human_file.setLevel(LOG_LEVEL)
    human_file.setFormatter(
        logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s :: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    human_file.addFilter(lambda record: getattr(record, "is_json", False) is not True)
    _logger.addHandler(human_file)


def _format_human(evt: dict[str, Any]) -> str:
    base = f"session={evt.get('session_id')} kind={evt.get('kind')}"
    extras: list[str] = []
    for key in ("node", "decision", "action", "severity", "ms", "intent", "outcome"):
        if key in evt:
            extras.append(f"{key}={evt[key]}")
    return base + (" " + " ".join(extras) if extras else "")


def log_event(kind: str, session_id: str, **fields: Any) -> None:
    """Emit human logs to console and JSON/human logs to files."""

    _ensure_handlers()

    payload: dict[str, Any] = {
        "ts": time.time(),
        "trace": str(uuid.uuid4()),
        "kind": kind,
        "session_id": session_id,
    }
    payload.update(fields)

    # Human line (console + human file handler)
    human_record = _logger.makeRecord(
        name=_logger.name,
        level=logging.INFO,
        fn="",
        lno=0,
        msg=_format_human(payload),
        args=(),
        exc_info=None,
    )
    human_record.is_json = False  # type: ignore[attr-defined]
    _logger.handle(human_record)

    if not ENABLE_FILE_LOGS:
        return

    # JSON line (file only)
    json_record = _logger.makeRecord(
        name=_logger.name,
        level=logging.INFO,
        fn="",
        lno=0,
        msg=json.dumps(payload, ensure_ascii=False),
        args=(),
        exc_info=None,
    )
    json_record.is_json = True  # type: ignore[attr-defined]
    _logger.handle(json_record)


__all__ = ["log_event"]
