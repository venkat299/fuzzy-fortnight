from __future__ import annotations  # Minimal output parser adapters

from typing import Any, Optional, Type

from pydantic import BaseModel

from .runnables import Runnable


class PydanticOutputParser(Runnable):  # Parses LLM output into a Pydantic model
    def __init__(self, schema: Type[BaseModel]) -> None:
        self._schema = schema

    def invoke(self, input: Any, config: Optional[dict] = None) -> BaseModel:
        if isinstance(input, self._schema):
            return input
        if isinstance(input, BaseModel):
            return self._schema.model_validate(input.model_dump())
        if isinstance(input, str):
            return self._schema.model_validate_json(_strip_fences(input))
        if isinstance(input, dict):
            return self._schema.model_validate(input)
        raise TypeError("Unsupported input for PydanticOutputParser")


def _strip_fences(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        value = "\n".join(lines)
    return value


__all__ = ["PydanticOutputParser"]
