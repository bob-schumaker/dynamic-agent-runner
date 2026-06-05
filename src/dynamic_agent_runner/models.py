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


class ToolType(str, Enum):
    """Portable semantic capability category for a tool."""

    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    WEB_SEARCH = "web_search"
    WEB_FETCH = "web_fetch"
    SHELL_COMMAND = "shell_command"
    CODE_EXECUTION = "code_execution"
    STRUCTURED_DATA_QUERY = "structured_data_query"
    EXTERNAL_API = "external_api"
    AGENT_TOOL = "agent_tool"
    HUMAN_APPROVAL = "human_approval"


class ToolSourceKind(str, Enum):
    """Where a tool definition originated before runtime dispatch."""

    MANIFEST = "manifest"
    TOOL_INDEX = "tool_index"
    BUILT_IN = "built_in"
    RUNTIME_OVERRIDE = "runtime_override"
    CALLER_REGISTERED = "caller_registered"


class ToolOriginKind(str, Enum):
    """Higher-level provenance bucket for runtime and future tool sources."""

    REGISTERED = "registered"
    BUILT_IN = "built_in"
    OVERRIDE = "override"
    MCP = "mcp"
    AGENT_AS_TOOL = "agent_as_tool"


@dataclass(frozen=True)
class ToolSource:
    """Diagnostic provenance for a tool definition."""

    kind: ToolSourceKind
    origin: ToolOriginKind | None = None
    source_id: str | None = None
    detail: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ToolSource:
        """Build tool provenance metadata from a mapping."""

        raw_kind = value.get("kind") or value.get("source_kind")
        try:
            kind = ToolSourceKind(str(raw_kind))
        except ValueError:
            kind = ToolSourceKind.CALLER_REGISTERED
        raw_origin = value.get("origin") or value.get("origin_kind")
        origin = _tool_origin_from_value(raw_origin) or _default_tool_origin(kind)
        return cls(
            kind=kind,
            origin=origin,
            source_id=_optional_str(value.get("source_id")),
            detail=_optional_str(value.get("detail")),
        )

    def to_mapping(self) -> dict[str, Any]:
        """Return JSON-serializable provenance metadata."""

        payload: dict[str, Any] = {"kind": self.kind.value}
        if self.origin is not None:
            payload["origin"] = self.origin.value
        if self.source_id is not None:
            payload["source_id"] = self.source_id
        if self.detail is not None:
            payload["detail"] = self.detail
        return payload


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
    embeddings: bool | None = None
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
            embeddings=_optional_bool(raw.get("embeddings")),
            modalities=tuple(str(item) for item in _copy_list(raw.get("modalities"))),
            parallel_tool_calls=_optional_bool(raw.get("parallel_tool_calls")),
            raw=raw,
        )


@dataclass(frozen=True)
class GuardrailDeclaration:
    """Deferred guardrail metadata preserved from the runtime manifest."""

    id: str | None
    phase: str | None = None
    behavior_on_tripwire: str | None = None
    message: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> GuardrailDeclaration:
        """Build a guardrail declaration from a manifest mapping."""

        raw = dict(value)
        return cls(
            id=_optional_str(raw.get("id")),
            phase=_optional_str(raw.get("phase")),
            behavior_on_tripwire=_optional_str(raw.get("behavior_on_tripwire")),
            message=_optional_str(
                raw.get("message") or raw.get("reject_content_message")
            ),
            raw=raw,
        )


@dataclass(frozen=True)
class MCPRegistrySource:
    """Deferred MCP registry-source metadata preserved from manifest extensions."""

    id: str | None
    server: str | None = None
    status: str | None = None
    tool_cache: str | None = None
    disabled: bool | None = None
    operation_locking: str | None = None
    memory_pollution: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> MCPRegistrySource:
        """Build MCP registry-source metadata from a manifest mapping."""

        raw = dict(value)
        return cls(
            id=_optional_str(raw.get("id")),
            server=_optional_str(raw.get("server")),
            status=_optional_str(raw.get("status")),
            tool_cache=_optional_str(raw.get("tool_cache")),
            disabled=_optional_bool(raw.get("disabled")),
            operation_locking=_optional_str(raw.get("operation_locking")),
            memory_pollution=_optional_str(raw.get("memory_pollution")),
            raw=raw,
        )


@dataclass(frozen=True)
class MCPLifecycleDiagnostics:
    """Deferred MCP lifecycle diagnostics metadata preserved from extensions."""

    startup_mode: str | None = None
    reconnect: str | None = None
    cleanup_timeout: str | None = None
    active_servers_state_key: str | None = None
    failed_servers_state_key: str | None = None
    error_map_state_key: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> MCPLifecycleDiagnostics:
        """Build MCP lifecycle diagnostics metadata from a manifest mapping."""

        raw = dict(value)
        return cls(
            startup_mode=_optional_str(raw.get("startup_mode")),
            reconnect=_optional_str(raw.get("reconnect")),
            cleanup_timeout=_optional_str(raw.get("cleanup_timeout")),
            active_servers_state_key=_optional_str(raw.get("active_servers_state_key")),
            failed_servers_state_key=_optional_str(raw.get("failed_servers_state_key")),
            error_map_state_key=_optional_str(raw.get("error_map_state_key")),
            raw=raw,
        )


@dataclass(frozen=True)
class ToolUseCompletionPolicy:
    """Deferred tool-use completion policy metadata for future loop runtimes."""

    run_again: str | None = None
    stop_on_tool: str | None = None
    final_output: str | None = None
    final_output_state_key: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ToolUseCompletionPolicy:
        """Build tool-use completion policy metadata from execution policy."""

        raw = dict(value)
        return cls(
            run_again=_optional_str(raw.get("run_again")),
            stop_on_tool=_optional_str(raw.get("stop_on_tool")),
            final_output=_optional_str(raw.get("final_output")),
            final_output_state_key=_optional_str(raw.get("final_output_state_key")),
            raw=raw,
        )


@dataclass(frozen=True)
class ApprovalInterruptionPolicy:
    """Deferred approval interruption metadata for future pause/resume runtimes."""

    mode: str | None = None
    persist: str | None = None
    resume_from: str | None = None
    pending_tool_calls_state_key: str | None = None
    pending_approvals_state_key: str | None = None
    interruption_state_key: str | None = None
    resume_token_state_key: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ApprovalInterruptionPolicy:
        """Build approval interruption policy metadata from execution policy."""

        raw = dict(value)
        return cls(
            mode=_optional_str(raw.get("mode")),
            persist=_optional_str(raw.get("persist")),
            resume_from=_optional_str(raw.get("resume_from")),
            pending_tool_calls_state_key=_optional_str(
                raw.get("pending_tool_calls_state_key")
            ),
            pending_approvals_state_key=_optional_str(
                raw.get("pending_approvals_state_key")
            ),
            interruption_state_key=_optional_str(raw.get("interruption_state_key")),
            resume_token_state_key=_optional_str(raw.get("resume_token_state_key")),
            raw=raw,
        )


@dataclass(frozen=True)
class AsyncSessionPolicy:
    """Deferred async session metadata for future multi-turn runtimes."""

    mode: str | None = None
    persist: str | None = None
    history: str | None = None
    session_id_state_key: str | None = None
    session_messages_state_key: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> AsyncSessionPolicy:
        """Build async session policy metadata from execution policy."""

        raw = dict(value)
        return cls(
            mode=_optional_str(raw.get("mode")),
            persist=_optional_str(raw.get("persist")),
            history=_optional_str(raw.get("history")),
            session_id_state_key=_optional_str(raw.get("session_id_state_key")),
            session_messages_state_key=_optional_str(
                raw.get("session_messages_state_key")
            ),
            raw=raw,
        )


@dataclass(frozen=True)
class SandboxRuntimePolicy:
    """Deferred sandbox/workspace runtime metadata for future write-command runtimes."""

    mode: str | None = None
    filesystem: str | None = None
    persist_workspace: str | None = None
    command_policy: str | None = None
    writable_root_state_key: str | None = None
    working_directory_state_key: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> SandboxRuntimePolicy:
        """Build sandbox runtime policy metadata from execution policy."""

        raw = dict(value)
        return cls(
            mode=_optional_str(raw.get("mode")),
            filesystem=_optional_str(raw.get("filesystem")),
            persist_workspace=_optional_str(raw.get("persist_workspace")),
            command_policy=_optional_str(raw.get("command_policy")),
            writable_root_state_key=_optional_str(raw.get("writable_root_state_key")),
            working_directory_state_key=_optional_str(
                raw.get("working_directory_state_key")
            ),
            raw=raw,
        )


@dataclass(frozen=True)
class HandoffMetadata:
    """Deferred handoff metadata for future active-agent transfer workflows."""

    id: str | None
    target: str | None = None
    on_handoff: str | None = None
    input_filter: str | None = None
    nested_history: str | None = None
    enabled_when: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> HandoffMetadata:
        """Build handoff metadata from grouped manifest metadata."""

        raw = dict(value)
        return cls(
            id=_optional_str(raw.get("id")),
            target=_optional_str(raw.get("target") or raw.get("target_agent")),
            on_handoff=_optional_str(raw.get("on_handoff")),
            input_filter=_optional_str(raw.get("input_filter")),
            nested_history=_optional_str(raw.get("nested_history")),
            enabled_when=_optional_str(raw.get("enabled_when")),
            raw=raw,
        )


@dataclass(frozen=True)
class AgentAsToolMetadata:
    """Deferred bounded delegation metadata for agent-as-tool nodes."""

    skill_id: str | None = None
    skill_path: str | None = None
    task_boundary: str | None = None
    output_mode: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> AgentAsToolMetadata:
        """Build agent-as-tool metadata from node-local manifest metadata."""

        raw = dict(value)
        return cls(
            skill_id=_optional_str(raw.get("skill_id")),
            skill_path=_optional_str(raw.get("skill_path")),
            task_boundary=_optional_str(raw.get("task_boundary") or raw.get("task")),
            output_mode=_optional_str(raw.get("output_mode")),
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
    agent_as_tool: AgentAsToolMetadata | None = None
    model_requirements: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> RuntimeNode:
        """Build a runtime node from a manifest mapping."""

        raw = dict(value)
        available_tools = tuple(
            str(item) for item in _copy_list(raw.get("available_tools"))
        )
        skill_refs = tuple(str(item) for item in _copy_list(raw.get("skill_refs")))
        agent_as_tool = _as_mapping(raw.get("agent_as_tool") or raw.get("agent_tool"))
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
            agent_as_tool=(
                AgentAsToolMetadata.from_mapping(agent_as_tool)
                if agent_as_tool is not None
                else None
            ),
            model_requirements=_copy_mapping(
                _as_mapping(raw.get("model_requirements"))
            ),
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
    tool_type: ToolType | str | None = None
    adapter: str | None = None
    side_effect: str | None = None
    approval_required: str | None = None
    exposure: ToolExposure | str = ToolExposure.DIRECT
    policy: ToolPolicy = field(default_factory=ToolPolicy)
    source: ToolSource | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ToolDefinition:
        """Build a tool definition from a manifest or tool-index mapping."""

        raw = dict(value)
        policy = ToolPolicy.from_mapping(raw)
        source = _tool_source_from_raw(raw)
        return cls(
            id=str(raw["id"]) if raw.get("id") is not None else None,
            label=str(raw["label"]) if raw.get("label") is not None else None,
            tool_type=_tool_type_from_value(raw.get("tool_type")),
            adapter=str(raw["adapter"]) if raw.get("adapter") is not None else None,
            side_effect=policy.side_effect,
            approval_required=policy.approval_required,
            exposure=_tool_exposure_from_value(raw.get("exposure")),
            policy=policy,
            source=source,
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
    rag_pipeline: Mapping[str, Any] = field(default_factory=dict)
    legacy_root_fields: tuple[str, ...] = ()
    patterns_present: tuple[str, ...] = ()
    execution_policy: Mapping[str, Any] = field(default_factory=dict)
    model_capabilities: ModelCapabilities | None = None
    guardrails: tuple[GuardrailDeclaration, ...] = ()
    mcp_registry_sources: tuple[MCPRegistrySource, ...] = ()
    mcp_lifecycle_diagnostics: MCPLifecycleDiagnostics | None = None
    tool_use_completion_policy: ToolUseCompletionPolicy | None = None
    approval_interruption_policy: ApprovalInterruptionPolicy | None = None
    async_session_policy: AsyncSessionPolicy | None = None
    sandbox_runtime_policy: SandboxRuntimePolicy | None = None
    handoffs: tuple[HandoffMetadata, ...] = ()
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
        guardrails = _guardrail_declarations(extensions)
        mcp_registry_sources = _mcp_registry_sources(extensions)
        mcp_lifecycle_diagnostics = _mcp_lifecycle_diagnostics(extensions)
        tool_use_completion = _as_mapping(execution_policy.get("tool_use_completion"))
        approval_interruption = _as_mapping(
            execution_policy.get("approval_interruption")
        )
        async_session = _as_mapping(execution_policy.get("async_session"))
        sandbox_runtime = _as_mapping(execution_policy.get("sandbox_runtime"))
        handoffs = _handoff_metadata(metadata)
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
            rag_pipeline=_copy_mapping(_as_mapping(metadata.get("rag_pipeline"))),
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
            guardrails=guardrails,
            mcp_registry_sources=mcp_registry_sources,
            mcp_lifecycle_diagnostics=mcp_lifecycle_diagnostics,
            tool_use_completion_policy=(
                ToolUseCompletionPolicy.from_mapping(tool_use_completion)
                if tool_use_completion is not None
                else None
            ),
            approval_interruption_policy=(
                ApprovalInterruptionPolicy.from_mapping(approval_interruption)
                if approval_interruption is not None
                else None
            ),
            async_session_policy=(
                AsyncSessionPolicy.from_mapping(async_session)
                if async_session is not None
                else None
            ),
            sandbox_runtime_policy=(
                SandboxRuntimePolicy.from_mapping(sandbox_runtime)
                if sandbox_runtime is not None
                else None
            ),
            handoffs=handoffs,
            state=_copy_mapping(_as_mapping(runtime.get("state"))),
            skills=tuple(_manifest_objects(raw.get("skills"))),
            tools=tuple(
                _tool_definitions(
                    raw.get("tools"),
                    source=ToolSource(
                        kind=ToolSourceKind.MANIFEST,
                        origin=ToolOriginKind.REGISTERED,
                        source_id=_optional_str(raw.get("package_id")),
                        detail="tools",
                    ),
                )
            ),
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
            tools=tuple(
                _tool_definitions(
                    raw.get("tools"),
                    source=ToolSource(
                        kind=ToolSourceKind.TOOL_INDEX,
                        origin=ToolOriginKind.REGISTERED,
                        source_id=_optional_str(raw.get("index_id")),
                        detail="tools",
                    ),
                )
            ),
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
    package_root: str | None = None
    skill_bundle_root: str | None = None
    mermaid_graph: str | None = None
    agent_design: AgentDesign | None = None
    tool_index: ToolIndex | None = None
    runtime_overrides: RuntimeBehaviorOverrides | None = None


@dataclass(frozen=True)
class CompiledAgentWorkflow:
    """Execution-ready workflow view compiled from a base bundle plus overrides."""

    base_workflow: LoadedAgentWorkflow
    runtime_manifest: RuntimeManifest
    package_root: str | None = None
    skill_bundle_root: str | None = None
    mermaid_graph: str | None = None
    agent_design: AgentDesign | None = None
    tool_index: ToolIndex | None = None
    runtime_overrides: RuntimeBehaviorOverrides | None = None


@dataclass(frozen=True)
class PreparedNode:
    """Execution-ready node data derived once from a runtime node."""

    source_node: RuntimeNode
    id: str
    kind: str
    label: str | None = None
    tool_id: str | None = None
    decision_subtype: str | None = None
    available_tools: tuple[str, ...] = ()
    skill_refs: tuple[str, ...] = ()
    agent_as_tool: AgentAsToolMetadata | None = None
    model: str | None = None
    model_parameters: Mapping[str, Any] = field(default_factory=dict)
    model_requirements: Mapping[str, Any] = field(default_factory=dict)
    tool_choice: Any = None
    response_format: Mapping[str, Any] | None = None
    inputs: Mapping[str, Any] = field(default_factory=dict)
    inputs_from: Any = None
    outputs: Mapping[str, Any] = field(default_factory=dict)
    route_from: Any = "last"
    allowed_routes: frozenset[str] = frozenset()
    output_schema_ref: str | None = None
    failure_behavior: str = "error"
    retry_policy: Any = None
    token_budget_policy: Any = None
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionPlan:
    """Prepared workflow control-flow and node lookup data."""

    workflow: LoadedAgentWorkflow | CompiledAgentWorkflow
    entrypoint_id: str | None
    nodes_by_id: Mapping[str, PreparedNode] = field(default_factory=dict)
    edges_by_source: Mapping[str, tuple[RuntimeEdge, ...]] = field(default_factory=dict)
    execution_policy: Mapping[str, Any] = field(default_factory=dict)
    tool_use_completion_policy: ToolUseCompletionPolicy | None = None
    approval_interruption_policy: ApprovalInterruptionPolicy | None = None
    async_session_policy: AsyncSessionPolicy | None = None
    sandbox_runtime_policy: SandboxRuntimePolicy | None = None
    handoffs: tuple[HandoffMetadata, ...] = ()
    output_contracts: Mapping[str, Any] = field(default_factory=dict)
    unsupported_extensions: tuple[str, ...] = ()
    max_steps: int | None = None


def prepare_execution_plan(
    workflow: LoadedAgentWorkflow | CompiledAgentWorkflow,
) -> ExecutionPlan:
    """Resolve execution indexes and node defaults once before a run."""

    manifest = workflow.runtime_manifest
    execution_policy = dict(manifest.execution_policy)
    return ExecutionPlan(
        workflow=workflow,
        entrypoint_id=manifest.entrypoint,
        nodes_by_id={
            prepared_node.id: prepared_node
            for prepared_node in (
                _prepare_node(node, execution_policy) for node in manifest.nodes
            )
            if prepared_node.id
        },
        edges_by_source=_edges_by_source(manifest.edges),
        execution_policy=execution_policy,
        tool_use_completion_policy=manifest.tool_use_completion_policy,
        approval_interruption_policy=manifest.approval_interruption_policy,
        async_session_policy=manifest.async_session_policy,
        sandbox_runtime_policy=manifest.sandbox_runtime_policy,
        handoffs=manifest.handoffs,
        output_contracts=dict(manifest.output_contracts),
        unsupported_extensions=tuple(
            str(extension_id)
            for extension_id, extension in manifest.extensions.items()
            if isinstance(extension, Mapping)
            and extension.get("required", False) is False
        ),
        max_steps=_max_steps(execution_policy),
    )


def _prepare_node(
    node: RuntimeNode,
    execution_policy: Mapping[str, Any],
) -> PreparedNode:
    raw = dict(node.raw)
    prompt = _as_mapping(raw.get("prompt")) or {}
    return PreparedNode(
        source_node=node,
        id=str(node.id or ""),
        kind=str(node.kind or ""),
        label=node.label,
        tool_id=node.tool_id,
        decision_subtype=node.decision_subtype,
        available_tools=node.available_tools,
        skill_refs=node.skill_refs,
        agent_as_tool=node.agent_as_tool,
        model=_prepared_model(raw, execution_policy),
        model_parameters=_copy_mapping(_as_mapping(raw.get("model_parameters"))),
        model_requirements=_copy_mapping(_as_mapping(raw.get("model_requirements"))),
        tool_choice=raw.get("tool_choice"),
        response_format=_as_mapping(raw.get("response_format")),
        inputs=_copy_mapping(_as_mapping(raw.get("inputs"))),
        inputs_from=raw.get("inputs_from"),
        outputs=_copy_mapping(_as_mapping(raw.get("outputs"))),
        route_from=raw.get("route_from") or "last",
        allowed_routes=frozenset(_allowed_routes(raw)),
        output_schema_ref=_prepared_output_schema_ref(raw, prompt),
        failure_behavior=str(raw.get("failure_behavior") or "error"),
        retry_policy=raw.get("retry_policy"),
        token_budget_policy=raw.get("token_budget") or raw.get("token_budget_policy"),
        raw=raw,
    )


def _prepared_model(
    node_raw: Mapping[str, Any],
    execution_policy: Mapping[str, Any],
) -> str | None:
    value = node_raw.get("model") or execution_policy.get("model")
    if value is None:
        value = execution_policy.get("default_model")
    return str(value) if value is not None else None


def _prepared_output_schema_ref(
    node_raw: Mapping[str, Any],
    prompt: Mapping[str, Any],
) -> str | None:
    value = node_raw.get("output_schema_ref") or prompt.get("output_schema_ref")
    return str(value) if value is not None else None


def _allowed_routes(node_raw: Mapping[str, Any]) -> set[str]:
    contract = node_raw.get("decision_contract")
    if not isinstance(contract, Mapping):
        return set()
    paths = contract.get("allowed_paths")
    if isinstance(paths, Mapping):
        return {str(key) for key in paths}
    if isinstance(paths, list):
        routes: set[str] = set()
        for path in paths:
            if isinstance(path, Mapping):
                value = path.get("id") or path.get("route") or path.get("condition")
            else:
                value = path
            if value is not None:
                routes.add(str(value))
        return routes
    return set()


def _edges_by_source(
    edges: tuple[RuntimeEdge, ...],
) -> dict[str, tuple[RuntimeEdge, ...]]:
    grouped: dict[str, list[RuntimeEdge]] = {}
    for edge in edges:
        if edge.source is None:
            continue
        grouped.setdefault(edge.source, []).append(edge)
    return {source: tuple(values) for source, values in grouped.items()}


def _max_steps(execution_policy: Mapping[str, Any]) -> int | None:
    value = execution_policy.get("max_steps") or execution_policy.get("maximum_steps")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


def _tool_type_from_value(value: object) -> ToolType | str | None:
    if value is None:
        return None
    try:
        return ToolType(str(value))
    except ValueError:
        return str(value)


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


def _tool_definitions(
    value: object,
    *,
    source: ToolSource | None = None,
) -> list[ToolDefinition]:
    return [
        _tool_definition_with_source(ToolDefinition.from_mapping(item), source)
        for item in _mapping_items(value)
    ]


def _tool_definition_with_source(
    definition: ToolDefinition,
    source: ToolSource | None,
) -> ToolDefinition:
    if source is None or definition.source is not None:
        return definition
    return ToolDefinition(
        id=definition.id,
        raw=definition.raw,
        label=definition.label,
        tool_type=definition.tool_type,
        adapter=definition.adapter,
        side_effect=definition.side_effect,
        approval_required=definition.approval_required,
        exposure=definition.exposure,
        policy=definition.policy,
        source=source,
    )


def _tool_source_from_raw(raw: Mapping[str, Any]) -> ToolSource | None:
    value = raw.get("source") or raw.get("origin")
    if isinstance(value, Mapping):
        return ToolSource.from_mapping(value)
    raw_kind = raw.get("source_kind") or raw.get("origin_kind")
    raw_origin = raw.get("tool_origin") or raw.get("provenance_origin")
    if raw_kind is None and raw_origin is None:
        return None
    return ToolSource.from_mapping(
        {
            "kind": raw_kind,
            "origin": raw_origin,
            "source_id": raw.get("source_id") or raw.get("origin_id"),
            "detail": raw.get("source_detail") or raw.get("origin_detail"),
        }
    )


def _tool_origin_from_value(value: object) -> ToolOriginKind | None:
    if value is None:
        return None
    try:
        return ToolOriginKind(str(value))
    except ValueError:
        return None


def _default_tool_origin(kind: ToolSourceKind) -> ToolOriginKind:
    if kind is ToolSourceKind.BUILT_IN:
        return ToolOriginKind.BUILT_IN
    if kind is ToolSourceKind.RUNTIME_OVERRIDE:
        return ToolOriginKind.OVERRIDE
    return ToolOriginKind.REGISTERED


def _output_contracts(value: object) -> dict[str, Any]:
    contracts: dict[str, Any] = {}
    for item in _mapping_items(value):
        contract_id = item.get("id") or item.get("name")
        if contract_id is not None:
            contracts[str(contract_id)] = dict(item)
    return contracts


def _guardrail_declarations(
    extensions: Mapping[str, Any],
) -> tuple[GuardrailDeclaration, ...]:
    guardrails = _as_mapping(extensions.get("guardrails"))
    if not guardrails:
        return ()
    declarations = guardrails.get("declarations")
    return tuple(
        GuardrailDeclaration.from_mapping(item) for item in _mapping_items(declarations)
    )


def _mcp_registry_sources(
    extensions: Mapping[str, Any],
) -> tuple[MCPRegistrySource, ...]:
    registry_sources = _as_mapping(extensions.get("mcp_registry_sources"))
    if not registry_sources:
        return ()
    sources = registry_sources.get("sources")
    return tuple(
        MCPRegistrySource.from_mapping(item) for item in _mapping_items(sources)
    )


def _mcp_lifecycle_diagnostics(
    extensions: Mapping[str, Any],
) -> MCPLifecycleDiagnostics | None:
    diagnostics = _as_mapping(extensions.get("mcp_lifecycle_diagnostics"))
    if not diagnostics:
        return None
    return MCPLifecycleDiagnostics.from_mapping(diagnostics)


def _handoff_metadata(
    metadata: Mapping[str, Any],
) -> tuple[HandoffMetadata, ...]:
    handoffs = metadata.get("handoffs")
    return tuple(
        HandoffMetadata.from_mapping(item) for item in _mapping_items(handoffs)
    )
