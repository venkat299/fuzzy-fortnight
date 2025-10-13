from __future__ import annotations  # Persona agent generating interviewer questions

from textwrap import dedent
from typing import Type

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from config import LlmRoute
from llm_gateway import call


PERSONA_AGENT_KEY = "flow_manager.persona_agent"  # Registry key for persona agent configuration

PERSONA_GUIDANCE = dedent(  # Persona agent system guidance
    """
    You craft human interviewer prompts using supplied briefs.
    Maintain the requested tone and persona while sounding natural and adaptive.
    Output only the final question text with no commentary.
    """
).strip()


class PersonaQuestion(BaseModel):  # Persona agent output schema
    question: str

    @classmethod
    def from_raw_content(cls, content: str) -> "PersonaQuestion":  # Adapt raw string payloads into schema
        return cls(question=content.strip())


class PersonaAgent:  # Agent invoking persona LLM route
    def __init__(self, route: LlmRoute, schema: Type[PersonaQuestion]) -> None:  # Configure persona route and schema
        self._route = route
        self._schema = schema
        self._prompt = ChatPromptTemplate.from_messages(
            [
                ("system", PERSONA_GUIDANCE),
                (
                    "human",
                    (
                        "{brief}\n\n"
                        "Draft question to refine:\n{draft_question}\n\n"
                        "Polish or rewrite the draft so it matches the persona brief."
                        " If the draft is unusable, craft a fresh question that fulfills the brief."
                        " Reply with only the final interviewer question."
                    ),
                ),
            ]
        )

    def generate(self, *, brief: str, draft_question: str) -> str:  # Execute persona agent and return formatted question
        draft = draft_question.strip() or "(no draft provided)"
        task = self._prompt.format(brief=brief, draft_question=draft)
        result = call(task, self._schema, cfg=self._route)
        return result.question.strip()


__all__ = [
    "PERSONA_AGENT_KEY",
    "PERSONA_GUIDANCE",
    "PersonaAgent",
    "PersonaQuestion",
]
