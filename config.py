from __future__ import annotations  # Configuration schema for LLM routing

from pathlib import Path
from typing import Dict, Tuple, Type

from pydantic import BaseModel, Field


class LlmRoute(BaseModel):  # LLM endpoint configuration
    name: str
    base_url: str
    endpoint: str
    model: str
    timeout_s: float = Field(ge=0.1)
    max_retries: int = Field(default=2, ge=0)
    api_key_env: str | None = None
    response_format: str | None = None
    extra_headers: Dict[str, str] = Field(default_factory=dict)


class AppConfig(BaseModel):  # Application configuration root
    llm_routes: Dict[str, LlmRoute]
    registry: Dict[str, str]


def load_config(path: Path) -> AppConfig:  # Load configuration from disk
    data = path.read_text(encoding="utf-8")
    return AppConfig.model_validate_json(data)


def resolve_registry(cfg: AppConfig, schemas: Dict[str, Type[BaseModel]]) -> Dict[str, Tuple[LlmRoute, Type[BaseModel]]]:  # Build registry with schemas
    resolved: Dict[str, Tuple[LlmRoute, Type[BaseModel]]] = {}
    for target, route_id in cfg.registry.items():
        if route_id not in cfg.llm_routes:
            raise KeyError(f"Route '{route_id}' missing for '{target}'")
        if target not in schemas:
            raise KeyError(f"Schema missing for '{target}'")
        schema = schemas[target]
        if not issubclass(schema, BaseModel):
            raise TypeError(f"Schema for '{target}' must be BaseModel")
        resolved[target] = (cfg.llm_routes[route_id], schema)
    return resolved


def load_app_registry(path: Path, schemas: Dict[str, Type[BaseModel]]) -> Dict[str, Tuple[LlmRoute, Type[BaseModel]]]:  # Load config and build registry
    cfg = load_config(path)
    return resolve_registry(cfg, schemas)
