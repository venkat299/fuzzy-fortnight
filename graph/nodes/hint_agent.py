"""Hint agent node wrapper."""
from agents.hint_agent import run as run_hint


def run(state):
    return run_hint(state)
