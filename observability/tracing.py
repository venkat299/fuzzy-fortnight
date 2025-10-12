"""Simple span helper for recording node timings."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def span(state, name: str) -> Iterator[None]:
    start = time.time()
    try:
        yield
    finally:
        elapsed_ms = int((time.time() - start) * 1000)
        state.events.append({"span": name, "ms": elapsed_ms})


__all__ = ["span"]
