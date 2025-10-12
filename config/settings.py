"""Application settings and configuration management."""
from __future__ import annotations

from typing import Any, Dict

from pydantic import Field

try:  # pragma: no cover - prefer pydantic-settings when available
    from pydantic_settings import BaseSettings, SettingsConfigDict  # type: ignore
except ImportError:  # pragma: no cover
    from pydantic import BaseModel  # type: ignore

    class BaseSettings(BaseModel):  # type: ignore[misc]
        """Minimal fallback shim when pydantic-settings is unavailable."""

        model_config: Dict[str, Any] = {"extra": "ignore"}

    def SettingsConfigDict(**kwargs: Any) -> Dict[str, Any]:  # type: ignore[misc]
        return kwargs


class Settings(BaseSettings):
    """Settings loaded from environment variables or defaults."""

    DB_PATH: str = Field(default="data/interview.db")
    RAW_TEXT_RETENTION_DAYS: int = 90

    PERSONA_DEFAULT: str = "Friendly Expert"
    OFF_TOPIC_CUTOFF: float = 0.45
    LOW_CONTENT_TOKENS: int = 12
    HINTS_PER_STAGE: int = 2
    THINK_SECONDS: int = 30

    model_config = SettingsConfigDict(env_file=".env", validate_assignment=True)


settings = Settings()
