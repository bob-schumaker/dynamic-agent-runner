"""Persistent agent session state and in-memory storage."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
from typing import Any
from uuid import uuid4

from dynamic_agent_runner.context import WorkflowExecutionContext
from dynamic_agent_runner.errors import AgentSessionError
from dynamic_agent_runner.openai_client import OpenAIMessage


AGENT_SESSION_STATE_SCHEMA_VERSION = 1


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

    def current_state(self) -> AgentSessionState:
        """Return a copy-safe snapshot of the current session state."""

        return self.session_store.load(self.session_id)


def _workflow_identity(execution_context: WorkflowExecutionContext) -> str:
    manifest = execution_context.workflow.runtime_manifest
    package_id = manifest.package_id or "<anonymous>"
    entrypoint = manifest.entrypoint or "<no-entrypoint>"
    return f"{package_id}:{entrypoint}"


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
