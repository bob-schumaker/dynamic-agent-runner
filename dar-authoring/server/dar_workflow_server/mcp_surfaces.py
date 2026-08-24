"""Human-reviewed, immutable MCP `tools/list` surface snapshots."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Iterable, Mapping, Protocol

from dar_workflow_server.connections import (
    MCPConnectionControlPlane,
    MCPConnectionError,
)
from dar_workflow_server.profiles import InstallationIdentityProvider
from dar_workflow_server.state import OpaqueRecordError, PrivateStateStore


class MCPSurfaceSnapshotError(ValueError):
    """Raised when a reviewed MCP surface is unavailable or has drifted."""


@dataclass(frozen=True)
class MCPDiscoveredTool:
    """The executable identity and schema from `tools/list`, without prose."""

    name: str
    input_schema: Mapping[str, object]


@dataclass(frozen=True)
class MCPSurfaceSnapshot:
    """One immutable reviewed remote tool surface bound to a client generation."""

    snapshot_id: str
    connection_id: str
    authentication_id: str
    connection_generation: int
    tool_set_digest: str
    tool_side_effects: Mapping[str, str]

    @property
    def read_only_tool_names(self) -> frozenset[str]:
        """Return the compatibility view for the currently executable G2 surface."""

        return frozenset(
            name
            for name, side_effect in self.tool_side_effects.items()
            if side_effect == "read"
        )


class CurrentMCPSurfaceClient(Protocol):
    """The current, initialized client identity required for surface binding."""

    connection_id: str
    authentication_id: str
    current_generation: int

    def list_tools(self) -> tuple[MCPDiscoveredTool, ...]:
        """Return the currently exposed remote tool surface."""


class MCPSurfaceSnapshotControlPlane:
    """Human-only review and passive drift boundary for remote MCP metadata."""

    def __init__(
        self, *, store: PrivateStateStore, connections: MCPConnectionControlPlane
    ) -> None:
        self._store = store
        self._connections = connections
        self._identity = InstallationIdentityProvider()

    def create(
        self,
        *,
        connection_id: str,
        authentication_id: str,
        connection_generation: int,
        tools: Iterable[MCPDiscoveredTool],
        approved_read_only_tool_names: Iterable[str],
        approved_tool_side_effects: Mapping[str, str] | None = None,
    ) -> MCPSurfaceSnapshot:
        """Persist the human-approved read-only subset of one discovered surface."""

        _positive_generation(connection_generation)
        try:
            self._connections.preflight(
                connection_id, authentication_id=authentication_id
            )
        except MCPConnectionError as error:
            raise MCPSurfaceSnapshotError("connection is unavailable") from error
        discovered = _canonical_tools(tools)
        approved = _approved_tool_side_effects(
            approved_read_only_tool_names, approved_tool_side_effects
        )
        if not set(approved).issubset({item["name"] for item in discovered}):
            raise MCPSurfaceSnapshotError("approved tool is unknown")
        digest = _digest(discovered)
        try:
            snapshot_id = self._store.issue(
                kind="mcp_surface_snapshot",
                owner=self._identity.principal,
                payload={
                    "connection_id": connection_id,
                    "authentication_id": authentication_id,
                    "connection_generation": connection_generation,
                    "tool_set_digest": digest,
                    "read_only_tool_names": sorted(
                        name
                        for name, side_effect in approved.items()
                        if side_effect == "read"
                    ),
                    "tool_side_effects": dict(approved),
                },
                expires_at=datetime.max.replace(tzinfo=UTC),
                now=datetime.now(UTC),
            )
        except OpaqueRecordError as error:
            raise MCPSurfaceSnapshotError(
                "surface snapshot could not be created"
            ) from error
        return MCPSurfaceSnapshot(
            snapshot_id=snapshot_id,
            connection_id=connection_id,
            authentication_id=authentication_id,
            connection_generation=connection_generation,
            tool_set_digest=digest,
            tool_side_effects=MappingProxyType(approved),
        )

    def load(self, snapshot_id: str) -> MCPSurfaceSnapshot:
        """Load an immutable snapshot owned by this local installation principal."""

        try:
            record = self._store.load(
                snapshot_id,
                expected_kind="mcp_surface_snapshot",
                owner=self._identity.principal,
                now=datetime.now(UTC),
            )
            payload = record.payload
            connection_id = payload["connection_id"]
            authentication_id = payload["authentication_id"]
            connection_generation = payload["connection_generation"]
            tool_set_digest = payload["tool_set_digest"]
            tool_side_effects = _loaded_tool_side_effects(payload)
        except (OpaqueRecordError, KeyError, TypeError) as error:
            raise MCPSurfaceSnapshotError("surface snapshot is unavailable") from error
        _opaque_id(connection_id, "connection_id")
        _opaque_id(authentication_id, "authentication_id")
        _positive_generation(connection_generation)
        if not isinstance(tool_set_digest, str) or len(tool_set_digest) != 64:
            raise MCPSurfaceSnapshotError("surface snapshot is invalid")
        return MCPSurfaceSnapshot(
            snapshot_id=snapshot_id,
            connection_id=connection_id,
            authentication_id=authentication_id,
            connection_generation=connection_generation,
            tool_set_digest=tool_set_digest,
            tool_side_effects=MappingProxyType(tool_side_effects),
        )

    def require_read_only_tool(
        self, snapshot_id: str, tool_name: str
    ) -> MCPSurfaceSnapshot:
        """Return the snapshot only if one requested tool was explicitly approved."""

        snapshot = self.load(snapshot_id)
        if snapshot.tool_side_effects.get(tool_name) != "read":
            raise MCPSurfaceSnapshotError("tool is not approved for read-only use")
        return snapshot

    def require_approved_tool(
        self, snapshot_id: str, tool_name: str, side_effect: str
    ) -> MCPSurfaceSnapshot:
        """Return the snapshot only for the exact human-reviewed effect class."""

        if side_effect not in _SIDE_EFFECT_CLASSES:
            raise MCPSurfaceSnapshotError("approved tool side effect is invalid")
        snapshot = self.load(snapshot_id)
        if snapshot.tool_side_effects.get(tool_name) != side_effect:
            raise MCPSurfaceSnapshotError("tool is not approved for this side effect")
        return snapshot

    def verify_current(
        self, snapshot_id: str, current_tools: Iterable[MCPDiscoveredTool]
    ) -> MCPSurfaceSnapshot:
        """Fail closed if the current remote identity or input schemas drifted."""

        snapshot = self.load(snapshot_id)
        if _digest(_canonical_tools(current_tools)) != snapshot.tool_set_digest:
            raise MCPSurfaceSnapshotError("surface_changed")
        return snapshot

    def verify_current_client(
        self, snapshot_id: str, client: CurrentMCPSurfaceClient
    ) -> MCPSurfaceSnapshot:
        """Verify that a live client is the reviewed authenticated generation."""

        snapshot, _ = self.verify_current_client_tools(snapshot_id, client)
        return snapshot

    def verify_current_client_tools(
        self, snapshot_id: str, client: CurrentMCPSurfaceClient
    ) -> tuple[MCPSurfaceSnapshot, tuple[MCPDiscoveredTool, ...]]:
        """Return one current reviewed client surface without a second lookup."""

        snapshot = self.load(snapshot_id)
        if (
            client.connection_id != snapshot.connection_id
            or client.authentication_id != snapshot.authentication_id
            or client.current_generation != snapshot.connection_generation
        ):
            raise MCPSurfaceSnapshotError("surface_changed")
        tools = client.list_tools()
        return self.verify_current(snapshot_id, tools), tools

    def verify_reconnected_client_tools(
        self, snapshot_id: str, client: CurrentMCPSurfaceClient
    ) -> tuple[MCPSurfaceSnapshot, tuple[MCPDiscoveredTool, ...]]:
        """Revalidate a reconnect against identity and full reviewed surface."""

        snapshot = self.load(snapshot_id)
        if (
            client.connection_id != snapshot.connection_id
            or client.authentication_id != snapshot.authentication_id
        ):
            raise MCPSurfaceSnapshotError("surface_changed")
        tools = client.list_tools()
        return self.verify_current(snapshot_id, tools), tools


_TOOL_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
_SIDE_EFFECT_CLASSES = frozenset({"read", "write", "delete"})


def _approved_tool_side_effects(
    read_only_names: Iterable[str], additional: Mapping[str, str] | None
) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in read_only_names:
        if not isinstance(name, str) or not name:
            raise MCPSurfaceSnapshotError("approved read-only tool is invalid")
        result[name] = "read"
    if additional is None:
        return result
    if not isinstance(additional, Mapping):
        raise MCPSurfaceSnapshotError("approved tool side effects are invalid")
    for name, side_effect in additional.items():
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(side_effect, str)
            or side_effect not in _SIDE_EFFECT_CLASSES
            or name in result
        ):
            raise MCPSurfaceSnapshotError("approved tool side effect is invalid")
        result[name] = side_effect
    return result


def _loaded_tool_side_effects(payload: Mapping[str, object]) -> dict[str, str]:
    value = payload.get("tool_side_effects")
    if value is None:
        value = dict.fromkeys(payload["read_only_tool_names"], "read")
    if not isinstance(value, Mapping):
        raise MCPSurfaceSnapshotError("surface snapshot is invalid")
    try:
        return _approved_tool_side_effects((), value)
    except MCPSurfaceSnapshotError as error:
        raise MCPSurfaceSnapshotError("surface snapshot is invalid") from error


def _canonical_tools(tools: Iterable[MCPDiscoveredTool]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    names: set[str] = set()
    for tool in tools:
        if not isinstance(tool, MCPDiscoveredTool):
            raise MCPSurfaceSnapshotError("discovered tool is invalid")
        if not isinstance(tool.name, str) or _TOOL_NAME.fullmatch(tool.name) is None:
            raise MCPSurfaceSnapshotError("discovered tool name is invalid")
        if tool.name in names:
            raise MCPSurfaceSnapshotError("discovered tool names must be unique")
        if not isinstance(tool.input_schema, Mapping):
            raise MCPSurfaceSnapshotError("discovered tool input schema is invalid")
        schema = _canonical_json(dict(tool.input_schema))
        names.add(tool.name)
        result.append({"name": tool.name, "input_schema": json.loads(schema)})
    if not result:
        raise MCPSurfaceSnapshotError("discovered tool surface is empty")
    return sorted(result, key=lambda item: str(item["name"]))


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise MCPSurfaceSnapshotError(
            "discovered tool input schema is invalid"
        ) from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _positive_generation(value: object) -> None:
    if not isinstance(value, int) or value <= 0:
        raise MCPSurfaceSnapshotError("connection generation is invalid")


def _opaque_id(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.startswith("v1."):
        raise MCPSurfaceSnapshotError(f"{name} must be an opaque identifier")
