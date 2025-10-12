"""Shared type definitions for agents."""
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Stage = Literal["warmup", "competency", "wrapup"]


class MonitorResult(BaseModel):
    action: Literal["ALLOW", "REDIRECT", "REMIND", "NUDGE_DEPTH", "BLOCK_AND_REFOCUS"]
    severity: Literal["info", "low", "high", "critical"]
    reason_codes: List[Literal["off_topic", "silence", "jailbreak", "low_content", "unsafe"]]
    rationale: str
    safe_reply: str
    quick_actions: List[Literal["hint", "think_30", "repeat", "skip"]] = Field(default_factory=list)
    proceed_to_intent_classifier: bool = True


class IntentResult(BaseModel):
    intent: Literal["answer", "ask_hint", "ask_clarify", "ask_pause", "ask_think", "other"]
    confidence: float
    rationale: str


class EvalCriterionScore(BaseModel):
    id: str
    score: int  # 1..5


class EvalResult(BaseModel):
    competency_id: str
    item_id: str
    turn_index: int
    criterion_scores: List[EvalCriterionScore]
    overall: float
    band: Literal["low", "mid", "high"]
    notes: str


class QuestionMetadata(BaseModel):
    competency_id: str
    item_id: str
    followup_index: int
    facet_id: str
    facet_name: str
    evidence_targets: List[str] = Field(default_factory=list)


class QuestionOut(BaseModel):
    question_text: str
    metadata: QuestionMetadata


class QuickAction(BaseModel):
    id: Literal["hint", "think_30", "repeat", "skip"]
    note: Optional[str] = None


class ScoresTriple(BaseModel):
    avg: float
    median: float
    max: float


class LiveScores(BaseModel):
    per_competency: Dict[str, ScoresTriple]
    overall: ScoresTriple
