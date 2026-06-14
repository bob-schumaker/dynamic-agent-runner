"""Capability/status reporting contracts for workflow preflight."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from dynamic_agent_runner.api import load_agent_package_workflow
from dynamic_agent_runner.errors import DynamicAgentRunnerError
from dynamic_agent_runner.models import LoadedAgentWorkflow, prepare_execution_plan


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

    _ = (model_adapter, model_adapter_coverage, built_in_tool_packs)
    try:
        workflow = load_agent_package_workflow(
            str(package_directory),
            runtime_overrides=runtime_overrides,
            tool_registry=tool_registry,
        )
    except DynamicAgentRunnerError as exc:
        if strict:
            raise
        return _invalid_report(str(exc))

    plan = prepare_execution_plan(workflow)
    return CapabilityStatusReport.from_items(
        package_id=workflow.runtime_manifest.package_id,
        items=_capability_items(workflow, has_skill_refs=_has_skill_refs(plan)),
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
    has_skill_refs: bool,
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
