"""Package-owned tracing primitives for workflow execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Protocol


REDACTED_VALUE = "[REDACTED]"


class TraceSink(Protocol):
    """Receives workflow trace events emitted by the executor."""

    def emit(self, event: "TraceEvent") -> None:
        """Receive a trace event."""


@dataclass(frozen=True)
class TraceEvent:
    """A single workflow trace event.

    `sensitive_fields` names payload keys that should be redacted before an
    event is emitted to an external observability backend.
    """

    sequence: int
    event_type: str
    node_id: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    sensitive_fields: tuple[str, ...] = ()

    def redacted_payload(self) -> dict[str, Any]:
        """Return a shallow redacted copy of the event payload."""

        redacted = dict(self.payload)
        for field_name in self.sensitive_fields:
            if field_name in redacted:
                redacted[field_name] = REDACTED_VALUE
        return redacted

    def redacted(self) -> "TraceEvent":
        """Return a copy of this event with sensitive payload fields redacted."""

        return replace(self, payload=self.redacted_payload())


@dataclass
class InMemoryTraceSink:
    """Simple trace sink useful for tests and local callers."""

    events: list[TraceEvent] = field(default_factory=list)

    def emit(self, event: TraceEvent) -> None:
        """Store a trace event in memory."""

        self.events.append(event)


class WorkflowTracer:
    """Emits trace events to execution state and an optional external sink."""

    def __init__(
        self,
        *,
        events: list[TraceEvent],
        sink: TraceSink | None = None,
    ) -> None:
        self._events = events
        self._sink = sink

    def emit(
        self,
        event_type: str,
        *,
        node_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        sensitive_fields: tuple[str, ...] = (),
    ) -> TraceEvent:
        """Create and publish a trace event."""

        event = TraceEvent(
            sequence=len(self._events) + 1,
            event_type=event_type,
            node_id=node_id,
            payload=dict(payload or {}),
            sensitive_fields=sensitive_fields,
        )
        self._events.append(event)
        if self._sink is not None:
            self._sink.emit(event)
        return event
