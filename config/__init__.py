"""Configuration package for interview agent services."""
from .legacy import AppConfig, LlmRoute, load_app_registry, load_config, resolve_registry
from .registry import INTENT_KEY, MONITOR_KEY, bind_model, get_model
from .settings import Settings, settings

__all__ = [
    "AppConfig",
    "LlmRoute",
    "load_app_registry",
    "load_config",
    "resolve_registry",
    "INTENT_KEY",
    "MONITOR_KEY",
    "bind_model",
    "get_model",
    "Settings",
    "settings",
]
