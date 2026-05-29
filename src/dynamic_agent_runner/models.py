"""Internal data models for generated dynamic-agent runtime artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
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

LEGACY_RUNTIME_ROOT_FIELDS = (
    "execution_policy",
    "state",
    "patterns_present",
    "participant_groups",
    "modes",
    "phases",
    "roles",
    "runtime_surface",
    "workspace_boundary",
    "completion_contract",
)


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


class ToolExposure(str, Enum):
    """How a tool may be exposed to models and direct workflow execution."""

    DIRECT = "direct"
    DEFERRED = "deferred"
    DIRECT_MODEL_ONLY = "direct_model_only"
    HIDDEN = "hidden"


@dataclass(frozen=True)
class ToolPolicy:
    """Lightweight tool policy metadata separated from callable registration."""

    side_effect: str | None = None
    approval_required: str | None = None
    sandbox: str | None = None
    timeout: str | None = None
    retry_policy: str | None = None
    failure_behavior: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ToolPolicy:
        """Build tool policy metadata from a manifest or tool-index mapping."""

        return cls(
            side_effect=_optional_str(value.get("side_effect")),
            approval_required=_optional_str(value.get("approval_required")),
            sandbox=_optional_str(value.get("sandbox")),
            timeout=_optional_str(value.get("timeout")),
            retry_policy=_optional_str(value.get("retry_policy")),
            failure_behavior=_optional_str(value.get("failure_behavior")),
        )


@dataclass(frozen=True)
class ModelCapabilities:
    """Lightweight model capability metadata preserved from execution policy."""

    context_window: int | None = None
    structured_output: bool | None = None
    reasoning: bool | None = None
    modalities: tuple[str, ...] = ()
    parallel_tool_calls: bool | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ModelCapabilities:
        """Build model capability metadata from a manifest mapping."""

        raw = dict(value)
        return cls(
            context_window=_optional_int(raw.get("context_window")),
            structured_output=_optional_bool(raw.get("structured_output")),
            reasoning=_optional_bool(raw.get("reasoning")),
            modalities=tuple(str(item) for item in _copy_list(raw.get("modalities"))),
            parallel_tool_calls=_optional_bool(raw.get("parallel_tool_calls")),
            raw=raw,
        )


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
    skill_refs: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> RuntimeNode:
        """Build a runtime node from a manifest mapping."""

        raw = dict(value)
        available_tools = tuple(
            str(item) for item in _copy_list(raw.get("available_tools"))
        )
        skill_refs = tuple(str(item) for item in _copy_list(raw.get("skill_refs")))
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
            skill_refs=skill_refs,
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
    exposure: ToolExposure | str = ToolExposure.DIRECT
    policy: ToolPolicy = field(default_factory=ToolPolicy)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ToolDefinition:
        """Build a tool definition from a manifest or tool-index mapping."""

        raw = dict(value)
        policy = ToolPolicy.from_mapping(raw)
        return cls(
            id=str(raw["id"]) if raw.get("id") is not None else None,
            label=str(raw["label"]) if raw.get("label") is not None else None,
            adapter=str(raw["adapter"]) if raw.get("adapter") is not None else None,
            side_effect=policy.side_effect,
            approval_required=policy.approval_required,
            exposure=_tool_exposure_from_value(raw.get("exposure")),
            policy=policy,
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
    runtime: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    extensions: Mapping[str, Any] = field(default_factory=dict)
    legacy_root_fields: tuple[str, ...] = ()
    patterns_present: tuple[str, ...] = ()
    execution_policy: Mapping[str, Any] = field(default_factory=dict)
    model_capabilities: ModelCapabilities | None = None
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
        runtime = _copy_mapping(_as_mapping(raw.get("runtime")))
        metadata = _copy_mapping(_as_mapping(raw.get("metadata")))
        extensions = _copy_mapping(_as_mapping(raw.get("extensions")))
        execution_policy = _copy_mapping(_as_mapping(runtime.get("execution_policy")))
        return cls(
            raw=raw,
            format_version=raw.get("format_version"),
            package_type=_optional_str(raw.get("package_type")),
            package_id=_optional_str(raw.get("package_id")),
            name=_optional_str(raw.get("name")),
            entrypoint=_optional_str(raw.get("entrypoint")),
            mermaid_diagram=_optional_str(raw.get("mermaid_diagram")),
            packaging=_copy_mapping(_as_mapping(raw.get("packaging"))),
            runtime=runtime,
            metadata=metadata,
            extensions=extensions,
            legacy_root_fields=tuple(
                field_name
                for field_name in LEGACY_RUNTIME_ROOT_FIELDS
                if field_name in raw
            ),
            patterns_present=tuple(
                str(pattern) for pattern in _copy_list(metadata.get("patterns_present"))
            ),
            execution_policy=execution_policy,
            model_capabilities=_model_capabilities_from_policy(execution_policy),
            state=_copy_mapping(_as_mapping(runtime.get("state"))),
            skills=tuple(_manifest_objects(raw.get("skills"))),
            tools=tuple(_tool_definitions(raw.get("tools"))),
            participant_groups=tuple(
                _manifest_objects(metadata.get("participant_groups"))
            ),
            modes=tuple(_manifest_objects(metadata.get("modes"))),
            phases=tuple(_manifest_objects(metadata.get("phases"))),
            roles=tuple(_manifest_objects(metadata.get("roles"))),
            nodes=tuple(_runtime_nodes(raw.get("nodes"))),
            edges=tuple(_runtime_edges(raw.get("edges"))),
            output_contracts=_output_contracts(raw.get("output_contracts")),
            validation=_copy_mapping(_as_mapping(raw.get("validation"))),
        )


@dataclass(frozen=True)
class PromptOverride:
    """Prompt patch operations for one runtime node."""

    replace: Mapping[str, Any] = field(default_factory=dict)
    prepend: Mapping[str, str] = field(default_factory=dict)
    append: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> PromptOverride:
        """Build prompt override operations from a mapping."""

        raw_replace = _copy_mapping(_as_mapping(value.get("replace")))
        raw_prepend = _copy_mapping(_as_mapping(value.get("prepend")))
        raw_append = _copy_mapping(_as_mapping(value.get("append")))
        return cls(
            replace=raw_replace,
            prepend={str(key): str(item) for key, item in raw_prepend.items()},
            append={str(key): str(item) for key, item in raw_append.items()},
        )


@dataclass(frozen=True)
class SkillReferenceOverride:
    """Per-node skill binding changes layered over node `skill_refs`."""

    add: tuple[str, ...] = ()
    remove: tuple[str, ...] = ()
    only: tuple[str, ...] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> SkillReferenceOverride:
        """Build skill-reference override operations from a mapping."""

        only_value = value.get("only")
        return cls(
            add=tuple(str(item) for item in _copy_list(value.get("add"))),
            remove=tuple(str(item) for item in _copy_list(value.get("remove"))),
            only=(
                tuple(str(item) for item in _copy_list(only_value))
                if only_value is not None
                else None
            ),
        )


@dataclass(frozen=True)
class NodeBehaviorOverride:
    """Runtime behavior override for a single `llm_step` node."""

    prompt: PromptOverride | None = None
    skill_refs: SkillReferenceOverride | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> NodeBehaviorOverride:
        """Build a per-node behavior override from a mapping."""

        prompt_value = value.get("prompt")
        skill_refs_value = value.get("skill_refs")
        return cls(
            prompt=(
                PromptOverride.from_mapping(prompt_value)
                if isinstance(prompt_value, Mapping)
                else None
            ),
            skill_refs=(
                SkillReferenceOverride.from_mapping(skill_refs_value)
                if isinstance(skill_refs_value, Mapping)
                else None
            ),
        )


@dataclass(frozen=True)
class RuntimeBehaviorOverrides:
    """Runtime prompt and skill override bundle."""

    raw: Mapping[str, Any] = field(default_factory=dict)
    format_version: Any = None
    override_type: str | None = None
    added_skills: tuple[ManifestObject, ...] = ()
    replacement_skills: tuple[ManifestObject, ...] = ()
    node_overrides: Mapping[str, NodeBehaviorOverride] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> RuntimeBehaviorOverrides:
        """Build runtime behavior overrides from parsed YAML data."""

        raw = dict(value)
        skills = _as_mapping(raw.get("skills")) or {}
        nodes = _as_mapping(raw.get("nodes")) or {}
        return cls(
            raw=raw,
            format_version=raw.get("format_version"),
            override_type=_optional_str(raw.get("override_type")),
            added_skills=tuple(_manifest_objects(skills.get("added"))),
            replacement_skills=tuple(_manifest_objects(skills.get("replacement"))),
            node_overrides={
                str(node_id): NodeBehaviorOverride.from_mapping(node_override)
                for node_id, node_override in nodes.items()
                if isinstance(node_override, Mapping)
            },
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
    runtime_overrides: RuntimeBehaviorOverrides | None = None


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _model_capabilities_from_policy(
    execution_policy: Mapping[str, Any],
) -> ModelCapabilities | None:
    value = execution_policy.get("model_capabilities")
    if not isinstance(value, Mapping):
        return None
    return ModelCapabilities.from_mapping(value)


def _tool_exposure_from_value(value: object) -> ToolExposure | str:
    if value is None:
        return ToolExposure.DIRECT
    try:
        return ToolExposure(str(value))
    except ValueError:
        return str(value)


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


def _output_contracts(value: object) -> dict[str, Any]:
    contracts: dict[str, Any] = {}
    for item in _mapping_items(value):
        contract_id = item.get("id") or item.get("name")
        if contract_id is not None:
            contracts[str(contract_id)] = dict(item)
    return contracts
