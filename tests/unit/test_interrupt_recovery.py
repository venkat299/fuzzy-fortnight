from __future__ import annotations

from graph.state import GraphState
from graph.checkpointer import save_checkpoint
from graph import checkpointer
from graph.nodes.interrupt_recovery import run as run_interrupt
from agents.interrupt_recovery import run_resume


def _mk_state() -> GraphState:
    state = GraphState(session_id="sess-ir", interview_id="i", candidate_id="c")
    state.stage = "competency"
    state.question_id = "ARCH_01"
    state.question_text = "How did you ensure idempotency?"
    state.mem = {
        "competency_id": "ARCH",
        "item_id": "ARCH_01",
        "facet_id": "F_IDEMPOTENCY",
        "facet_name": "Idempotency & Retries",
        "followup_index": 0,
        "evidence_targets": ["idempotency locus", "retry policy"],
        "think_until": "2024-01-01T00:00:00Z",
    }
    return state


def test_resume_with_checkpoint(tmp_path, monkeypatch):
    checkpoint_dir = tmp_path / "checkpoints"
    monkeypatch.setattr(checkpointer, "BASE_DIR", str(checkpoint_dir))

    state = _mk_state()
    save_checkpoint(state)

    payload = run_interrupt(state, reason="think_expired")
    assert "resume_line" in payload
    assert payload["question"]["text"].lower().startswith("how")
    assert state.mem.get("think_until") is None
    assert payload["question"]["metadata"]["facet_id"] == "F_IDEMPOTENCY"


def test_resume_without_checkpoint(monkeypatch):
    monkeypatch.setattr(checkpointer, "BASE_DIR", "nonexistent-dir")
    payload = run_resume(
        session_id="missing", reason="reconnected", persona="Friendly Expert", fallback_question_text="Re-asking last question."
    )
    assert payload["question"]["text"].startswith("Re-asking")
    assert payload["question"]["metadata"] is None
