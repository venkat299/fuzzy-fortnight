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


__all__ = ["InMemoryChatMessageHistory"]
