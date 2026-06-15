"""Caller-registered guardrail helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GuardrailDecision(str, Enum):
    """Decision returned by a guardrail handler."""

    PASS = "pass"
    ABORT = "abort"


@dataclass(frozen=True)
class GuardrailResult:
    """Structured result returned by a guardrail handler."""

    guardrail_id: str
    decision: GuardrailDecision = GuardrailDecision.PASS
    phase: str = "input"
    reason_code: str | None = None
    message: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision", GuardrailDecision(self.decision))
        object.__setattr__(self, "details", dict(self.details))


GuardrailHandler = Callable[[Any], GuardrailResult]


class InMemoryGuardrailRegistry:
    """Simple caller-owned guardrail handler registry."""

    def __init__(
        self,
        handlers: Mapping[str, GuardrailHandler] | None = None,
    ) -> None:
        self._handlers = dict(handlers or {})

    def has_guardrail(self, guardrail_id: str) -> bool:
        """Return whether a guardrail handler is registered."""

        return guardrail_id in self._handlers

    def run(self, guardrail_id: str, subject: Any) -> GuardrailResult:
        """Run a registered guardrail handler."""

        return self._handlers[guardrail_id](subject)
