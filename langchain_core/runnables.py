from __future__ import annotations  # Minimal runnable primitives inspired by LangChain

from typing import Any, Callable, Iterable, List, Optional


class Runnable:  # Base runnable implementing composition helpers
    def invoke(self, input: Any, config: Optional[dict] = None) -> Any:  # noqa: D401
        raise NotImplementedError

    def __or__(self, other: Any) -> "RunnableSequence":
        return RunnableSequence([ensure_runnable(self), ensure_runnable(other)])


class RunnableLambda(Runnable):  # Wraps a callable for runnable composition
    def __init__(self, func: Callable[[Any], Any]) -> None:
        self._func = func

    def invoke(self, input: Any, config: Optional[dict] = None) -> Any:
        return self._func(input)


class RunnablePassthrough(Runnable):  # Returns the original input optionally projecting keys
    def __init__(self, fields: Optional[Iterable[str]] = None) -> None:
        self._fields = list(fields) if fields is not None else None

    def invoke(self, input: Any, config: Optional[dict] = None) -> Any:
        if self._fields is None:
            return input
        if not isinstance(input, dict):
            raise TypeError("RunnablePassthrough with fields requires dict input")
        return {key: input[key] for key in self._fields if key in input}


class RunnableSequence(Runnable):  # Sequentially executes runnables piping outputs
    def __init__(self, steps: Iterable[Runnable]) -> None:
        self._steps: List[Runnable] = list(steps)

    def invoke(self, input: Any, config: Optional[dict] = None) -> Any:
        value = input
        for step in self._steps:
            value = step.invoke(value, config=config)
        return value

    def __or__(self, other: Any) -> "RunnableSequence":
        return RunnableSequence(self._steps + [ensure_runnable(other)])


def ensure_runnable(obj: Any) -> Runnable:
    if isinstance(obj, Runnable):
        return obj
    if callable(obj):
        return RunnableLambda(obj)
    raise TypeError("Object is not runnable")


__all__ = [
    "Runnable",
    "RunnableLambda",
    "RunnablePassthrough",
    "RunnableSequence",
    "ensure_runnable",
]
