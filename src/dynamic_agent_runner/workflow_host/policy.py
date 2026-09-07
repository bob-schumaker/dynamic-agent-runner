"""Gate-independent compilation of cataloged no-tool workflow policy."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml
from dynamic_agent_runner import load_agent_package_workflow

from dynamic_agent_runner.workflow_host.catalog import CatalogPackageRevision
from dynamic_agent_runner.workflow_host.descriptor import (
    DeclaredTool,
    DeclaredLocalTool,
    DeclaredArtifactTool,
    DeclaredTerminalOutputValidator,
    InputContract,
    TaskInvocation,
    WorkflowDescriptor,
    WorkflowLimits,
    WorkspaceContract,
    validate_package_skill_contract,
    validate_no_tool_runtime_nodes,
    validate_runtime_tool_contract,
)


DESCRIPTOR_FILENAME = "workflow-descriptor.yaml"


class PolicyCompilationError(ValueError):
    """Raised when a cataloged package cannot produce immutable policy."""


@dataclass(frozen=True)
class WorkflowPolicy:
    """Logical package policy without any live profile or connection binding."""

    package_id: str
    revision_digest: str
    descriptor_digest: str
    policy_digest: str
    model_profile_requirement: str
    input_contract: InputContract
    task_invocation: TaskInvocation
    limits: WorkflowLimits
    required_capabilities: frozenset[str]
    workspace: WorkspaceContract = field(
        default_factory=lambda: WorkspaceContract((), "none")
    )
    declared_skill_ids: tuple[str, ...] = ()
    declared_tools: tuple[DeclaredTool, ...] = ()
    declared_local_tools: tuple[DeclaredLocalTool, ...] = ()
    declared_artifact_tools: tuple[DeclaredArtifactTool, ...] = ()
    terminal_output_validator: DeclaredTerminalOutputValidator | None = None


@dataclass(frozen=True)
class CapabilityResolution:
    """A deterministic, non-binding capability result."""

    status: str
    missing_capabilities: tuple[str, ...]


def compile_workflow_policy(revision: CatalogPackageRevision) -> WorkflowPolicy:
    """Compile descriptor and DAR graph data from one immutable catalog revision."""

    descriptor_path = revision.package_root / DESCRIPTOR_FILENAME
    try:
        descriptor_bytes = descriptor_path.read_bytes()
        descriptor = WorkflowDescriptor.from_mapping(yaml.safe_load(descriptor_bytes))
        workflow = load_agent_package_workflow(str(revision.package_root))
        _validate_local_tool_assets(
            package_root=revision.package_root, tools=descriptor.declared_local_tools
        )
        _validate_terminal_output_validator(
            package_root=revision.package_root,
            validator=descriptor.terminal_output_validator,
        )
        validate_no_tool_runtime_nodes(descriptor, workflow.runtime_manifest.nodes)
        validate_runtime_tool_contract(descriptor, workflow.runtime_manifest.tools)
        validate_package_skill_contract(
            descriptor,
            runtime_skills=workflow.runtime_manifest.skills,
            nodes=workflow.runtime_manifest.nodes,
            packaging=workflow.runtime_manifest.packaging,
            skill_source_resolution=workflow.runtime_manifest.skill_source_resolution_policy,
        )
    except Exception as error:  # DAR loader errors vary by invalid package artifact.
        raise PolicyCompilationError("cataloged package policy is invalid") from error
    if descriptor.package_id != revision.package_id:
        raise PolicyCompilationError("descriptor package_id does not match catalog")
    if workflow.runtime_manifest.package_id != revision.package_id:
        raise PolicyCompilationError("DAR package_id does not match catalog")
    if descriptor.output_schema_ref not in workflow.runtime_manifest.output_contracts:
        raise PolicyCompilationError("registered terminal output contract is missing")
    descriptor_digest = hashlib.sha256(descriptor_bytes).hexdigest()
    tool_capabilities = _tool_capabilities(descriptor.declared_tools)
    local_tool_capabilities = _local_tool_capabilities(descriptor.declared_local_tools)
    deferred_capabilities = _deferred_runtime_capabilities(descriptor, workflow)
    required_capabilities = frozenset(
        {
            "text_generation",
            *tool_capabilities,
            *local_tool_capabilities,
            *deferred_capabilities,
        }
    )
    policy_digest = _digest(
        {
            "format_version": 1,
            "package_id": revision.package_id,
            "revision_digest": revision.revision_digest,
            "descriptor_digest": descriptor_digest,
            "model_profile_requirement": descriptor.model_profile_requirement,
            "workspace": {
                "accepted_input_types": descriptor.workspace.accepted_input_types,
                "scratch_access": descriptor.workspace.scratch_access,
            },
            "input_contract": {
                "mode": descriptor.input_contract.mode,
                "additional_context_max_bytes": descriptor.input_contract.additional_context_max_bytes,
                "field_precedence": descriptor.input_contract.field_precedence,
            },
            "task_invocation": {
                "entrypoint": descriptor.task_invocation.entrypoint,
                "allowed_tool_ids": descriptor.task_invocation.allowed_tool_ids,
                "max_total_tool_calls": descriptor.task_invocation.max_total_tool_calls,
                "allowed_structured_input_fields": descriptor.task_invocation.allowed_structured_input_fields,
                "allowed_artifact_roles": descriptor.task_invocation.allowed_artifact_roles,
                "terminal_output_schema_ref": descriptor.task_invocation.terminal_output_schema_ref,
                "argument_sources": {
                    tool_id: {
                        argument_name: {
                            "sources": rule.sources,
                            "authority": rule.authority,
                        }
                        for argument_name, rule in sorted(arguments.items())
                    }
                    for tool_id, arguments in sorted(
                        descriptor.task_invocation.argument_sources.items()
                    )
                },
            },
            "declared_skill_ids": descriptor.declared_skill_ids,
            "declared_tools": [
                {
                    "tool_id": tool.tool_id,
                    "remote_tool_name": tool.remote_tool_name,
                    "side_effect": tool.side_effect,
                    "approval_required": tool.approval_required,
                }
                for tool in descriptor.declared_tools
            ],
            "declared_local_tools": [
                {
                    "tool_id": tool.tool_id,
                    "asset_path": tool.asset_path,
                    "accepted_artifact_role": tool.accepted_artifact_role,
                    "max_input_bytes": tool.max_input_bytes,
                    "max_output_bytes": tool.max_output_bytes,
                    "timeout_seconds": tool.timeout_seconds,
                }
                for tool in descriptor.declared_local_tools
            ],
            "declared_artifact_tools": [
                {
                    "tool_id": tool.tool_id,
                    "reviewed_package_name": tool.reviewed_package_name,
                    "accepted_artifact_role": tool.accepted_artifact_role,
                    "max_result_bytes": tool.max_result_bytes,
                }
                for tool in descriptor.declared_artifact_tools
            ],
            "terminal_output_validator": (
                {
                    "asset_path": descriptor.terminal_output_validator.asset_path,
                    "max_output_bytes": descriptor.terminal_output_validator.max_output_bytes,
                    "timeout_seconds": descriptor.terminal_output_validator.timeout_seconds,
                }
                if descriptor.terminal_output_validator is not None
                else None
            ),
            "max_steps": descriptor.limits.max_steps,
            "required_capabilities": sorted(required_capabilities),
        }
    )
    return WorkflowPolicy(
        package_id=revision.package_id,
        revision_digest=revision.revision_digest,
        descriptor_digest=descriptor_digest,
        policy_digest=policy_digest,
        model_profile_requirement=descriptor.model_profile_requirement,
        workspace=descriptor.workspace,
        input_contract=descriptor.input_contract,
        task_invocation=descriptor.task_invocation,
        limits=descriptor.limits,
        required_capabilities=required_capabilities,
        declared_skill_ids=descriptor.declared_skill_ids,
        declared_tools=descriptor.declared_tools,
        declared_local_tools=descriptor.declared_local_tools,
        declared_artifact_tools=descriptor.declared_artifact_tools,
        terminal_output_validator=descriptor.terminal_output_validator,
    )


def resolve_capabilities(
    policy: WorkflowPolicy, *, available_capabilities: Iterable[str]
) -> CapabilityResolution:
    """Resolve only declared logical requirements; this creates no registration."""

    available = frozenset(available_capabilities)
    missing = tuple(sorted(policy.required_capabilities - available))
    return CapabilityResolution(
        status="eligible" if not missing else "capability_unavailable",
        missing_capabilities=missing,
    )


def _tool_capabilities(tools: tuple[DeclaredTool, ...]) -> frozenset[str]:
    return frozenset(
        capability
        for capability, present in (
            ("mcp_read_only", any(tool.side_effect == "read" for tool in tools)),
            ("mcp_side_effects", any(tool.side_effect != "read" for tool in tools)),
        )
        if present
    )


def _local_tool_capabilities(
    tools: tuple[DeclaredLocalTool, ...],
) -> frozenset[str]:
    return frozenset({"local_tool_sandbox"}) if tools else frozenset()


def _validate_local_tool_assets(
    *, package_root: Path, tools: tuple[DeclaredLocalTool, ...]
) -> None:
    """Require each local-tool declaration to name a catalog-contained executable."""

    root = package_root.resolve(strict=True)
    for tool in tools:
        try:
            asset = (root / tool.asset_path).resolve(strict=True)
            asset.relative_to(root)
            metadata = os.lstat(asset)
        except (OSError, ValueError) as error:
            raise PolicyCompilationError("local tool asset is unavailable") from error
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or not metadata.st_mode & stat.S_IXUSR
        ):
            raise PolicyCompilationError("local tool asset is unavailable")


def _validate_terminal_output_validator(
    *, package_root: Path, validator: DeclaredTerminalOutputValidator | None
) -> None:
    if validator is None:
        return
    _validate_local_tool_assets(
        package_root=package_root,
        tools=(
            DeclaredLocalTool(
                tool_id="terminal-output-validator",
                asset_path=validator.asset_path,
                accepted_artifact_role="terminal_output",
                max_input_bytes=32 * 1024,
                max_output_bytes=validator.max_output_bytes,
                timeout_seconds=validator.timeout_seconds,
            ),
        ),
    )


def _deferred_runtime_capabilities(
    descriptor: WorkflowDescriptor, workflow: Any
) -> frozenset[str]:
    """Name declared runtime needs that this host does not provide by default."""

    manifest = workflow.runtime_manifest
    capabilities: set[str] = set()
    execution_policy = manifest.execution_policy
    prepare_model_input = execution_policy.get("prepare_model_input")
    if isinstance(prepare_model_input, dict):
        context_compaction = prepare_model_input.get("context_compaction")
        if isinstance(context_compaction, dict):
            auto = context_compaction.get("auto")
            if isinstance(auto, dict) and auto.get("enabled") is True:
                capabilities.add("context-pruning-pipeline")
    if descriptor.workspace.scratch_access == "ephemeral":
        capabilities.add("scratch-workspace")
    if any(
        media_type.startswith("image/")
        for media_type in descriptor.workspace.accepted_input_types
    ):
        capabilities.add("multimodal_input")
    if (
        manifest.async_session_policy is not None
        and manifest.async_session_policy.persist != "none"
    ):
        capabilities.add("durable-session-continuation")
    if (
        manifest.approval_interruption_policy is not None
        and manifest.approval_interruption_policy.mode == "pause_on_approval"
        and manifest.approval_interruption_policy.persist != "none"
    ):
        capabilities.add("native-approval-resume")
    if manifest.participant_groups or any(
        node.agent_as_tool is not None for node in manifest.nodes
    ):
        capabilities.add("collaboration-subagents")
    if manifest.rag_pipeline and any(
        "embeddings" in node.model_requirements.get("required_capabilities", ())
        for node in manifest.nodes
    ):
        capabilities.add("retrieval-embedding-rag")
    return frozenset(capabilities)


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
