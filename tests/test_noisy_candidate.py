from difflib import SequenceMatcher

from candidate_agent.auto_reply import NOISY_LEVELS, generate_noisy_answer, set_noisy_seed


def _stub_call_factory(answer: str):
    def _call(task: str, schema, *, cfg, **kwargs):
        return schema(answer=answer)

    return _call


def test_level_configuration():
    assert NOISY_LEVELS[1]["max_words"] == 50
    assert NOISY_LEVELS[1]["hedging"] == 0.5
    assert NOISY_LEVELS[1]["filler"] == 0.4
    assert NOISY_LEVELS[1]["mistakes"] == (2, 3)
    assert NOISY_LEVELS[1]["grammar_p"] == 0.3
    assert NOISY_LEVELS[1]["typo_p"] == 0.2
    assert NOISY_LEVELS[1]["miss_p"] == 0.25
    assert NOISY_LEVELS[5]["max_words"] == 120
    assert NOISY_LEVELS[5]["hedging"] == 0.05
    assert NOISY_LEVELS[5]["filler"] == 0.0
    assert NOISY_LEVELS[5]["mistakes"] == (0, 0)
    assert NOISY_LEVELS[5]["grammar_p"] == 0.0
    assert NOISY_LEVELS[5]["typo_p"] == 0.0
    assert NOISY_LEVELS[5]["miss_p"] == 0.0


def test_truncation(monkeypatch):
    answer = " ".join([f"word{i}" for i in range(200)])
    monkeypatch.setattr(
        "candidate_agent.auto_reply.call", _stub_call_factory(answer)
    )
    set_noisy_seed(11)
    result = generate_noisy_answer("Describe your experience", level=1)
    assert len(result.split()) <= NOISY_LEVELS[1]["max_words"]


def test_determinism_with_seed(monkeypatch):
    answer = "This answer mentions database index 42 for repeatability."
    monkeypatch.setattr(
        "candidate_agent.auto_reply.call", _stub_call_factory(answer)
    )
    set_noisy_seed(7)
    first = generate_noisy_answer("Explain sharding", level=2)
    set_noisy_seed(7)
    second = generate_noisy_answer("Explain sharding", level=2)
    assert first == second


def test_monotonic_errors(monkeypatch):
    base = (
        "This answer covers database index tuning with 10 steps so therefore the logic flows."
    )
    monkeypatch.setattr(
        "candidate_agent.auto_reply.call", _stub_call_factory(base)
    )
    set_noisy_seed(5)
    noisy_l1 = generate_noisy_answer("How do you tune indexes?", level=1)
    set_noisy_seed(5)
    noisy_l5 = generate_noisy_answer("How do you tune indexes?", level=5)
    ratio_l1 = SequenceMatcher(None, base, noisy_l1).ratio()
    ratio_l5 = SequenceMatcher(None, base, noisy_l5).ratio()
    assert ratio_l1 < ratio_l5


def test_api_contract(monkeypatch):
    monkeypatch.setattr(
        "candidate_agent.auto_reply.call",
        _stub_call_factory("This is a confident summary answer."),
    )
    set_noisy_seed(13)
    output = generate_noisy_answer("Summarize your background", level=3)
    assert isinstance(output, str) and output.strip()
