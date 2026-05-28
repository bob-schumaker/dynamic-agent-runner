"""Package-owned tracing primitives for workflow execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from threading import RLock
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
    run_id: str | None = None
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

    def __post_init__(self) -> None:
        self._lock = RLock()

    def emit(self, event: TraceEvent) -> None:
        """Store a trace event in memory."""

        with self._lock:
            self.events.append(event)


class WorkflowTracer:
    """Emits trace events to execution state and an optional external sink."""

    def __init__(
        self,
        *,
        events: list[TraceEvent],
        sink: TraceSink | None = None,
        run_id: str | None = None,
    ) -> None:
        self._events = events
        self._sink = sink
        self._run_id = run_id
        self._lock = RLock()

    def emit(
        self,
        event_type: str,
        *,
        node_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        sensitive_fields: tuple[str, ...] = (),
    ) -> TraceEvent:
        """Create and publish a trace event."""

        with self._lock:
            event = TraceEvent(
                sequence=len(self._events) + 1,
                event_type=event_type,
                run_id=self._run_id,
                node_id=node_id,
                payload=dict(payload or {}),
                sensitive_fields=sensitive_fields,
            )
            self._events.append(event)
        if self._sink is not None:
            self._sink.emit(event)
        return event
