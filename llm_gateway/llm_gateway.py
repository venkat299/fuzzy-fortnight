from __future__ import annotations  # LLM request gateway module

import json
import logging
import os
import threading
from typing import Any, Callable, Dict, Optional, Protocol, Tuple, Type, TypeVar

from pydantic import BaseModel, ValidationError

from config import LlmRoute


logger = logging.getLogger(__name__)  # Module logger setup


_MODEL_LOCKS: Dict[str, threading.Lock] = {}
_MODEL_LOCKS_GUARD = threading.Lock()


class HttpClient(Protocol):  # Minimal HTTP client protocol
    def post(self, url: str, *, json: Dict[str, Any], headers: Dict[str, str], timeout: float) -> "HttpResponse": ...


class HttpResponse(Protocol):  # Minimal HTTP response protocol
    @property
    def status_code(self) -> int: ...

    def json(self) -> Any: ...

    @property
    def text(self) -> str: ...


class LlmGatewayError(RuntimeError):  # Base gateway error
    pass


T = TypeVar("T", bound=BaseModel)


def _lock_for(cfg: LlmRoute) -> threading.Lock:
    key = cfg.name or f"{cfg.base_url}{cfg.endpoint}"
    with _MODEL_LOCKS_GUARD:
        lock = _MODEL_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _MODEL_LOCKS[key] = lock
    return lock


def call(task: str, schema: Type[T], *, cfg: LlmRoute, client: Optional[HttpClient] = None) -> T:  # Invoke configured LLM route and validate output
    def _execute() -> T:
        base_messages = []
        if cfg.enforce_json:
            schema_json = json.dumps(schema.model_json_schema(), indent=2)
            system_prompt = "Reply with a single JSON object matching this schema:\n" + schema_json
            base_messages.append({"role": "system", "content": system_prompt})
        base_messages.append({"role": "user", "content": task})
        attempts = cfg.max_retries + 1
        last_error: Optional[Exception] = None
        last_error_text: Optional[str] = None
        preview = task.strip().splitlines()[0] if task.strip() else ""
        if len(preview) > 120:
            preview = preview[:117] + "..."
        logger.info(
            "LLM request start route=%s model=%s attempts=%d preview=%s",
            cfg.name,
            cfg.model,
            attempts,
            preview,
        )
        for attempt in range(attempts):
            messages = list(base_messages)
            if attempt > 0:
                messages.append(
                    {
                        "role": "system",
                        "content": _retry_hint(last_error_text, cfg.enforce_json),
                    }
                )
            payload: Dict[str, Any] = {"model": cfg.model, "messages": messages}
            if cfg.response_format:
                payload["response_format"] = {"type": cfg.response_format}
            headers = {"Content-Type": "application/json"}
            if cfg.api_key_env:
                api_key = os.getenv(cfg.api_key_env)
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
            headers.update(cfg.extra_headers)
            logger.info(
                "LLM request send route=%s model=%s attempt=%d/%d preview=%s",
                cfg.name,
                cfg.model,
                attempt + 1,
                attempts,
                preview,
            )
            try:
                response, close_cb = _post(f"{cfg.base_url}{cfg.endpoint}", payload, headers, cfg.timeout_s, client)
            except Exception as exc:  # noqa: BLE001
                logger.error("LLM transport failure: %s", exc)
                raise LlmGatewayError("LLM transport failed") from exc
            if response.status_code >= 400:
                logger.error("LLM error status: %s", response.status_code)
                raise LlmGatewayError(f"LLM returned status {response.status_code}")
            try:
                data = response.json()
            except Exception as exc:  # noqa: BLE001
                logger.error("Invalid JSON payload from LLM: %s", exc)
                raise LlmGatewayError("LLM payload was not JSON") from exc
            content = _extract_content(data)
            try:
                parsed = _validate(schema, content)
                _close_safely(close_cb)
                logger.info(
                    "LLM request done route=%s model=%s attempt=%d",
                    cfg.name,
                    cfg.model,
                    attempt + 1,
                )
                return parsed
            except (json.JSONDecodeError, ValidationError) as exc:
                logger.warning("LLM output validation failed: %s", exc)
                last_error = exc
                last_error_text = str(exc)
                _close_safely(close_cb)
                continue
        raise LlmGatewayError("LLM output validation failed") from last_error

    if getattr(cfg, "sequential", False):
        lock = _lock_for(cfg)
        with lock:
            return _execute()
    return _execute()


def _post(url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: float, client: Optional[HttpClient]) -> Tuple[HttpResponse, Optional[Callable[[], None]]]:  # Dispatch HTTP request
    if client is not None:
        response = client.post(url, json=payload, headers=headers, timeout=timeout)
        close_cb = getattr(client, "close", None)
        if callable(close_cb):
            return response, close_cb
        return response, None
    try:
        import httpx  # type: ignore
    except ImportError as exc:  # noqa: F401
        raise LlmGatewayError("httpx is required for default transport") from exc
    http_client = httpx.Client(timeout=timeout)
    response = http_client.post(url, json=payload, headers=headers)
    return response, http_client.close


def _close_safely(close_cb: Optional[Callable[[], None]]) -> None:  # Close HTTP client callback when provided
    if close_cb is not None:
        close_cb()


def _extract_content(data: Any) -> str:  # Extract message content from LLM response
    if isinstance(data, dict):
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, str):
                return content
        if isinstance(data.get("content"), str):
            return data["content"]
    raise LlmGatewayError("LLM response missing content")


def _validate(schema: Type[T], content: str) -> T:  # Parse JSON content with schema
    cleaned = _strip_code_fences(content)
    try:
        return schema.model_validate_json(cleaned)
    except (json.JSONDecodeError, ValidationError) as exc:
        adapter = getattr(schema, "from_raw_content", None)
        if callable(adapter):
            try:
                return adapter(cleaned)  # type: ignore[return-value]
            except Exception:  # noqa: BLE001
                pass
        raise exc


def _strip_code_fences(content: str) -> str:  # Remove common markdown fences from LLM output
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
            while lines and lines[0].strip() == "":
                lines = lines[1:]
            while lines and lines[-1].strip() == "":
                lines = lines[:-1]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
    return text


def _retry_hint(error_text: Optional[str], enforce_json: bool) -> str:  # Compose retry instructions including last error
    base = "The previous reply failed validation."
    if error_text:
        truncated = error_text.splitlines()[0].strip()
        if len(truncated) > 200:
            truncated = truncated[:197] + "..."
        base += f" Reason: {truncated}."
    if enforce_json:
        return base + " Return a single JSON object that matches the schema."
    return base + " Follow the requested format precisely."
