from config.registry import bind_model
from agents.response_evaluator import EVAL_KEY, score_turn

RUBRIC = {
    "criteria": [
        {"id": "C1", "name": "Evidence", "weight": 0.34, "definition": ""},
        {"id": "C2", "name": "Reasoning", "weight": 0.33, "definition": ""},
        {"id": "C3", "name": "Technical Depth", "weight": 0.33, "definition": ""},
    ],
    "bands": {"low": [1, 2], "mid": [3], "high": [4, 5]},
}


def fake_llm_good(**kwargs):
    return {
        "competency_id": "ARCH",
        "item_id": "ARCH_01",
        "turn_index": kwargs["inputs"]["followup_index"],
        "criterion_scores": [
            {"id": "C1", "score": 4},
            {"id": "C2", "score": 4},
            {"id": "C3", "score": 3},
        ],
        "overall": 3.7,
        "band": "mid",
        "notes": "good structure; minor gaps",
    }


def fake_llm_bad_schema(**kwargs):
    return {"unexpected": True}


def setup_module(_module):
    bind_model(EVAL_KEY, fake_llm_good)


def test_low_content_override():
    result = score_turn(
        competency_id="ARCH",
        item_id="ARCH_01",
        followup_index=0,
        question_text="Q",
        candidate_reply="too short",
        rubric=RUBRIC,
        is_blocked=False,
    )
    assert result.overall == 1.0
    assert result.band == "low"
    assert all(score.score == 1 for score in result.criterion_scores)


def test_good_path(monkeypatch):
    bind_model(EVAL_KEY, fake_llm_good)
    reply = (
        "We used idempotent handlers with retries, circuit breakers, clear ownership, "
        "and post-deploy metrics to prove stability."
    )
    result = score_turn(
        competency_id="ARCH",
        item_id="ARCH_01",
        followup_index=0,
        question_text="Q",
        candidate_reply=reply,
        rubric=RUBRIC,
    )
    assert result.band in {"mid", "high"}
    assert 1.0 <= result.overall <= 5.0
    assert result.turn_index == 0


def test_schema_fallback(monkeypatch):
    bind_model(EVAL_KEY, fake_llm_bad_schema)
    reply = (
        "Detailed explanation exceeding thresholds with trade-offs, metrics, ownership details, "
        "and mitigation steps spelled out."
    )
    result = score_turn(
        competency_id="ARCH",
        item_id="ARCH_01",
        followup_index=1,
        question_text="Q",
        candidate_reply=reply,
        rubric=RUBRIC,
    )
    assert result.overall >= 3.0
    assert result.band in {"mid", "high"}
    assert all(score.score == 3 for score in result.criterion_scores)
