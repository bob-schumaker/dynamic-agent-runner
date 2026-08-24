"""Human-reviewed, immutable MCP `tools/list` surface snapshots."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable, Mapping

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
    read_only_tool_names: frozenset[str]


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
        approved = frozenset(approved_read_only_tool_names)
        if not approved.issubset({item["name"] for item in discovered}):
            raise MCPSurfaceSnapshotError("approved read-only tool is unknown")
        if any(not isinstance(name, str) or not name for name in approved):
            raise MCPSurfaceSnapshotError("approved read-only tool is invalid")
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
                    "read_only_tool_names": sorted(approved),
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
            read_only_tool_names=approved,
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
            read_only_tool_names = frozenset(payload["read_only_tool_names"])
        except (OpaqueRecordError, KeyError, TypeError) as error:
            raise MCPSurfaceSnapshotError("surface snapshot is unavailable") from error
        _opaque_id(connection_id, "connection_id")
        _opaque_id(authentication_id, "authentication_id")
        _positive_generation(connection_generation)
        if not isinstance(tool_set_digest, str) or len(tool_set_digest) != 64:
            raise MCPSurfaceSnapshotError("surface snapshot is invalid")
        if any(not isinstance(name, str) or not name for name in read_only_tool_names):
            raise MCPSurfaceSnapshotError("surface snapshot is invalid")
        return MCPSurfaceSnapshot(
            snapshot_id=snapshot_id,
            connection_id=connection_id,
            authentication_id=authentication_id,
            connection_generation=connection_generation,
            tool_set_digest=tool_set_digest,
            read_only_tool_names=read_only_tool_names,
        )

    def require_read_only_tool(
        self, snapshot_id: str, tool_name: str
    ) -> MCPSurfaceSnapshot:
        """Return the snapshot only if one requested tool was explicitly approved."""

        snapshot = self.load(snapshot_id)
        if tool_name not in snapshot.read_only_tool_names:
            raise MCPSurfaceSnapshotError("tool is not approved for read-only use")
        return snapshot

    def verify_current(
        self, snapshot_id: str, current_tools: Iterable[MCPDiscoveredTool]
    ) -> MCPSurfaceSnapshot:
        """Fail closed if the current remote identity or input schemas drifted."""

        snapshot = self.load(snapshot_id)
        if _digest(_canonical_tools(current_tools)) != snapshot.tool_set_digest:
            raise MCPSurfaceSnapshotError("surface_changed")
        return snapshot


_TOOL_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


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
