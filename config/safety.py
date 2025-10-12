"""YAML-driven safety configuration and analysis helpers."""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

CONFIG_PATH = os.environ.get("SAFETY_CONFIG", "config/safety.yaml")


@dataclass
class MatchHit:
    """Individual regex match metadata."""

    category: str
    pattern: str
    span: Tuple[int, int]
    excerpt: str


@dataclass
class SafetyFinding:
    """Aggregate result returned from the safety engine."""

    category: Optional[str]
    severity: str
    hits: List[MatchHit]
    allow_list_reason: Optional[str] = None


def _load_yaml(path: str) -> dict:
    import yaml  # local import to avoid mandatory dependency until used

    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


class SafetyEngine:
    """Compile and evaluate regex-based safety categories from YAML."""

    def __init__(self, path: str = CONFIG_PATH):
        self.path = path
        self._mtime = 0.0
        self._config: dict = {}
        self._compiled: Dict[str, List[re.Pattern[str]]] = {}
        self._severity: Dict[str, str] = {}
        self._precedence: List[str] = []
        self._allow_lists: Dict[str, List[str]] = {}
        self.reload_if_changed(force=True)

    # ------------------------------------------------------------------
    # Loading & compilation
    # ------------------------------------------------------------------
    def reload_if_changed(self, force: bool = False) -> None:
        """Reload YAML configuration when the file timestamp changes."""

        try:
            stat = os.stat(self.path)
            if not force and stat.st_mtime <= self._mtime:
                return
            cfg = _load_yaml(self.path)
            self._mtime = stat.st_mtime
        except FileNotFoundError:
            cfg = {
                "version": 1,
                "precedence": ["unsafe", "jailbreak", "pii", "offtopic", "low_content"],
                "categories": {},
                "allow_lists": {},
                "normalizers": ["strip_whitespace", "collapse_spaces", "to_lower"],
            }
            self._mtime = time.time()

        self._config = cfg
        self._precedence = cfg.get("precedence", [])
        self._severity = {
            name: values.get("severity", "info")
            for name, values in cfg.get("categories", {}).items()
        }
        self._allow_lists = {
            tag: list(terms or []) for tag, terms in cfg.get("allow_lists", {}).items()
        }
        self._compiled = {
            name: [re.compile(pattern) for pattern in values.get("patterns", [])]
            for name, values in cfg.get("categories", {}).items()
        }

    # ------------------------------------------------------------------
    # Normalization helpers
    # ------------------------------------------------------------------
    def _normalize(self, text: str) -> str:
        ops = self._config.get("normalizers", [])
        sample = text or ""
        if "strip_whitespace" in ops:
            sample = sample.strip()
        if "collapse_spaces" in ops:
            sample = re.sub(r"\s+", " ", sample)
        if "to_lower" in ops:
            sample = sample.lower()
        return sample

    # ------------------------------------------------------------------
    # Allow-list helpers
    # ------------------------------------------------------------------
    def _allow_ok(self, token: str, context_tags: List[str]) -> bool:
        tags = set(context_tags or [])
        normal_token = self._normalize(token)
        for tag, terms in self._allow_lists.items():
            if tag in tags:
                normalized_terms = {self._normalize(term) for term in terms}
                if normal_token in normalized_terms:
                    return True
        return False

    def allow_terms(self) -> List[str]:
        terms: List[str] = []
        for values in self._allow_lists.values():
            terms.extend(values)
        # Preserve insertion order while removing duplicates
        seen: set[str] = set()
        unique_terms: List[str] = []
        for term in terms:
            if term not in seen:
                seen.add(term)
                unique_terms.append(term)
        return unique_terms

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------
    def analyze(self, text: str, context_tags: Optional[List[str]] = None) -> SafetyFinding:
        self.reload_if_changed()
        context_tags = context_tags or []
        sample = self._normalize(text or "")
        matches: List[MatchHit] = []

        for category, patterns in self._compiled.items():
            for pattern in patterns:
                for match in pattern.finditer(sample):
                    token = match.group(0)
                    if self._allow_ok(token, context_tags):
                        return SafetyFinding(
                            category=None,
                            severity="info",
                            hits=[],
                            allow_list_reason=f"allowed by {context_tags}",
                        )
                    start, end = match.span()
                    excerpt = sample[max(0, start - 20) : min(len(sample), end + 20)]
                    matches.append(
                        MatchHit(
                            category=category,
                            pattern=pattern.pattern,
                            span=(start, end),
                            excerpt=excerpt,
                        )
                    )

        if not matches:
            return SafetyFinding(category=None, severity="info", hits=[])

        precedence_lookup = {name: index for index, name in enumerate(self._precedence)}
        winning_category = min(
            matches,
            key=lambda hit: precedence_lookup.get(hit.category, float("inf")),
        ).category
        severity = self._severity.get(winning_category, "info")
        top_hits = [hit for hit in matches if hit.category == winning_category]
        return SafetyFinding(category=winning_category, severity=severity, hits=top_hits)


_engine: Optional[SafetyEngine] = None


def safety_engine() -> SafetyEngine:
    global _engine
    if _engine is None:
        _engine = SafetyEngine()
    return _engine


def match_categories(text: str, context_tags: Optional[List[str]] = None) -> SafetyFinding:
    """Convenience wrapper returning the current engine's analysis."""

    return safety_engine().analyze(text, context_tags or [])


def allow_terms() -> List[str]:
    """Return the flattened allow-list terms for telemetry/prompts."""

    return safety_engine().allow_terms()


__all__ = [
    "MatchHit",
    "SafetyFinding",
    "SafetyEngine",
    "allow_terms",
    "match_categories",
    "safety_engine",
]
