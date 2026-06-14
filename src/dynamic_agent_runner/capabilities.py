"""Capability/status reporting contracts for workflow preflight."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from dynamic_agent_runner.api import load_agent_package_workflow
from dynamic_agent_runner.errors import DynamicAgentRunnerError
from dynamic_agent_runner.models import LoadedAgentWorkflow, prepare_execution_plan
from dynamic_agent_runner.registry import ToolRegistryError


_OWNER_DYNAMIC_AGENT_RUNNER = "dynamic-agent-runner"
_OWNER_APPROVAL_INTERRUPTION = "approval-interruption-resume"
_OWNER_ASYNC_SESSION = "async-session-memory-pipeline"
_OWNER_GUARDRAILS = "live-guardrail-execution"
_OWNER_MCP = "mcp-runtime-integration"
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
        return _invalid_report(str(exc))

    plan = prepare_execution_plan(workflow)
    return CapabilityStatusReport.from_items(
        package_id=workflow.runtime_manifest.package_id,
        items=_capability_items(
            workflow,
            plan=plan,
            has_skill_refs=_has_skill_refs(plan),
            tool_registry=tool_registry,
            model_adapter=model_adapter,
            model_adapter_coverage=model_adapter_coverage,
            built_in_tool_packs=built_in_tool_packs,
        ),
    )


def _invalid_report(validation_error: str) -> CapabilityStatusReport:
    return CapabilityStatusReport.from_items(
        package_id=None,
        valid=False,
        validation_error=validation_error,
        items=(
            CapabilityStatusItem(
                id="package.validation",
                label="Package validation",
                state=CapabilityState.INVALID,
                category="validation",
                summary="The package could not be loaded or validated.",
                owner=_OWNER_DYNAMIC_AGENT_RUNNER,
            ),
        ),
    )


def _capability_items(
    workflow: LoadedAgentWorkflow,
    *,
    plan: object,
    has_skill_refs: bool,
    tool_registry: object | None,
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
    if manifest.mcp_registry_sources:
        items.append(
            _metadata_only_item(
                "metadata.mcp_registry_sources",
                "MCP registry sources",
                _OWNER_MCP,
                "MCP source declarations are preserved but no live MCP clients run.",
            )
        )
    if has_skill_refs:
        items.append(
            _metadata_only_item(
                "metadata.skill_refs",
                "Skill references",
                _OWNER_SKILL_SOURCE,
                "Skill references are preserved but SKILL.md bodies are not loaded.",
            )
        )
    items.extend(
        _model_coverage_items(
            plan,
            model_adapter=model_adapter,
            model_adapter_coverage=model_adapter_coverage,
        )
    )
    items.extend(_tool_coverage_items(plan, tool_registry=tool_registry))
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
