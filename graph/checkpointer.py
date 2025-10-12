"""Minimal checkpoint persistence helpers."""
from __future__ import annotations

import json
import os
from typing import Optional

from .state import GraphState

BASE_DIR = "data/checkpoints"


def _checkpoint_path(session_id: str) -> str:
    return os.path.join(BASE_DIR, f"{session_id}.json")


def save_checkpoint(state: GraphState) -> str:
    """Persist the full graph state atomically and return the file path."""
    os.makedirs(BASE_DIR, exist_ok=True)
    path = _checkpoint_path(state.session_id)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(state.model_dump(), handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)
    return path


def load_checkpoint(session_id: str) -> Optional[GraphState]:
    """Load a graph state from disk if present."""
    path = _checkpoint_path(session_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return GraphState(**data)
