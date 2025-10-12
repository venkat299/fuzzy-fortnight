import re

from agents.persona_manager import apply_persona


def test_fe_ask_question_trim():
    text = "Explain your approach. Include details about trade-offs and metrics. Also mention results."
    out = apply_persona(text, purpose="ask_question")
    assert out
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", out) if s.strip()]
    assert len(sentences) <= 2


def test_fe_redirect_wraps_core():
    out = apply_persona("Could you focus on the consistency aspect?", purpose="redirect")
    assert out.startswith("Interesting! Let’s refocus")
    assert "consistency" in out.lower()


def test_fe_block_refocus():
    out = apply_persona("Here is the safe version of the question.", purpose="block_refocus")
    assert "bypass the interview rules" in out


def test_hint_style():
    out = apply_persona("Address role → key decision → measurable outcome.", purpose="hint")
    assert out.lower().startswith("here’s a nudge")


def test_resume_line():
    out = apply_persona("We were discussing idempotency.", purpose="resume")
    assert out.lower().startswith("let’s pick up")
