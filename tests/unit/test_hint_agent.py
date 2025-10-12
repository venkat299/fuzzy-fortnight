from types import SimpleNamespace

from config.registry import bind_model
from agents.hint_agent import HINT_KEY, run as hint_run


def fake_llm(**kwargs):
    inputs = kwargs.get("inputs", {})
    targets = inputs.get("evidence_targets") or []
    reply = inputs.get("last_reply", "")
    target = targets[0] if targets else "the key signal"
    suffix = "" if target in reply else f" and tie it to {target}"
    return {"hint": f"Name your role{suffix}."}


def _state():
    state = SimpleNamespace()
    state.persona = "Friendly Expert"
    state.question_text = "How did you set boundaries?"
    state.mem = {
        "facet_id": "F_BOUNDARIES",
        "facet_name": "Decomposition & Boundaries",
        "evidence_targets": ["boundary rationale", "coupling mitigations"],
    }
    state.user_msg = "Could I get a hint?"
    return state


def setup_module(_module):
    bind_model(HINT_KEY, fake_llm)


def test_hint_llm_required():
    state = _state()
    hint = hint_run(state)
    assert isinstance(hint, str) and hint
    assert "Here’s a nudge" in hint
    assert "boundary rationale" in hint


def test_hint_de_duplication():
    state = _state()
    first = hint_run(state)
    second = hint_run(state)
    assert first and second
    assert len(state.mem["prior_hints"]["F_BOUNDARIES"]) >= 2


def test_hint_uses_last_reply_cache():
    state = _state()
    state.user_msg = ""
    state.mem["last_reply_for_item"] = "I described the boundary rationale already."
    hint = hint_run(state)
    assert "boundary rationale" not in hint.lower()
