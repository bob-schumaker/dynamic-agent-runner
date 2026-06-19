"""Persistent agent session state and in-memory storage."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
from typing import Any
from uuid import uuid4

from dynamic_agent_runner.context import WorkflowExecutionContext
from dynamic_agent_runner.errors import AgentSessionError
from dynamic_agent_runner.executor import (
    WorkflowInterruptedResult,
    WorkflowResult,
    _run_async_from_sync,
    execute_workflow_async,
)
from dynamic_agent_runner.openai_client import OpenAIMessage
from dynamic_agent_runner.tracing import TraceEvent, TraceSink


AGENT_SESSION_STATE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class AgentSessionResult:
    """Result returned after a session accepts one prompt."""

    workflow_result: WorkflowResult | WorkflowInterruptedResult
    state: AgentSessionState

    @property
    def final_result(self) -> Any:
        """Return the bounded workflow final result."""

        return self.workflow_result.final_result


@dataclass(frozen=True)
class AgentSessionStreamEvent:
    """Caller-facing event emitted while a session accepts one prompt."""

    sequence: int
    event_type: str
    session_id: str
    run_id: str | None = None
    node_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    final_result: Any = None
    session_result: AgentSessionResult | None = None

    @property
    def workflow_result(self) -> WorkflowResult | WorkflowInterruptedResult | None:
        """Return the terminal workflow result when one is attached."""

        if self.session_result is None:
            return None
        return self.session_result.workflow_result


@dataclass(frozen=True)
class AgentSessionState:
    """Copy-safe persistent state for one agent session."""

    session_id: str
    workflow_identity: str
    schema_version: int = AGENT_SESSION_STATE_SCHEMA_VERSION
    messages: tuple[OpenAIMessage, ...] = ()
    turn_count: int = 0
    last_run_id: str | None = None
    last_result: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.session_id:
            raise AgentSessionError("session state requires a non-empty session_id")
        if not self.workflow_identity:
            raise AgentSessionError(
                "session state requires a non-empty workflow_identity"
            )
        if self.schema_version != AGENT_SESSION_STATE_SCHEMA_VERSION:
            raise AgentSessionError(
                "unsupported session snapshot schema "
                f"{self.schema_version!r}; expected "
                f"{AGENT_SESSION_STATE_SCHEMA_VERSION}"
            )
        object.__setattr__(self, "messages", tuple(self.messages))
        object.__setattr__(self, "metadata", deepcopy(dict(self.metadata)))

    @classmethod
    def from_mapping(cls, snapshot: Any) -> AgentSessionState:
        """Build session state from a plain mapping snapshot."""

        if not isinstance(snapshot, dict):
            raise AgentSessionError("session snapshot must be a mapping")
        schema_version = snapshot.get(
            "schema_version", AGENT_SESSION_STATE_SCHEMA_VERSION
        )
        if schema_version != AGENT_SESSION_STATE_SCHEMA_VERSION:
            raise AgentSessionError(
                "unsupported session snapshot schema "
                f"{schema_version!r}; expected "
                f"{AGENT_SESSION_STATE_SCHEMA_VERSION}"
            )
        session_id = snapshot.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise AgentSessionError("session snapshot requires session_id")
        workflow_identity = snapshot.get("workflow_identity")
        if not isinstance(workflow_identity, str) or not workflow_identity:
            raise AgentSessionError("session snapshot requires workflow_identity")
        raw_messages = snapshot.get("messages", ())
        if not isinstance(raw_messages, list | tuple):
            raise AgentSessionError("session snapshot messages must be a sequence")
        return cls(
            session_id=session_id,
            workflow_identity=workflow_identity,
            schema_version=schema_version,
            messages=tuple(_message_from_snapshot(message) for message in raw_messages),
            turn_count=_optional_int(snapshot.get("turn_count"), "turn_count") or 0,
            last_run_id=_optional_str(snapshot.get("last_run_id"), "last_run_id"),
            last_result=deepcopy(snapshot.get("last_result")),
            metadata=deepcopy(snapshot.get("metadata") or {}),
        )

    def to_mapping(self) -> dict[str, Any]:
        """Return a copy-safe plain mapping snapshot."""

        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "workflow_identity": self.workflow_identity,
            "messages": [message.to_mapping() for message in self.messages],
            "turn_count": self.turn_count,
            "last_run_id": self.last_run_id,
            "last_result": deepcopy(self.last_result),
            "metadata": deepcopy(self.metadata),
        }


class InMemorySessionStore:
    """Process-local session store for v1 persistent agent sessions."""

    def __init__(self) -> None:
        self._states: dict[str, AgentSessionState] = {}
        self._lock = RLock()

    def save(self, state: AgentSessionState) -> None:
        """Save a copy of session state by session id."""

        with self._lock:
            self._states[state.session_id] = AgentSessionState.from_mapping(
                state.to_mapping()
            )

    def load(self, session_id: str) -> AgentSessionState:
        """Load a copy of session state by session id."""

        with self._lock:
            state = self._states.get(session_id)
            if state is None:
                raise AgentSessionError(f"session {session_id!r} was not found")
            return AgentSessionState.from_mapping(state.to_mapping())

    def contains(self, session_id: str) -> bool:
        """Return whether a session id is present in the store."""

        with self._lock:
            return session_id in self._states


class AgentSession:
    """Persistent session wrapper around a reusable execution context."""

    def __init__(
        self,
        *,
        execution_context: WorkflowExecutionContext,
        session_store: InMemorySessionStore,
        session_id: str,
    ) -> None:
        self.execution_context = execution_context
        self.session_store = session_store
        self.session_id = session_id
        self._accepting = False

    @classmethod
    def create(
        cls,
        *,
        execution_context: WorkflowExecutionContext,
        session_store: InMemorySessionStore,
        session_id: str | None = None,
    ) -> AgentSession:
        """Create a new session and initialize empty state when needed."""

        resolved_session_id = session_id or f"session-{uuid4().hex}"
        session = cls(
            execution_context=execution_context,
            session_store=session_store,
            session_id=resolved_session_id,
        )
        if not session_store.contains(resolved_session_id):
            session_store.save(
                AgentSessionState(
                    session_id=resolved_session_id,
                    workflow_identity=_workflow_identity(execution_context),
                )
            )
        return session

    @classmethod
    def from_snapshot(
        cls,
        snapshot: AgentSessionState | dict[str, Any],
        *,
        execution_context: WorkflowExecutionContext,
        session_store: InMemorySessionStore,
    ) -> AgentSession:
        """Restart a session from a saved state snapshot."""

        state = (
            snapshot
            if isinstance(snapshot, AgentSessionState)
            else AgentSessionState.from_mapping(snapshot)
        )
        workflow_identity = _workflow_identity(execution_context)
        if state.workflow_identity != workflow_identity:
            raise AgentSessionError(
                f"session snapshot workflow {state.workflow_identity!r} "
                f"does not match workflow {workflow_identity!r}"
            )
        session_store.save(state)
        return cls(
            execution_context=execution_context,
            session_store=session_store,
            session_id=state.session_id,
        )

    def current_state(self) -> AgentSessionState:
        """Return a copy-safe snapshot of the current session state."""

        return self.session_store.load(self.session_id)

    async def accept(self, prompt: str) -> AgentSessionResult:
        """Accept a prompt and execute it as one bounded workflow run."""

        if self._accepting:
            raise AgentSessionError(
                f"session {self.session_id!r} is already accepting a prompt"
            )
        self._accepting = True
        try:
            current = self.current_state()
            result = await execute_workflow_async(
                self.execution_context,
                prompt=prompt,
                session_messages=_messages_for_replay(
                    current.messages,
                    self.execution_context,
                ),
                initial_node_outputs=_initial_node_outputs(
                    self.session_id,
                    self.execution_context,
                ),
            )
            if isinstance(result, WorkflowInterruptedResult):
                return AgentSessionResult(workflow_result=result, state=current)

            updated = AgentSessionState(
                session_id=current.session_id,
                workflow_identity=current.workflow_identity,
                messages=(
                    *current.messages,
                    OpenAIMessage(role="user", content=prompt),
                    OpenAIMessage(
                        role="assistant",
                        content=_assistant_content(result.final_result),
                    ),
                ),
                turn_count=current.turn_count + 1,
                last_run_id=result.state.run_id,
                last_result=deepcopy(result.final_result),
                metadata=current.metadata,
            )
            self.session_store.save(updated)
            return AgentSessionResult(
                workflow_result=result,
                state=self.current_state(),
            )
        finally:
            self._accepting = False

    def accept_sync(self, prompt: str) -> AgentSessionResult:
        """Synchronously accept a prompt when no event loop is running."""

        return _run_async_from_sync(lambda: self.accept(prompt))

    async def accept_stream(
        self,
        prompt: str,
        *,
        include_progress_events: bool = True,
        include_terminal_event: bool = True,
        include_terminal_session_result: bool = True,
        progress_event_types: Iterable[str] | None = None,
    ) -> AsyncIterator[AgentSessionStreamEvent]:
        """Accept a prompt and stream redacted execution events."""

        if self._accepting:
            raise AgentSessionError(
                f"session {self.session_id!r} is already accepting a prompt"
            )
        self._accepting = True
        last_sequence = 0
        try:
            current = self.current_state()
            included_event_types = (
                frozenset(progress_event_types)
                if progress_event_types is not None
                else None
            )
            queue: asyncio.Queue[AgentSessionStreamEvent] = asyncio.Queue()
            execution_context = _execution_context_with_stream_sink(
                self.execution_context,
                _SessionStreamTraceSink(
                    queue=queue,
                    session_id=self.session_id,
                    downstream=self.execution_context.trace_sink,
                ),
            )
            task = asyncio.create_task(
                execute_workflow_async(
                    execution_context,
                    prompt=prompt,
                    session_messages=_messages_for_replay(
                        current.messages,
                        self.execution_context,
                    ),
                    initial_node_outputs=_initial_node_outputs(
                        self.session_id,
                        self.execution_context,
                    ),
                )
            )

            while not task.done():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.01)
                except TimeoutError:
                    continue
                last_sequence = event.sequence
                if _should_yield_progress_event(
                    event,
                    include_progress_events=include_progress_events,
                    included_event_types=included_event_types,
                ):
                    yield event

            result = await task
            while not queue.empty():
                event = queue.get_nowait()
                last_sequence = event.sequence
                if _should_yield_progress_event(
                    event,
                    include_progress_events=include_progress_events,
                    included_event_types=included_event_types,
                ):
                    yield event

            if isinstance(result, WorkflowInterruptedResult):
                if include_terminal_event:
                    session_result = (
                        AgentSessionResult(workflow_result=result, state=current)
                        if include_terminal_session_result
                        else None
                    )
                    yield AgentSessionStreamEvent(
                        sequence=last_sequence + 1,
                        event_type="approval_interrupted",
                        session_id=self.session_id,
                        run_id=result.state.run_id,
                        payload={"reason": result.interruption.reason},
                        session_result=session_result,
                    )
                return

            updated = AgentSessionState(
                session_id=current.session_id,
                workflow_identity=current.workflow_identity,
                messages=(
                    *current.messages,
                    OpenAIMessage(role="user", content=prompt),
                    OpenAIMessage(
                        role="assistant",
                        content=_assistant_content(result.final_result),
                    ),
                ),
                turn_count=current.turn_count + 1,
                last_run_id=result.state.run_id,
                last_result=deepcopy(result.final_result),
                metadata=current.metadata,
            )
            self.session_store.save(updated)
            if include_terminal_event:
                session_result = (
                    AgentSessionResult(
                        workflow_result=result,
                        state=self.current_state(),
                    )
                    if include_terminal_session_result
                    else None
                )
                yield AgentSessionStreamEvent(
                    sequence=last_sequence + 1,
                    event_type="run_completed",
                    session_id=self.session_id,
                    run_id=result.state.run_id,
                    final_result=deepcopy(result.final_result),
                    session_result=session_result,
                )
        finally:
            self._accepting = False


def _should_yield_progress_event(
    event: AgentSessionStreamEvent,
    *,
    include_progress_events: bool,
    included_event_types: frozenset[str] | None,
) -> bool:
    if not include_progress_events:
        return False
    if included_event_types is None:
        return True
    return event.event_type in included_event_types


def _workflow_identity(execution_context: WorkflowExecutionContext) -> str:
    manifest = execution_context.workflow.runtime_manifest
    package_id = manifest.package_id or "<anonymous>"
    entrypoint = manifest.entrypoint or "<no-entrypoint>"
    return f"{package_id}:{entrypoint}"


class _SessionStreamTraceSink:
    def __init__(
        self,
        *,
        queue: asyncio.Queue[AgentSessionStreamEvent],
        session_id: str,
        downstream: TraceSink | None,
    ) -> None:
        self._queue = queue
        self._session_id = session_id
        self._downstream = downstream

    def emit(self, event: TraceEvent) -> None:
        redacted = event.redacted()
        if self._downstream is not None:
            self._downstream.emit(redacted)
        self._queue.put_nowait(_stream_event_from_trace(redacted, self._session_id))


def _stream_event_from_trace(
    event: TraceEvent,
    session_id: str,
) -> AgentSessionStreamEvent:
    return AgentSessionStreamEvent(
        sequence=event.sequence,
        event_type=_stream_event_type(event.event_type),
        session_id=session_id,
        run_id=event.run_id,
        node_id=event.node_id,
        payload=dict(event.payload),
    )


def _stream_event_type(trace_event_type: str) -> str:
    if trace_event_type == "workflow_started":
        return "run_started"
    return trace_event_type


def _execution_context_with_stream_sink(
    execution_context: WorkflowExecutionContext,
    trace_sink: TraceSink,
) -> WorkflowExecutionContext:
    return WorkflowExecutionContext(
        workflow=execution_context.workflow,
        tool_registry=execution_context.tool_registry,
        guardrail_registry=execution_context.guardrail_registry,
        model_adapter=execution_context.model_adapter,
        max_steps=execution_context.max_steps,
        trace_sink=trace_sink,
        prompt_cache=execution_context.prompt_cache,
        lifecycle_hooks=execution_context.lifecycle_hooks,
        model_adapter_coverage=execution_context.model_adapter_coverage,
    )


def _assistant_content(final_result: Any) -> str:
    if isinstance(final_result, str):
        return final_result
    return str(final_result)


def _messages_for_replay(
    messages: tuple[OpenAIMessage, ...],
    execution_context: WorkflowExecutionContext,
) -> tuple[OpenAIMessage, ...]:
    policy = execution_context.workflow.runtime_manifest.async_session_policy
    history = policy.history if policy is not None else None
    if history == "none":
        return ()
    if history == "last_turn":
        return messages[-2:]
    if history == "summary":
        return ()
    return messages


def _initial_node_outputs(
    session_id: str,
    execution_context: WorkflowExecutionContext,
) -> dict[str, Any]:
    policy = execution_context.workflow.runtime_manifest.async_session_policy
    if policy is None or not policy.session_id_state_key:
        return {}
    return {policy.session_id_state_key: session_id}


def _message_from_snapshot(message: Any) -> OpenAIMessage:
    if isinstance(message, OpenAIMessage):
        return message
    if not isinstance(message, dict):
        raise AgentSessionError("session snapshot messages must be mappings")
    role = message.get("role")
    content = message.get("content")
    if not isinstance(role, str) or not role:
        raise AgentSessionError("session snapshot message requires role")
    if not isinstance(content, str):
        raise AgentSessionError("session snapshot message requires content")
    return OpenAIMessage(role=role, content=content)


def _optional_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int):
        raise AgentSessionError(f"session snapshot {field_name} must be an integer")
    return value


def _optional_str(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AgentSessionError(f"session snapshot {field_name} must be a string")
    return value
