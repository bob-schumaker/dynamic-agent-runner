"""Capability/status reporting contracts for workflow preflight."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from dynamic_agent_runner.api import load_agent_package_workflow
from dynamic_agent_runner.artifacts import load_agent_package
from dynamic_agent_runner.behavior import effective_node_behavior
from dynamic_agent_runner.errors import DynamicAgentRunnerError
from dynamic_agent_runner.models import (
    LoadedAgentWorkflow,
    ToolOriginKind,
    prepare_execution_plan,
)
from dynamic_agent_runner.registry import ToolRegistryError


_OWNER_DYNAMIC_AGENT_RUNNER = "dynamic-agent-runner"
_OWNER_APPROVAL_INTERRUPTION = "approval-interruption-resume"
_OWNER_ASYNC_SESSION = "async-session-memory-pipeline"
_OWNER_GUARDRAILS = "live-guardrail-execution"
_OWNER_MCP = "mcp-runtime-integration"
_OWNER_RAG = "rag-orchestration-contract"
_OWNER_SANDBOX = "sandbox-workspace-runtime"
_OWNER_SKILL_SOURCE = "skill-source-resolution"
_OWNER_TOOL_LOOP = "iterative-agent-loop-runtime"


class CapabilityState(str, Enum):
    """Effective status for one runtime capability."""

    LIVE = "live"
    METADATA_ONLY = "metadata_only"
    MISSING_COLLABORATOR = "missing_collaborator"
    DISABLED = "disabled"
    UNSUPPORTED = "unsupported"
    INVALID = "invalid"


@dataclass(frozen=True)
class CapabilityStatusItem:
    """One capability entry in a preflight report."""

    id: str
    label: str
    state: CapabilityState | str
    category: str
    summary: str
    owner: str | None = None
    required_collaborator: str | None = None
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", CapabilityState(self.state))
        object.__setattr__(self, "details", dict(self.details))


@dataclass(frozen=True)
class CapabilityStatusSummary:
    """Summary counts for a capability report."""

    total: int = 0
    counts_by_state: Mapping[str, int] = field(default_factory=dict)

    @classmethod
    def from_items(
        cls,
        items: Iterable[CapabilityStatusItem],
    ) -> CapabilityStatusSummary:
        """Build deterministic counts from report items."""

        counts = Counter(item.state.value for item in items)
        return cls(
            total=sum(counts.values()),
            counts_by_state=dict(sorted(counts.items())),
        )


@dataclass(frozen=True)
class CapabilityStatusReport:
    """Read-only preflight report for a workflow package."""

    package_id: str | None
    items: tuple[CapabilityStatusItem, ...] = ()
    summary: CapabilityStatusSummary = field(default_factory=CapabilityStatusSummary)
    valid: bool = True
    validation_error: str | None = None

    @classmethod
    def from_items(
        cls,
        *,
        package_id: str | None,
        items: Iterable[CapabilityStatusItem],
        valid: bool = True,
        validation_error: str | None = None,
    ) -> CapabilityStatusReport:
        """Build a report with stable item ordering and summary counts."""

        sorted_items = tuple(
            sorted(items, key=lambda item: (item.category, item.id, item.label))
        )
        return cls(
            package_id=package_id,
            items=sorted_items,
            summary=CapabilityStatusSummary.from_items(sorted_items),
            valid=valid,
            validation_error=validation_error,
        )


def inspect_agent_package_capabilities(
    *,
    package_directory: str | Path,
    runtime_overrides: Any | None = None,
    tool_registry: Any | None = None,
    guardrail_registry: Any | None = None,
    model_adapter: Any | None = None,
    model_adapter_coverage: str | None = None,
    built_in_tool_packs: Iterable[str] | None = None,
    strict: bool = False,
) -> CapabilityStatusReport:
    """Inspect a workflow package's capabilities without executing it."""

    try:
        workflow = load_agent_package_workflow(
            str(package_directory),
            runtime_overrides=runtime_overrides,
        )
    except DynamicAgentRunnerError as exc:
        if strict:
            raise
        return _invalid_report(
            str(exc),
            package_directory=package_directory,
        )

    plan = prepare_execution_plan(workflow)
    return CapabilityStatusReport.from_items(
        package_id=workflow.runtime_manifest.package_id,
        items=_capability_items(
            workflow,
            plan=plan,
            has_skill_refs=_has_skill_refs(plan),
            tool_registry=tool_registry,
            guardrail_registry=guardrail_registry,
            model_adapter=model_adapter,
            model_adapter_coverage=model_adapter_coverage,
            built_in_tool_packs=built_in_tool_packs,
        ),
    )


def _invalid_report(
    validation_error: str,
    *,
    package_directory: str | Path | None = None,
) -> CapabilityStatusReport:
    package_id: str | None = None
    items: list[CapabilityStatusItem] = [
        CapabilityStatusItem(
            id="package.validation",
            label="Package validation",
            state=CapabilityState.INVALID,
            category="validation",
            summary="The package could not be loaded or validated.",
            owner=_OWNER_DYNAMIC_AGENT_RUNNER,
        ),
    ]
    if package_directory is not None:
        try:
            workflow = load_agent_package(package_directory)
        except DynamicAgentRunnerError:
            workflow = None
        if workflow is not None:
            package_id = workflow.runtime_manifest.package_id
            skill_item = _invalid_skill_source_resolution_item(
                workflow,
                validation_error,
            )
            if skill_item is not None:
                items.append(skill_item)
    return CapabilityStatusReport.from_items(
        package_id=package_id,
        valid=False,
        validation_error=validation_error,
        items=tuple(items),
    )


def _capability_items(
    workflow: LoadedAgentWorkflow,
    *,
    plan: object,
    has_skill_refs: bool,
    tool_registry: object | None,
    guardrail_registry: object | None,
    model_adapter: object | None,
    model_adapter_coverage: str | None,
    built_in_tool_packs: Iterable[str] | None,
) -> tuple[CapabilityStatusItem, ...]:
    manifest = workflow.runtime_manifest
    items: list[CapabilityStatusItem] = [
        CapabilityStatusItem(
            id="runtime.execution",
            label="Finite workflow execution",
            state=CapabilityState.LIVE,
            category="runtime",
            summary="Finite package-directory workflow execution is implemented.",
            owner=_OWNER_DYNAMIC_AGENT_RUNNER,
        )
    ]
    if manifest.approval_interruption_policy is not None:
        items.append(
            _metadata_only_item(
                "metadata.approval_interruption",
                "Approval interruption metadata",
                _OWNER_APPROVAL_INTERRUPTION,
                "Approval interruption declarations are preserved but not executed.",
            )
        )
        approval_item = _approval_interruption_item(plan, tool_registry=tool_registry)
        if approval_item is not None:
            items.append(approval_item)
    if manifest.async_session_policy is not None:
        items.append(
            _metadata_only_item(
                "metadata.async_session",
                "Async session metadata",
                _OWNER_ASYNC_SESSION,
                "Async session declarations are preserved but no session store runs.",
            )
        )
    if manifest.sandbox_runtime_policy is not None:
        items.append(
            _metadata_only_item(
                "metadata.sandbox_runtime",
                "Sandbox runtime metadata",
                _OWNER_SANDBOX,
                "Sandbox runtime declarations are preserved but no write runtime runs.",
            )
        )
    if manifest.tool_use_completion_policy is not None:
        items.append(
            _metadata_only_item(
                "metadata.tool_use_completion",
                "Tool-use completion metadata",
                _OWNER_TOOL_LOOP,
                "Tool-use loop policy is preserved but iterative loops do not run.",
            )
        )
    if manifest.handoffs:
        items.append(
            _metadata_only_item(
                "metadata.handoffs",
                "Handoff metadata",
                _OWNER_DYNAMIC_AGENT_RUNNER,
                "Handoff metadata is preserved but active handoff execution is absent.",
            )
        )
    if manifest.guardrails:
        items.append(
            _metadata_only_item(
                "metadata.guardrails",
                "Guardrail declarations",
                _OWNER_GUARDRAILS,
                "Guardrail declarations are preserved but not executed.",
            )
        )
        items.extend(
            _guardrail_coverage_items(
                manifest.guardrails,
                guardrail_registry=guardrail_registry,
            )
        )
    if manifest.mcp_registry_sources:
        items.append(
            _metadata_only_item(
                "metadata.mcp_registry_sources",
                "MCP registry sources",
                _OWNER_MCP,
                "MCP source declarations are preserved but no live MCP clients run.",
            )
        )
    items.extend(_rag_items(manifest.rag_pipeline, tool_registry=tool_registry))
    if has_skill_refs:
        items.append(_skill_source_resolution_item(workflow, plan=plan))
    items.extend(
        _model_coverage_items(
            plan,
            model_adapter=model_adapter,
            model_adapter_coverage=model_adapter_coverage,
        )
    )
    items.extend(_tool_coverage_items(plan, tool_registry=tool_registry))
    items.extend(_mcp_registry_items(plan, tool_registry=tool_registry))
    items.append(_local_workspace_pack_item(built_in_tool_packs))
    return tuple(items)


def _metadata_only_item(
    item_id: str,
    label: str,
    owner: str,
    summary: str,
) -> CapabilityStatusItem:
    return CapabilityStatusItem(
        id=item_id,
        label=label,
        state=CapabilityState.METADATA_ONLY,
        category="metadata",
        summary=summary,
        owner=owner,
    )


def _skill_source_resolution_item(
    workflow: LoadedAgentWorkflow,
    *,
    plan: object,
) -> CapabilityStatusItem:
    policy = workflow.runtime_manifest.skill_source_resolution_policy
    if policy is None or not policy.enabled:
        return CapabilityStatusItem(
            id="metadata.skill_refs",
            label="Skill references",
            state=CapabilityState.METADATA_ONLY,
            category="metadata",
            summary="Skill references are preserved but SKILL.md bodies are not loaded.",
            owner=_OWNER_SKILL_SOURCE,
            details={
                "source_resolution": "absent" if policy is None else "disabled",
                "referenced_skills": _referenced_skill_count(workflow, plan),
            },
        )
    return CapabilityStatusItem(
        id="runtime.skill_source_resolution",
        label="Package-local skill source resolution",
        state=CapabilityState.LIVE,
        category="runtime",
        summary="Package-local SKILL.md bodies are loaded into prompt preparation.",
        owner=_OWNER_SKILL_SOURCE,
        details={
            "allowed_sources": policy.allowed_sources,
            "prompt_role": policy.prompt_role,
            "referenced_skills": _referenced_skill_count(workflow, plan),
        },
    )


def _invalid_skill_source_resolution_item(
    workflow: LoadedAgentWorkflow,
    validation_error: str,
) -> CapabilityStatusItem | None:
    policy = workflow.runtime_manifest.skill_source_resolution_policy
    if policy is None or not policy.enabled:
        return None
    return CapabilityStatusItem(
        id="runtime.skill_source_resolution",
        label="Package-local skill source resolution",
        state=CapabilityState.INVALID,
        category="runtime",
        summary="Package-local SKILL.md source loading was rejected during validation.",
        owner=_OWNER_SKILL_SOURCE,
        details={
            "allowed_sources": policy.allowed_sources,
            "prompt_role": policy.prompt_role,
            "validation_error": validation_error,
        },
    )


def _referenced_skill_count(workflow: LoadedAgentWorkflow, plan: object) -> int:
    skill_refs: set[str] = set()
    nodes_by_id = getattr(plan, "nodes_by_id", {})
    if not isinstance(nodes_by_id, Mapping):
        return 0
    for node in nodes_by_id.values():
        if getattr(node, "kind", None) != "llm_step":
            continue
        behavior = effective_node_behavior(node.source_node, workflow)
        skill_refs.update(behavior.skill_refs)
    return len(skill_refs)


def _approval_interruption_item(
    plan: object,
    *,
    tool_registry: object | None,
) -> CapabilityStatusItem | None:
    if tool_registry is None:
        return None
    for node in _nodes(plan):
        if getattr(node, "kind", None) != "tool_use_step":
            continue
        tool_id = getattr(node, "tool_id", None)
        if not tool_id:
            continue
        try:
            tool = tool_registry.get_tool(str(tool_id))
        except ToolRegistryError:
            continue
        if not _tool_requires_approval(tool):
            continue
        return CapabilityStatusItem(
            id="runtime.approval_interruption",
            label="Direct tool approval interruption",
            state=CapabilityState.LIVE,
            category="runtime",
            summary=("Direct approval-required tool steps pause before invocation."),
            owner=_OWNER_APPROVAL_INTERRUPTION,
            details={
                "node_id": str(getattr(node, "id", "")),
                "tool_id": str(tool_id),
            },
        )
    return None


def _tool_requires_approval(tool: object) -> bool:
    definition = getattr(tool, "definition", None)
    policy = getattr(definition, "policy", None)
    value = getattr(policy, "approval_required", None) or getattr(
        definition, "approval_required", None
    )
    return str(value).strip().lower() in {"1", "true", "yes", "required"}


def _guardrail_coverage_items(
    declarations: Iterable[object],
    *,
    guardrail_registry: object | None,
) -> tuple[CapabilityStatusItem, ...]:
    items: list[CapabilityStatusItem] = []
    for declaration in declarations:
        if getattr(declaration, "phase", None) != "input":
            continue
        guardrail_id = str(getattr(declaration, "id", ""))
        if not guardrail_id:
            continue
        has_guardrail = (
            guardrail_registry is not None
            and guardrail_registry.has_guardrail(guardrail_id)
        )
        items.append(
            CapabilityStatusItem(
                id=f"guardrail.input.{guardrail_id}",
                label=f"Input guardrail {guardrail_id}",
                state=(
                    CapabilityState.LIVE
                    if has_guardrail
                    else CapabilityState.MISSING_COLLABORATOR
                ),
                category="guardrail",
                summary=(
                    "Input guardrail has a registered adapter."
                    if has_guardrail
                    else "Input guardrail requires a registered adapter."
                ),
                owner=_OWNER_GUARDRAILS,
                required_collaborator=None if has_guardrail else "guardrail_registry",
            )
        )
    return tuple(items)


def _rag_items(
    pipeline: Mapping[str, Any] | None,
    *,
    tool_registry: object | None,
) -> tuple[CapabilityStatusItem, ...]:
    if not pipeline:
        return ()
    return (
        _rag_pipeline_metadata_item(pipeline),
        *_rag_retriever_items(pipeline, tool_registry=tool_registry),
    )


def _rag_pipeline_metadata_item(
    pipeline: Mapping[str, Any],
) -> CapabilityStatusItem:
    return CapabilityStatusItem(
        id="metadata.rag_pipeline",
        label="RAG orchestration metadata",
        state=CapabilityState.METADATA_ONLY,
        category="rag",
        summary=(
            "RAG declarations are preserved and validated; retrieval execution "
            "remains caller-owned."
        ),
        owner=_OWNER_RAG,
        details=_rag_pipeline_metadata_details(pipeline),
    )


def _rag_pipeline_metadata_details(pipeline: Mapping[str, Any]) -> dict[str, object]:
    retrievers = _rag_retriever_declarations(pipeline)
    details = _rag_pipeline_base_details(pipeline, retrievers)
    if pipeline.get("provenance_required") is not None:
        details["provenance_required"] = pipeline.get("provenance_required") is True
    _add_rag_context_details(details, pipeline.get("context_assembly"))
    _add_rag_readiness_details(
        details,
        degraded_states=pipeline.get("degraded_states"),
        source_readiness=pipeline.get("source_readiness"),
        permissions=pipeline.get("permissions"),
    )
    return details


def _rag_pipeline_base_details(
    pipeline: Mapping[str, Any],
    retrievers: tuple[_RAGRetrieverDeclaration, ...],
) -> dict[str, object]:
    required_retrievers = [retriever for retriever in retrievers if retriever.required]
    return {
        "orchestration_mode": str(pipeline.get("orchestration_mode", "unknown")),
        "retrieval_mode": str(pipeline.get("retrieval_mode", "unknown")),
        "required_retrievers": len(required_retrievers),
        "declared_retrievers": len(retrievers),
    }


def _add_rag_context_details(
    details: dict[str, object],
    context_assembly: object,
) -> None:
    if not isinstance(context_assembly, Mapping):
        return
    target = context_assembly.get("target")
    max_context_tokens = context_assembly.get("max_context_tokens")
    required_evidence_fields = context_assembly.get("required_evidence_fields")
    if target is not None:
        details["context_assembly_target"] = str(target)
    if isinstance(max_context_tokens, int) and not isinstance(max_context_tokens, bool):
        details["context_max_tokens"] = max_context_tokens
    if isinstance(required_evidence_fields, list):
        details["required_evidence_field_count"] = len(
            [field for field in required_evidence_fields if isinstance(field, str)]
        )


def _add_rag_readiness_details(
    details: dict[str, object],
    *,
    degraded_states: object,
    source_readiness: object,
    permissions: object,
) -> None:
    if isinstance(degraded_states, list):
        details["degraded_states"] = tuple(
            sorted(str(item) for item in degraded_states)
        )
    if isinstance(source_readiness, Mapping):
        stale_state = source_readiness.get("stale_state")
        if stale_state is not None:
            details["stale_state"] = str(stale_state)
    if isinstance(permissions, Mapping):
        permission_filtering = permissions.get("permission_filtering")
        if permission_filtering is not None:
            details["permission_filtering"] = str(permission_filtering)


@dataclass(frozen=True)
class _RAGRetrieverDeclaration:
    retriever_id: str
    tool_id: str | None
    mode: str | None
    required: bool


def _rag_retriever_items(
    pipeline: Mapping[str, Any],
    *,
    tool_registry: object | None,
) -> tuple[CapabilityStatusItem, ...]:
    items: list[CapabilityStatusItem] = []
    for retriever in _rag_retriever_declarations(pipeline):
        state, summary, required_collaborator = _rag_retriever_state(
            retriever,
            tool_registry=tool_registry,
        )
        items.append(
            CapabilityStatusItem(
                id=f"rag.retriever.{retriever.retriever_id}",
                label=f"RAG retriever {retriever.retriever_id}",
                state=state,
                category="rag",
                summary=summary,
                owner=_OWNER_RAG,
                required_collaborator=required_collaborator,
                details={
                    "retriever_id": retriever.retriever_id,
                    "tool_id": retriever.tool_id or "",
                    "mode": retriever.mode or "unknown",
                    "required": retriever.required,
                },
            )
        )
    return tuple(items)


def _rag_retriever_state(
    retriever: _RAGRetrieverDeclaration,
    *,
    tool_registry: object | None,
) -> tuple[CapabilityState, str, str | None]:
    if not retriever.tool_id:
        return (
            CapabilityState.METADATA_ONLY,
            "RAG retriever has no live tool collaborator declaration.",
            None,
        )
    if tool_registry is None:
        if retriever.required:
            return (
                CapabilityState.MISSING_COLLABORATOR,
                "Required RAG retriever needs a caller-supplied tool registry.",
                "tool_registry",
            )
        return (
            CapabilityState.METADATA_ONLY,
            "Optional RAG retriever is declared but has no live registry coverage.",
            None,
        )
    try:
        tool_registry.get_tool(retriever.tool_id)
    except ToolRegistryError as exc:
        if "disabled" in str(exc).lower():
            return (
                CapabilityState.DISABLED,
                "RAG retriever tool is disabled in the registry.",
                None,
            )
        if retriever.required:
            return (
                CapabilityState.MISSING_COLLABORATOR,
                "Required RAG retriever tool is missing from the registry.",
                "tool_registry",
            )
        return (
            CapabilityState.METADATA_ONLY,
            "Optional RAG retriever tool is not registered.",
            None,
        )
    return (
        CapabilityState.LIVE,
        "RAG retriever tool is registered.",
        None,
    )


def _rag_retriever_declarations(
    pipeline: Mapping[str, Any],
) -> tuple[_RAGRetrieverDeclaration, ...]:
    retrievers = pipeline.get("retrievers")
    if not isinstance(retrievers, list):
        return ()
    declarations: list[_RAGRetrieverDeclaration] = []
    for index, retriever in enumerate(retrievers):
        if not isinstance(retriever, Mapping):
            continue
        retriever_id = retriever.get("id")
        tool_id = retriever.get("tool_id")
        mode = retriever.get("mode")
        declarations.append(
            _RAGRetrieverDeclaration(
                retriever_id=(
                    str(retriever_id) if retriever_id is not None else str(index)
                ),
                tool_id=str(tool_id) if tool_id is not None else None,
                mode=str(mode) if mode is not None else None,
                required=retriever.get("required") is True,
            )
        )
    return tuple(declarations)


def _has_skill_refs(plan: object) -> bool:
    nodes_by_id = getattr(plan, "nodes_by_id", {})
    if not isinstance(nodes_by_id, Mapping):
        return False
    return any(bool(getattr(node, "skill_refs", ())) for node in nodes_by_id.values())


def _model_coverage_items(
    plan: object,
    *,
    model_adapter: object | None,
    model_adapter_coverage: str | None,
) -> tuple[CapabilityStatusItem, ...]:
    coverage = model_adapter_coverage or "augmented"
    adapters = _normalize_adapters(model_adapter)
    items: list[CapabilityStatusItem] = []
    for node in _nodes(plan):
        if getattr(node, "kind", None) != "llm_step":
            continue
        model = getattr(node, "model", None)
        if model is None:
            continue
        if _adapter_supports_model(adapters, str(model)):
            state = CapabilityState.LIVE
            summary = f"Model {model!r} is covered by a supplied adapter."
            required_collaborator = None
        elif coverage == "strict":
            state = CapabilityState.MISSING_COLLABORATOR
            summary = f"Model {model!r} is not covered by a supplied adapter."
            required_collaborator = "model_adapter"
        else:
            state = CapabilityState.LIVE
            summary = (
                f"Model {model!r} may use augmented default OpenAI adapter coverage."
            )
            required_collaborator = None
        items.append(
            CapabilityStatusItem(
                id=f"model.{getattr(node, 'id', 'unknown')}",
                label=f"Model coverage for {getattr(node, 'id', 'unknown')}",
                state=state,
                category="model",
                summary=summary,
                owner="model-adapter-coverage",
                required_collaborator=required_collaborator,
                details={"model": str(model), "coverage": coverage},
            )
        )
    return tuple(items)


def _tool_coverage_items(
    plan: object,
    *,
    tool_registry: object | None,
) -> tuple[CapabilityStatusItem, ...]:
    items: list[CapabilityStatusItem] = []
    for tool_id in _referenced_tool_ids(plan):
        if tool_registry is None:
            state = CapabilityState.MISSING_COLLABORATOR
            summary = f"Tool {tool_id!r} requires a caller-supplied registry."
            required_collaborator = "tool_registry"
        else:
            try:
                tool_registry.get_tool(tool_id)
            except ToolRegistryError as exc:
                if "disabled" in str(exc).lower():
                    state = CapabilityState.DISABLED
                    summary = f"Tool {tool_id!r} is disabled in the registry."
                    required_collaborator = None
                else:
                    state = CapabilityState.MISSING_COLLABORATOR
                    summary = f"Tool {tool_id!r} is missing from the registry."
                    required_collaborator = "tool_registry"
            else:
                state = CapabilityState.LIVE
                summary = f"Tool {tool_id!r} is registered."
                required_collaborator = None
        items.append(
            CapabilityStatusItem(
                id=f"tool.{tool_id}",
                label=f"Tool {tool_id}",
                state=state,
                category="tool",
                summary=summary,
                owner=_OWNER_DYNAMIC_AGENT_RUNNER,
                required_collaborator=required_collaborator,
            )
        )
    return tuple(items)


def _mcp_registry_items(
    plan: object,
    *,
    tool_registry: object | None,
) -> tuple[CapabilityStatusItem, ...]:
    if tool_registry is None:
        return ()
    items: list[CapabilityStatusItem] = []
    for tool_id in _referenced_tool_ids(plan):
        try:
            tool = tool_registry.get_tool(tool_id)
        except ToolRegistryError:
            continue
        source = getattr(getattr(tool, "definition", None), "source", None)
        if getattr(source, "origin", None) is not ToolOriginKind.MCP:
            continue
        items.append(
            CapabilityStatusItem(
                id=f"mcp.tool.{tool_id}",
                label=f"MCP tool {tool_id}",
                state=CapabilityState.LIVE,
                category="mcp",
                summary="Caller-supplied MCP-origin registry entry is live.",
                owner=_OWNER_MCP,
                details={
                    "source_id": str(getattr(source, "source_id", "")),
                    "detail": str(getattr(source, "detail", "")),
                },
            )
        )
    return tuple(items)


def _local_workspace_pack_item(
    built_in_tool_packs: Iterable[str] | None,
) -> CapabilityStatusItem:
    enabled_packs = {str(pack) for pack in built_in_tool_packs or ()}
    enabled = "local_workspace" in enabled_packs
    return CapabilityStatusItem(
        id="built_in.local_workspace",
        label="local_workspace tool pack",
        state=CapabilityState.LIVE if enabled else CapabilityState.DISABLED,
        category="built_in_tool_pack",
        summary=(
            "The read-only local_workspace tool pack is enabled."
            if enabled
            else "The read-only local_workspace tool pack is disabled by default."
        ),
        owner=_OWNER_DYNAMIC_AGENT_RUNNER,
    )


def _normalize_adapters(model_adapter: object | None) -> tuple[object, ...]:
    if model_adapter is None:
        return ()
    if isinstance(model_adapter, Sequence) and not isinstance(
        model_adapter, (str, bytes, bytearray)
    ):
        return tuple(model_adapter)
    return (model_adapter,)


def _adapter_supports_model(adapters: tuple[object, ...], model: str) -> bool:
    for adapter in adapters:
        models = tuple(str(item) for item in getattr(adapter, "models", ()))
        if not models or model in models:
            return True
    return False


def _referenced_tool_ids(plan: object) -> tuple[str, ...]:
    tool_ids: list[str] = []
    for node in _nodes(plan):
        tool_id = getattr(node, "tool_id", None)
        if tool_id:
            tool_ids.append(str(tool_id))
        tool_ids.extend(
            str(tool_id) for tool_id in getattr(node, "available_tools", ())
        )
    return tuple(dict.fromkeys(tool_ids))


def _nodes(plan: object) -> tuple[object, ...]:
    nodes_by_id = getattr(plan, "nodes_by_id", {})
    if not isinstance(nodes_by_id, Mapping):
        return ()
    return tuple(nodes_by_id.values())
