from types import SimpleNamespace

import services.scoring as scoring
from agents.types import EvalCriterionScore, EvalResult


def _state():
    s = SimpleNamespace()
    s.interview_id = "i1"
    s.candidate_id = "c1"
    s.mem = {}
    return s


def _ev(comp: str, item: str, overall: float, turn_index: int = 0) -> EvalResult:
    return EvalResult(
        competency_id=comp,
        item_id=item,
        turn_index=turn_index,
        criterion_scores=[EvalCriterionScore(id="C1", score=3)],
        overall=overall,
        band="mid",
        notes="ok",
    )


def test_bestof_and_live_scores(monkeypatch):
    monkeypatch.setattr(scoring, "insert_score", lambda **_: None)
    monkeypatch.setattr(scoring, "insert_scores_summary", lambda **_: None)
    monkeypatch.setattr(scoring, "insert_scores_overall", lambda **_: None)

    state = _state()
    scoring.attach_cache(state)
    scoring.record_eval(state, _ev("ARCH", "ARCH_01", 3.2))
    scoring.record_eval(state, _ev("ARCH", "ARCH_01", 4.1, turn_index=1))
    scoring.record_eval(state, _ev("DATA", "DATA_01", 2.8))

    live = scoring.live_scores(state)
    assert live.per_competency["ARCH"].max >= 4.1
    assert 0.0 < live.overall.avg <= 5.0


def test_mark_skip_and_finalize(monkeypatch):
    monkeypatch.setattr(scoring, "insert_score", lambda **_: None)
    monkeypatch.setattr(scoring, "insert_scores_summary", lambda **_: None)
    monkeypatch.setattr(scoring, "insert_scores_overall", lambda **_: None)

    state = _state()
    scoring.record_eval(state, _ev("ARCH", "ARCH_02", 3.0))
    scoring.mark_skip(state, "ARCH", "ARCH_03")

    summary = scoring.finalize_competency(state, "ARCH")
    assert summary["attempted"] >= 1
    assert summary["skipped"] >= 1

    overall = scoring.finalize_overall(state)
    assert "overall" in overall and "per_competency" in overall
