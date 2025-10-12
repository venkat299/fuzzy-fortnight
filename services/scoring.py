"""Scoring aggregation helpers and persistence adapters."""
from __future__ import annotations

from statistics import median
from typing import Dict, List

from agents.types import EvalResult, LiveScores, ScoresTriple
from storage.scores import insert_score, insert_scores_overall, insert_scores_summary


def _round1(value: float) -> float:
    """Round a float to one decimal place with stable formatting."""
    return float(f"{value:.1f}")


def attach_cache(state) -> Dict[str, Dict[str, Dict[str, object]]]:
    """Ensure the session state has a scoring cache and return it."""

    return state.mem.setdefault(
        "score_cache",
        {
            "competencies": {},
            "items_per_competency": 3,
        },
    )


def _bucket(cache: Dict[str, object], competency_id: str) -> Dict[str, object]:
    return cache.setdefault(competency_id, {"items": {}, "skipped_count": 0})


def record_eval(state, ev: EvalResult) -> None:
    """Update best-of tracking and persist the per-item turn history."""

    cache = attach_cache(state)
    comp_bucket = _bucket(cache["competencies"], ev.competency_id)
    item_entry = comp_bucket["items"].setdefault(
        ev.item_id,
        {"turns": [], "best_of": 1.0},
    )

    item_entry["turns"].append(ev.model_dump())
    if ev.overall > item_entry["best_of"]:
        item_entry["best_of"] = ev.overall

    insert_score(
        interview_id=state.interview_id,
        candidate_id=state.candidate_id,
        competency=ev.competency_id,
        item_id=ev.item_id,
        best_of_score=float(item_entry["best_of"]),
        turn_scores_json={"turns": item_entry["turns"]},
    )


def mark_skip(state, competency_id: str, item_id: str) -> None:
    """Record a skipped item for later summaries."""

    cache = attach_cache(state)
    comp_bucket = _bucket(cache["competencies"], competency_id)
    comp_bucket["skipped_count"] += 1
    comp_bucket["items"].setdefault(item_id, {"turns": [], "best_of": 1.0})


def _triples_from_bestofs(bestofs: List[float]) -> ScoresTriple:
    if not bestofs:
        return ScoresTriple(avg=0.0, median=0.0, max=0.0)
    avg = _round1(sum(bestofs) / len(bestofs))
    med = _round1(float(median(bestofs)))
    mx = _round1(max(bestofs))
    return ScoresTriple(avg=avg, median=med, max=mx)


def live_scores(state) -> LiveScores:
    """Produce per-competency and overall score triples."""

    cache = attach_cache(state)
    per_comp: Dict[str, ScoresTriple] = {}
    comp_avgs: List[float] = []

    for comp_id, bucket in cache["competencies"].items():
        bestofs = [entry["best_of"] for entry in bucket["items"].values() if entry["turns"]]
        triple = _triples_from_bestofs(bestofs)
        per_comp[comp_id] = triple
        if bestofs:
            comp_avgs.append(triple.avg)

    if comp_avgs:
        overall = ScoresTriple(
            avg=_round1(sum(comp_avgs) / len(comp_avgs)),
            median=_round1(float(median(comp_avgs))),
            max=_round1(max(comp_avgs)),
        )
    else:
        overall = ScoresTriple(avg=0.0, median=0.0, max=0.0)

    return LiveScores(per_competency=per_comp, overall=overall)


def finalize_competency(state, competency_id: str) -> Dict[str, object]:
    """Persist a competency summary row and return the computed triple."""

    cache = attach_cache(state)
    comp_bucket = _bucket(cache["competencies"], competency_id)
    bestofs = [entry["best_of"] for entry in comp_bucket["items"].values() if entry["turns"]]
    attempted = sum(1 for entry in comp_bucket["items"].values() if entry["turns"])
    skipped = int(comp_bucket["skipped_count"])

    triple = _triples_from_bestofs(bestofs)
    insert_scores_summary(
        interview_id=state.interview_id,
        candidate_id=state.candidate_id,
        competency=competency_id,
        avg_score=triple.avg,
        median_score=triple.median,
        max_score=triple.max,
        attempted_count=attempted,
        skipped_count=skipped,
    )
    return {
        "competency": competency_id,
        "triple": triple.model_dump(),
        "attempted": attempted,
        "skipped": skipped,
    }


def finalize_overall(state) -> Dict[str, object]:
    """Persist the overall summary row and return the live snapshot."""

    live = live_scores(state)
    overall = live.overall
    insert_scores_overall(
        interview_id=state.interview_id,
        candidate_id=state.candidate_id,
        avg_score=overall.avg,
        median_score=overall.median,
        max_score=overall.max,
    )
    return {
        "overall": overall.model_dump(),
        "per_competency": {key: triple.model_dump() for key, triple in live.per_competency.items()},
    }


__all__ = [
    "attach_cache",
    "record_eval",
    "mark_skip",
    "live_scores",
    "finalize_competency",
    "finalize_overall",
]
