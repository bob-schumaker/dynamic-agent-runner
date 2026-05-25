"""Internal data models for generated dynamic-agent runtime artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

SUPPORTED_AGENT_PATTERNS = (
    "basic-reasoning-agent",
    "tool-based-function-calling-agent",
    "tool-server-or-mcp-style-agent",
    "computer-use-agent",
    "coding-agent",
    "speech-or-voice-agent",
    "workflow-orchestration-agent",
    "memory-augmented-agent",
    "simulation-or-test-bed-agent",
    "observer-or-monitoring-agent",
    "multi-agent-collaboration",
)

PRIMITIVE_NODE_KINDS = ("llm_step", "tool_use_step", "decision_step")


def _copy_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a shallow dict copy for optional mapping fields."""

    return dict(value or {})


def _copy_list(value: object) -> list[Any]:
    """Return a shallow list copy for optional list fields."""

    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


@dataclass(frozen=True)
class ManifestObject:
    """Generic manifest object with a stable identifier and raw data."""

    id: str | None
    raw: Mapping[str, Any] = field(default_factory=dict)
    name: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ManifestObject:
        """Build a generic manifest object from a mapping."""

        raw = dict(value)
        identifier = raw.get("id")
        name = raw.get("name") or raw.get("label")
        return cls(
            id=str(identifier) if identifier is not None else None,
            name=str(name) if name is not None else None,
            raw=raw,
        )


@dataclass(frozen=True)
class RuntimeNode:
    """Runtime manifest node metadata preserved by the loader."""

    id: str | None
    kind: str | None
    raw: Mapping[str, Any] = field(default_factory=dict)
    label: str | None = None
    tool_id: str | None = None
    decision_subtype: str | None = None
    available_tools: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> RuntimeNode:
        """Build a runtime node from a manifest mapping."""

        raw = dict(value)
        available_tools = tuple(
            str(item) for item in _copy_list(raw.get("available_tools"))
        )
        return cls(
            id=str(raw["id"]) if raw.get("id") is not None else None,
            kind=str(raw["kind"]) if raw.get("kind") is not None else None,
            label=str(raw["label"]) if raw.get("label") is not None else None,
            tool_id=str(raw["tool_id"]) if raw.get("tool_id") is not None else None,
            decision_subtype=(
                str(raw["decision_subtype"])
                if raw.get("decision_subtype") is not None
                else None
            ),
            available_tools=available_tools,
            raw=raw,
        )


@dataclass(frozen=True)
class RuntimeEdge:
    """Runtime manifest edge metadata preserved by the loader."""

    source: str | None
    target: str | None
    edge_kind: str | None
    raw: Mapping[str, Any] = field(default_factory=dict)
    id: str | None = None
    condition: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> RuntimeEdge:
        """Build a runtime edge from a manifest mapping."""

        raw = dict(value)
        source = raw.get("source") or raw.get("from")
        target = raw.get("target") or raw.get("to")
        edge_kind = raw.get("edge_kind") or raw.get("kind")
        return cls(
            id=str(raw["id"]) if raw.get("id") is not None else None,
            source=str(source) if source is not None else None,
            target=str(target) if target is not None else None,
            edge_kind=str(edge_kind) if edge_kind is not None else None,
            condition=(
                str(raw["condition"]) if raw.get("condition") is not None else None
            ),
            raw=raw,
        )


@dataclass(frozen=True)
class ToolDefinition:
    """Tool metadata loaded from a runtime manifest or external tool index."""

    id: str | None
    raw: Mapping[str, Any] = field(default_factory=dict)
    label: str | None = None
    adapter: str | None = None
    side_effect: str | None = None
    approval_required: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ToolDefinition:
        """Build a tool definition from a manifest or tool-index mapping."""

        raw = dict(value)
        return cls(
            id=str(raw["id"]) if raw.get("id") is not None else None,
            label=str(raw["label"]) if raw.get("label") is not None else None,
            adapter=str(raw["adapter"]) if raw.get("adapter") is not None else None,
            side_effect=(
                str(raw["side_effect"]) if raw.get("side_effect") is not None else None
            ),
            approval_required=(
                str(raw["approval_required"])
                if raw.get("approval_required") is not None
                else None
            ),
            raw=raw,
        )


@dataclass(frozen=True)
class RuntimeManifest:
    """Loaded `agent-runtime.yaml` content for `format_version: 1`."""

    raw: Mapping[str, Any]
    format_version: Any = None
    package_type: str | None = None
    package_id: str | None = None
    name: str | None = None
    entrypoint: str | None = None
    mermaid_diagram: str | None = None
    packaging: Mapping[str, Any] = field(default_factory=dict)
    patterns_present: tuple[str, ...] = ()
    execution_policy: Mapping[str, Any] = field(default_factory=dict)
    state: Mapping[str, Any] = field(default_factory=dict)
    skills: tuple[ManifestObject, ...] = ()
    tools: tuple[ToolDefinition, ...] = ()
    participant_groups: tuple[ManifestObject, ...] = ()
    modes: tuple[ManifestObject, ...] = ()
    phases: tuple[ManifestObject, ...] = ()
    roles: tuple[ManifestObject, ...] = ()
    nodes: tuple[RuntimeNode, ...] = ()
    edges: tuple[RuntimeEdge, ...] = ()
    output_contracts: Mapping[str, Any] = field(default_factory=dict)
    validation: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> RuntimeManifest:
        """Build a runtime manifest while preserving structural metadata."""

        raw = dict(value)
        return cls(
            raw=raw,
            format_version=raw.get("format_version"),
            package_type=_optional_str(raw.get("package_type")),
            package_id=_optional_str(raw.get("package_id")),
            name=_optional_str(raw.get("name")),
            entrypoint=_optional_str(raw.get("entrypoint")),
            mermaid_diagram=_optional_str(raw.get("mermaid_diagram")),
            packaging=_copy_mapping(_as_mapping(raw.get("packaging"))),
            patterns_present=tuple(
                str(pattern) for pattern in _copy_list(raw.get("patterns_present"))
            ),
            execution_policy=_copy_mapping(_as_mapping(raw.get("execution_policy"))),
            state=_copy_mapping(_as_mapping(raw.get("state"))),
            skills=tuple(_manifest_objects(raw.get("skills"))),
            tools=tuple(_tool_definitions(raw.get("tools"))),
            participant_groups=tuple(_manifest_objects(raw.get("participant_groups"))),
            modes=tuple(_manifest_objects(raw.get("modes"))),
            phases=tuple(_manifest_objects(raw.get("phases"))),
            roles=tuple(_manifest_objects(raw.get("roles"))),
            nodes=tuple(_runtime_nodes(raw.get("nodes"))),
            edges=tuple(_runtime_edges(raw.get("edges"))),
            output_contracts=_copy_mapping(_as_mapping(raw.get("output_contracts"))),
            validation=_copy_mapping(_as_mapping(raw.get("validation"))),
        )


@dataclass(frozen=True)
class ToolIndex:
    """Loaded reusable `tool-index.yaml` catalog."""

    raw: Mapping[str, Any]
    format_version: Any = None
    index_type: str | None = None
    index_id: str | None = None
    name: str | None = None
    usage: Mapping[str, Any] = field(default_factory=dict)
    tools: tuple[ToolDefinition, ...] = ()
    skills: tuple[ManifestObject, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ToolIndex:
        """Build a reusable tool-index model from a mapping."""

        raw = dict(value)
        return cls(
            raw=raw,
            format_version=raw.get("format_version"),
            index_type=_optional_str(raw.get("index_type")),
            index_id=_optional_str(raw.get("index_id")),
            name=_optional_str(raw.get("name")),
            usage=_copy_mapping(_as_mapping(raw.get("usage"))),
            tools=tuple(_tool_definitions(raw.get("tools"))),
            skills=tuple(_manifest_objects(raw.get("skills"))),
        )


@dataclass(frozen=True)
class AgentDesign:
    """Loaded `agent-design.md` text and lightweight reference checks."""

    text: str
    references_runtime_manifest: bool = False
    references_mermaid_graph: bool = False

    @classmethod
    def from_text(cls, value: str) -> AgentDesign:
        """Build design metadata from markdown text."""

        lower_text = value.lower()
        return cls(
            text=value,
            references_runtime_manifest="agent-runtime.yaml" in lower_text,
            references_mermaid_graph="agent-graph.mmd" in lower_text,
        )


@dataclass(frozen=True)
class LoadedAgentWorkflow:
    """Artifact bundle loaded for later validation or execution slices."""

    runtime_manifest: RuntimeManifest
    mermaid_graph: str | None = None
    agent_design: AgentDesign | None = None
    tool_index: ToolIndex | None = None


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _as_mapping(value: object) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _mapping_items(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _manifest_objects(value: object) -> list[ManifestObject]:
    return [ManifestObject.from_mapping(item) for item in _mapping_items(value)]


def _runtime_nodes(value: object) -> list[RuntimeNode]:
    return [RuntimeNode.from_mapping(item) for item in _mapping_items(value)]


def _runtime_edges(value: object) -> list[RuntimeEdge]:
    return [RuntimeEdge.from_mapping(item) for item in _mapping_items(value)]


def _tool_definitions(value: object) -> list[ToolDefinition]:
    return [ToolDefinition.from_mapping(item) for item in _mapping_items(value)]
