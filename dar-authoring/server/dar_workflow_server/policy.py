"""Gate-independent compilation of cataloged no-tool workflow policy."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable

import yaml
from dynamic_agent_runner import load_agent_package_workflow

from dar_workflow_server.catalog import CatalogPackageRevision
from dar_workflow_server.descriptor import (
    DeclaredTool,
    InputContract,
    TaskInvocation,
    WorkflowDescriptor,
    WorkflowLimits,
    validate_no_tool_runtime_nodes,
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
    declared_tools: tuple[DeclaredTool, ...] = ()


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
        validate_no_tool_runtime_nodes(descriptor, workflow.runtime_manifest.nodes)
    except Exception as error:  # DAR loader errors vary by invalid package artifact.
        raise PolicyCompilationError("cataloged package policy is invalid") from error
    if descriptor.package_id != revision.package_id:
        raise PolicyCompilationError("descriptor package_id does not match catalog")
    if workflow.runtime_manifest.package_id != revision.package_id:
        raise PolicyCompilationError("DAR package_id does not match catalog")
    if descriptor.output_schema_ref not in workflow.runtime_manifest.output_contracts:
        raise PolicyCompilationError("registered terminal output contract is missing")
    descriptor_digest = hashlib.sha256(descriptor_bytes).hexdigest()
    required_capabilities = frozenset(
        {"local_model", *(("mcp_read_only",) if descriptor.declared_tools else ())}
    )
    policy_digest = _digest(
        {
            "format_version": 1,
            "package_id": revision.package_id,
            "revision_digest": revision.revision_digest,
            "descriptor_digest": descriptor_digest,
            "model_profile_requirement": descriptor.model_profile_requirement,
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
            },
            "declared_tools": [
                {
                    "tool_id": tool.tool_id,
                    "remote_tool_name": tool.remote_tool_name,
                }
                for tool in descriptor.declared_tools
            ],
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
        input_contract=descriptor.input_contract,
        task_invocation=descriptor.task_invocation,
        limits=descriptor.limits,
        required_capabilities=required_capabilities,
        declared_tools=descriptor.declared_tools,
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


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
