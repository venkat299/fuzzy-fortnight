from __future__ import annotations  # Simple chat history stub

from typing import List

from .messages import AIMessage, HumanMessage


class InMemoryChatMessageHistory:  # Stores alternating user/AI messages
    def __init__(self) -> None:
        self.messages: List[object] = []

    def add_user_message(self, content: str) -> None:
        self.messages.append(HumanMessage(content=content))

    def add_ai_message(self, content: str) -> None:
        self.messages.append(AIMessage(content=content))

    def as_messages(self) -> List[dict]:  # Return dict messages with role/content pairs
        return [{"role": getattr(msg, "role", "user"), "content": msg.content} for msg in self.messages]


__all__ = ["InMemoryChatMessageHistory"]
