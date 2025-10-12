"""FastAPI routes for interview session control."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from agents.persona_manager import apply_persona
from api.schemas import ApiResp, FinishReq, QuestionPayload, StartReq, TurnReq, UIMessage
from config.settings import settings
from graph.checkpointer import save_checkpoint
from graph.state import GraphState
from graph.build import step
from services.sessions import load_session, new_session
from services.think_expiry import maybe_resume_think
from services.qa_policy import remaining_hints, row as qa_row
from storage.actions import insert_quick_action


router = APIRouter(prefix="/api/interview-sessions")

def _emit_quick_actions(state: GraphState) -> List[str]:
    return qa_row(
        skip_streak=state.skip_streak,
        hints_used_stage=state.hints_used_stage,
        hints_cap=settings.HINTS_PER_STAGE,
    )


def _log_quick_action(
    state: GraphState,
    action_id: Optional[str],
    *,
    source: str = "standard",
    latency_ms: Optional[int] = None,
) -> None:
    if not action_id:
        return
    insert_quick_action(
        interview_id=state.interview_id,
        candidate_id=state.candidate_id,
        stage=state.stage,
        question_id=state.question_id or "NA",
        action_id=action_id,
        source=source,
        latency_ms=latency_ms,
        metadata={
            "skip_streak": state.skip_streak,
            "remaining_hints": remaining_hints(
                state.hints_used_stage, settings.HINTS_PER_STAGE
            ),
        },
    )


def _question_from_state(state: GraphState) -> Optional[Dict[str, Any]]:
    if not state.question_text:
        return None
    metadata = None
    if state.mem:
        metadata = {
            "competency_id": state.mem.get("competency_id"),
            "item_id": state.mem.get("item_id"),
            "followup_index": state.mem.get("followup_index"),
            "facet_id": state.mem.get("facet_id"),
            "facet_name": state.mem.get("facet_name"),
            "evidence_targets": state.mem.get("evidence_targets"),
        }
    return {"text": state.question_text, "metadata": metadata}


def _as_ui_messages(raw: List[Any]) -> List[UIMessage]:
    messages: List[UIMessage] = []
    for entry in raw:
        if isinstance(entry, UIMessage):
            messages.append(entry)
        elif isinstance(entry, str):
            messages.append(UIMessage(text=entry))
        elif isinstance(entry, dict):
            messages.append(UIMessage(text=entry.get("text", ""), role=entry.get("role", "assistant")))
        else:  # pragma: no cover - defensive
            messages.append(UIMessage(text=str(entry)))
    return messages


def _decision_to_payload(state: GraphState, decision: Dict[str, Any]) -> Dict[str, Any]:
    dtype = decision.get("type")
    payload = decision.get("payload", {})
    ui_messages: List[UIMessage] = []
    question = payload.get("question")

    if dtype in {"ASK", "EVAL_AND_ASK_NEXT", "SKIP_AND_NEXT", "AUTO_SKIP_MOVED"}:
        if question is None:
            question = _question_from_state(state)
    elif dtype == "REASK":
        text = payload.get("text")
        if text:
            ui_messages.append(UIMessage(text=text))
        question = question or _question_from_state(state)
    elif dtype == "HINT":
        text = payload.get("text")
        if text:
            ui_messages.append(UIMessage(text=text))
        question = _question_from_state(state)
    elif dtype == "CLARIFY":
        text = payload.get("text")
        if text:
            ui_messages.append(UIMessage(text=text))
        question = _question_from_state(state)
    elif dtype == "PAUSE_THINK":
        text = payload.get("text")
        if not text:
            text = apply_persona(
                "Take the 30 seconds to gather your thoughts—I’ll wait right here.",
                persona=state.persona,
                purpose="remind",
            )
        ui_messages.append(UIMessage(text=text))
        question = _question_from_state(state)
    else:
        question = question or _question_from_state(state)

    quick_actions = payload.get("quick_actions")
    if quick_actions is None:
        quick_actions = _emit_quick_actions(state)

    live_scores = payload.get("live_scores")

    return {
        "ui_messages": ui_messages,
        "question": question,
        "quick_actions": quick_actions,
        "live_scores": live_scores,
    }


def _resp_from_state(state: GraphState, payload: Dict[str, Any]) -> ApiResp:
    if "decision" in payload:
        converted = _decision_to_payload(state, payload["decision"])
        ui_messages = converted["ui_messages"]
        question_raw = converted["question"]
        quick_actions = converted["quick_actions"]
        live_scores = converted.get("live_scores")
    else:
        ui_messages = _as_ui_messages(payload.get("ui_messages", []))
        question_raw = payload.get("question") or _question_from_state(state)
        quick_actions_raw = payload.get("quick_actions")
        quick_actions = _emit_quick_actions(state) if quick_actions_raw is None else quick_actions_raw
        live_scores = payload.get("live_scores")

    question = None
    if question_raw and question_raw.get("text"):
        question = QuestionPayload(text=question_raw["text"], metadata=question_raw.get("metadata"))

    if live_scores is None:
        live_scores = payload.get("live_scores") or state.mem.get("live_scores")

    return ApiResp(
        session_id=state.session_id,
        state_ref=state.session_id,
        ui_messages=ui_messages,
        question=question,
        quick_actions=quick_actions,
        live_scores=live_scores,
        event_log=list(getattr(state, "events", [])),
        ui_state={
            "skip_streak": state.skip_streak,
            "hints_used_stage": state.hints_used_stage,
            "hints_cap": settings.HINTS_PER_STAGE,
        },
    )


@router.post("/start", response_model=ApiResp)
def start(req: StartReq) -> ApiResp:
    persona = req.persona_override or settings.PERSONA_DEFAULT
    state = new_session(req.interview_id, req.candidate_id, persona)
    result = step(state)
    save_checkpoint(state)
    return _resp_from_state(state, result)


@router.post("/turn", response_model=ApiResp)
def turn(req: TurnReq) -> ApiResp:
    state = load_session(req.session_id)
    if not state:
        raise HTTPException(status_code=404, detail="session not found")

    resume_payload = maybe_resume_think(state)
    if resume_payload:
        save_checkpoint(state)
        return _resp_from_state(
            state,
            {
                "ui_messages": [resume_payload["resume_line"]],
                "question": resume_payload.get("question"),
                "live_scores": state.mem.get("live_scores"),
            },
        )

    if req.quick_action:
        state.quick_action = req.quick_action
        _log_quick_action(state, req.quick_action.get("id"))
        if req.user_msg:
            state.queued_user_msg = req.user_msg
            state.user_msg = None
        else:
            state.user_msg = req.user_msg
    else:
        state.quick_action = None
        state.user_msg = req.user_msg
        if req.user_msg is None and state.queued_user_msg:
            state.user_msg = state.queued_user_msg
            state.queued_user_msg = None

    result = step(state)

    if state.queued_user_msg and not state.user_msg:
        state.user_msg = state.queued_user_msg
        state.queued_user_msg = None
        result = step(state)

    state.user_msg = None
    state.quick_action = None
    save_checkpoint(state)

    return _resp_from_state(state, result)


@router.post("/finish", response_model=ApiResp)
def finish(req: FinishReq) -> ApiResp:
    state = load_session(req.session_id)
    if not state:
        raise HTTPException(status_code=404, detail="session not found")

    from services.scoring import finalize_overall

    summary = finalize_overall(state)
    save_checkpoint(state)

    payload = {
        "ui_messages": [
            apply_persona(
                "Thanks for the conversation—your scores are available on the interview summary.",
                persona=state.persona,
                purpose="wrapup",
            )
        ],
        "question": None,
        "quick_actions": [],
        "live_scores": summary,
    }
    return _resp_from_state(state, payload)
