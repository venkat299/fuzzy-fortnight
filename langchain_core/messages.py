from dataclasses import dataclass


@dataclass
class HumanMessage:  # Minimal human message placeholder
    content: str


@dataclass
class AIMessage:  # Minimal AI message placeholder
    content: str


__all__ = ["HumanMessage", "AIMessage"]
