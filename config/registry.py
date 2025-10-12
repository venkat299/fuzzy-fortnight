"""In-memory model registry for agent components."""
from typing import Any, Callable, Dict

_REGISTRY: Dict[str, Callable[..., Any]] = {}


def bind_model(key: str, fn: Callable[..., Any]) -> None:
    """Bind a callable implementation to a registry key."""
    _REGISTRY[key] = fn


def get_model(key: str) -> Callable[..., Any]:
    """Retrieve a callable from the registry.

    Raises:
        KeyError: If no callable has been bound for ``key``.
    """

    if key not in _REGISTRY:
        raise KeyError(f"Model not bound in registry: {key}")
    return _REGISTRY[key]


INTENT_KEY = "models.intent_classifier"
MONITOR_KEY = "models.behavior_monitor"
