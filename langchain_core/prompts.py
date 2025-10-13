from __future__ import annotations  # Simple prompt template stub

from typing import Iterable, Tuple


class ChatPromptTemplate:  # Minimal template builder supporting .format()
    def __init__(self, messages: Iterable[Tuple[str, str]]) -> None:
        self._messages = list(messages)

    @classmethod
    def from_messages(cls, messages: Iterable[Tuple[str, str]]) -> "ChatPromptTemplate":
        return cls(messages)

    def format(self, **kwargs: str) -> str:
        parts = []
        for _role, template in self._messages:
            parts.append(template.format(**kwargs))
        return "\n".join(parts)


__all__ = ["ChatPromptTemplate"]
