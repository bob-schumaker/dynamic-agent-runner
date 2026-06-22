"""Caller-injected context selection contracts."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContextSelectionCandidate:
    """Structured older-turn candidate offered to a context selector."""

    turn_id: str
    text: str
    roles: tuple[str, ...]
    exact_match_count: int
    token_estimate: int | None = None


@dataclass(frozen=True)
class ContextSelection:
    """Selector score for one older-turn candidate."""

    turn_id: str
    score: float
    reason: str = "injected_semantic"


ContextSelector = Callable[
    [str, tuple[ContextSelectionCandidate, ...], Mapping[str, Any]],
    Iterable[ContextSelection],
]


__all__ = ["ContextSelection", "ContextSelectionCandidate", "ContextSelector"]
