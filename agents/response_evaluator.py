"""LLM-backed response evaluator with policy overrides."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from pydantic import ValidationError

from agents.types import EvalCriterionScore, EvalResult
from config.registry import get_model
from config.settings import settings

EVAL_KEY = "models.response_evaluator"


def _token_count(text: str) -> int:
    return 0 if not text else len(text.strip().split())


def _round_1dp(value: float) -> float:
    return float(f"{value:.1f}")


def _band(overall_1dp: float) -> str:
    if overall_1dp <= 2.0:
        return "low"
    if overall_1dp < 4.0:
        return "mid"
    return "high"


def _weights_from_rubric(rubric: Dict[str, Any]) -> List[Tuple[str, float]]:
    criteria = rubric.get("criteria", [])
    weights: List[Tuple[str, float]] = []
    for entry in criteria:
        try:
            cid = entry["id"]
            weight = float(entry.get("weight", 0.0))
        except (KeyError, TypeError, ValueError):  # pragma: no cover - defensive
            continue
        weights.append((cid, weight))
    return weights


def _weighted_overall(scores: List[EvalCriterionScore], rubric: Dict[str, Any]) -> float:
    weights = dict(_weights_from_rubric(rubric))
    total_weight = sum(weights.values()) or 1.0
    acc = 0.0
    for score in scores:
        acc += float(weights.get(score.id, 0.0)) * int(score.score)
    return acc / total_weight


def _policy_low_or_blocked(reply: str, is_blocked: bool) -> bool:
    return is_blocked or _token_count(reply) < settings.LOW_CONTENT_TOKENS


def _override_to_ones(rubric: Dict[str, Any], followup_index: int, competency_id: str, item_id: str) -> EvalResult:
    criteria = [
        EvalCriterionScore(id=crit["id"], score=1)
        for crit in rubric.get("criteria", [])
        if "id" in crit
    ]
    overall = 1.0
    return EvalResult(
        competency_id=competency_id,
        item_id=item_id,
        turn_index=followup_index,
        criterion_scores=criteria,
        overall=overall,
        band=_band(overall),
        notes="too brief or blocked; insufficient evidence",
    )


def score_turn(
    *,
    competency_id: str,
    item_id: str,
    followup_index: int,
    question_text: str,
    candidate_reply: str,
    rubric: Dict[str, Any],
    is_blocked: bool = False,
) -> EvalResult:
    """Evaluate a single turn using the rubric and policy overrides."""

    if _policy_low_or_blocked(candidate_reply, is_blocked):
        return _override_to_ones(rubric, followup_index, competency_id, item_id)

    llm = get_model(EVAL_KEY)
    raw = llm(
        system_prompt_path="prompts/response_evaluator.txt",
        inputs={
            "competency_id": competency_id,
            "item_id": item_id,
            "followup_index": followup_index,
            "question_text": question_text,
            "candidate_reply": candidate_reply,
            "rubric": rubric,
            "policies": {
                "low_content_token_threshold": settings.LOW_CONTENT_TOKENS,
                "max_followups_per_item": 2,
                "round_scores_to_dp": 1,
            },
            "context": {"is_blocked": False},
        },
        temperature=0.0,
        max_tokens=400,
    )

    try:
        parsed = EvalResult.model_validate(raw)
    except ValidationError:
        neutral_scores = [
            EvalCriterionScore(id=crit["id"], score=3)
            for crit in rubric.get("criteria", [])
            if "id" in crit
        ]
        overall = _round_1dp(_weighted_overall(neutral_scores, rubric))
        return EvalResult(
            competency_id=competency_id,
            item_id=item_id,
            turn_index=followup_index,
            criterion_scores=neutral_scores,
            overall=overall,
            band=_band(overall),
            notes="fallback schema; neutral scoring",
        )

    fixed_scores: List[EvalCriterionScore] = []
    for crit in parsed.criterion_scores:
        bounded = int(max(1, min(5, crit.score)))
        fixed_scores.append(EvalCriterionScore(id=crit.id, score=bounded))

    overall = _round_1dp(_weighted_overall(fixed_scores, rubric))
    return EvalResult(
        competency_id=parsed.competency_id or competency_id,
        item_id=parsed.item_id or item_id,
        turn_index=parsed.turn_index,
        criterion_scores=fixed_scores,
        overall=overall,
        band=_band(overall),
        notes=(parsed.notes or "")[:200],
    )


__all__ = ["score_turn", "EVAL_KEY"]
