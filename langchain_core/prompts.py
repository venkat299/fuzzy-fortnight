from __future__ import annotations  # LangChain-style chat prompt templates

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .runnables import Runnable

@dataclass(frozen=True)
class MessagesPlaceholder:  # Placeholder resolved with runtime chat history
    variable_name: str


class ChatPromptTemplate(Runnable):  # Prompt runnable emitting chat messages from templates
    def __init__(self, messages: Iterable[Any]) -> None:
        self._messages: List[Any] = list(messages)

    @classmethod
    def from_messages(cls, messages: Iterable[Any]) -> "ChatPromptTemplate":
        return cls(messages)

    def format_messages(self, **kwargs: Any) -> List[Dict[str, str]]:
        rendered: List[Dict[str, str]] = []
        for entry in self._messages:
            if isinstance(entry, MessagesPlaceholder):
                value = kwargs.get(entry.variable_name, [])
                rendered.extend(_coerce_history(value, entry.variable_name))
                continue
            role, template = _coerce_message(entry)
            rendered.append({"role": role, "content": template.format(**kwargs)})
        return rendered

    def format(self, **kwargs: Any) -> str:
        parts = [message["content"] for message in self.format_messages(**kwargs)]
        return "\n".join(parts)

    def invoke(self, input_values: Dict[str, Any], config: Dict[str, Any] | None = None) -> List[Dict[str, str]]:
        return self.format_messages(**input_values)


def _coerce_message(entry: Any) -> Tuple[str, str]:
    if not isinstance(entry, Sequence) or len(entry) != 2:
        raise TypeError("Prompt messages must be (role, template) tuples")
    role, template = entry
    if not isinstance(role, str) or not isinstance(template, str):
        raise TypeError("Prompt entries must contain string role and template")
    return role, template


def _coerce_history(value: Any, name: str) -> List[Dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, Sequence):
        raise TypeError(f"Placeholder '{name}' must be a sequence of messages")
    result: List[Dict[str, str]] = []
    for item in value:
        if isinstance(item, dict):
            role = str(item.get("role", "")).strip()
            content = str(item.get("content", ""))
        else:
            role = getattr(item, "role", "") or getattr(item, "type", "")
            content = getattr(item, "content", "")
        if not role:
            raise TypeError("Each history message requires a role")
        result.append({"role": role, "content": content})
    return result


__all__ = ["ChatPromptTemplate", "MessagesPlaceholder"]
