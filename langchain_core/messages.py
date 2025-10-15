from dataclasses import dataclass


@dataclass
class HumanMessage:  # Minimal human message placeholder
    content: str
    role: str = "user"


@dataclass
class AIMessage:  # Minimal AI message placeholder
    content: str
    role: str = "assistant"


__all__ = ["HumanMessage", "AIMessage"]
