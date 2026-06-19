"""In-memory collaborative parent/child agent session management."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class CollaborativeAgentPreset:
    """Configuration for one spawnable child agent role."""

    id: str
    role: str | None = None
    tool_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_ids", tuple(self.tool_ids))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class ChildAgentState:
    """Current state for one child agent session."""

    agent_id: str
    preset_id: str
    name: str
    role: str | None = None
    status: str = "idle"
    last_result: Any = None
    session_state: Any = None

    def to_mapping(self) -> dict[str, Any]:
        """Return a JSON-compatible child snapshot."""

        payload: dict[str, Any] = {
            "agent_id": self.agent_id,
            "preset_id": self.preset_id,
            "name": self.name,
            "status": self.status,
        }
        if self.role is not None:
            payload["role"] = self.role
        if self.last_result is not None:
            payload["last_result"] = self.last_result
        if self.session_state is not None:
            payload["session_state"] = self.session_state
        return payload

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ChildAgentState":
        """Restore child state from a snapshot mapping."""

        return cls(
            agent_id=str(value["agent_id"]),
            preset_id=str(value["preset_id"]),
            name=str(value.get("name") or value["agent_id"]),
            role=str(value["role"]) if value.get("role") is not None else None,
            status=str(value.get("status") or "idle"),
            last_result=value.get("last_result"),
            session_state=value.get("session_state"),
        )


@dataclass(frozen=True)
class CollaborativeAgentSessionState:
    """Snapshot for a parent collaboration manager."""

    parent_session_id: str
    children: tuple[ChildAgentState, ...] = ()

    def to_mapping(self) -> dict[str, Any]:
        """Return a JSON-compatible collaboration snapshot."""

        return {
            "parent_session_id": self.parent_session_id,
            "children": [child.to_mapping() for child in self.children],
        }

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
    ) -> "CollaborativeAgentSessionState":
        """Restore collaboration state from a snapshot mapping."""

        raw_children = value.get("children") or ()
        children = tuple(
            ChildAgentState.from_mapping(child)
            for child in raw_children
            if isinstance(child, Mapping)
        )
        return cls(parent_session_id=str(value["parent_session_id"]), children=children)


class CollaborativeAgentSessionManager:
    """Manage parent/child AgentSession-style collaboration in memory."""

    def __init__(
        self,
        *,
        parent_session_id: str,
        presets: Mapping[str, CollaborativeAgentPreset],
        session_factory: Callable[[str, CollaborativeAgentPreset], Any],
        initial_state: CollaborativeAgentSessionState | None = None,
    ) -> None:
        self.parent_session_id = parent_session_id
        self.presets = dict(presets)
        self.session_factory = session_factory
        self._children: dict[str, ChildAgentState] = {}
        self._sessions: dict[str, Any] = {}
        if initial_state is not None:
            self._children.update(
                (child.agent_id, child) for child in initial_state.children
            )

    @classmethod
    def from_snapshot(
        cls,
        snapshot: Mapping[str, Any] | CollaborativeAgentSessionState,
        *,
        presets: Mapping[str, CollaborativeAgentPreset],
        session_factory: Callable[[str, CollaborativeAgentPreset], Any],
    ) -> "CollaborativeAgentSessionManager":
        """Restart a manager from a saved collaboration snapshot."""

        state = (
            snapshot
            if isinstance(snapshot, CollaborativeAgentSessionState)
            else CollaborativeAgentSessionState.from_mapping(snapshot)
        )
        return cls(
            parent_session_id=state.parent_session_id,
            presets=presets,
            session_factory=session_factory,
            initial_state=state,
        )

    def spawn_agent(
        self,
        *,
        preset_id: str,
        name: str,
        role: str | None = None,
        prompt: str | None = None,
    ) -> ChildAgentState:
        """Create a child session record without starting background work."""

        del prompt
        preset = self.presets.get(preset_id)
        if preset is None:
            return ChildAgentState(
                agent_id="",
                preset_id=preset_id,
                name=name,
                role=role,
                status="not_found",
            )
        agent_id = f"agent-{uuid4()}"
        child = ChildAgentState(
            agent_id=agent_id,
            preset_id=preset_id,
            name=name,
            role=role or preset.role,
            status="idle",
            session_state=None,
        )
        self._children[agent_id] = child
        self._sessions[agent_id] = self.session_factory(agent_id, preset)
        return child

    def list_agents(self) -> tuple[ChildAgentState, ...]:
        """List child agents in deterministic creation order."""

        return tuple(self._children.values())

    def get_agent_state(self, agent_id: str) -> ChildAgentState:
        """Return current state for one child agent."""

        return self._children.get(
            agent_id,
            ChildAgentState(
                agent_id=agent_id,
                preset_id="",
                name=agent_id,
                status="not_found",
            ),
        )

    async def send_input(self, agent_id: str, prompt: str) -> Any:
        """Send a prompt to an existing child session."""

        child = self.get_agent_state(agent_id)
        if child.status in {"not_found", "closed"}:
            return {"status": child.status, "agent_id": agent_id}
        preset = self.presets[child.preset_id]
        session = self._sessions.get(agent_id)
        if session is None:
            session = self.session_factory(agent_id, preset)
            self._sessions[agent_id] = session
        self._children[agent_id] = _replace_child(child, status="running")
        try:
            result = await session.accept(prompt)
            session_state = (
                session.current_state() if hasattr(session, "current_state") else None
            )
            self._children[agent_id] = _replace_child(
                child,
                status="idle",
                last_result=result,
                session_state=session_state,
            )
            return result
        except Exception as exc:  # noqa: BLE001 - preserve child failure as state.
            self._children[agent_id] = _replace_child(
                child,
                status="errored",
                last_result={"error": str(exc)},
            )
            raise

    def close_agent(self, agent_id: str) -> ChildAgentState:
        """Close a child agent and reject future prompts."""

        child = self.get_agent_state(agent_id)
        closed = _replace_child(child, status="closed")
        self._children[agent_id] = closed
        self._sessions.pop(agent_id, None)
        return closed

    def current_state(self) -> CollaborativeAgentSessionState:
        """Return current collaboration state."""

        return CollaborativeAgentSessionState(
            parent_session_id=self.parent_session_id,
            children=tuple(self._children.values()),
        )


def _replace_child(child: ChildAgentState, **changes: Any) -> ChildAgentState:
    values = {
        "agent_id": child.agent_id,
        "preset_id": child.preset_id,
        "name": child.name,
        "role": child.role,
        "status": child.status,
        "last_result": child.last_result,
        "session_state": child.session_state,
    }
    values.update(changes)
    return ChildAgentState(**values)


__all__ = [
    "ChildAgentState",
    "CollaborativeAgentPreset",
    "CollaborativeAgentSessionManager",
    "CollaborativeAgentSessionState",
]
