"""Machine-validated no-tool workflow descriptors for the G1 base path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from dynamic_agent_runner.models import RuntimeNode


class WorkflowDescriptorError(ValueError):
    """Raised when a package descriptor exceeds the current wrapper gate."""


@dataclass(frozen=True)
class InputContract:
    mode: str
    additional_context_max_bytes: int
    field_precedence: str


@dataclass(frozen=True)
class WorkspaceContract:
    """Package-declared host constraints for opaque file artifacts."""

    accepted_input_types: tuple[str, ...]
    scratch_access: str


@dataclass(frozen=True)
class TaskInvocation:
    entrypoint: str
    max_total_tool_calls: int
    allowed_structured_input_fields: tuple[str, ...]
    allowed_artifact_roles: tuple[str, ...]
    terminal_output_schema_ref: str
    allowed_tool_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowLimits:
    max_steps: int


@dataclass(frozen=True)
class DeclaredTool:
    """One task-specific read-only MCP capability declared by the package."""

    tool_id: str
    remote_tool_name: str


@dataclass(frozen=True)
class WorkflowDescriptor:
    """The immutable authoring-to-runtime handoff for a bounded task workflow."""

    package_id: str
    purpose: str
    required_dar_version: str
    model_profile_requirement: str
    workspace: WorkspaceContract
    input_contract: InputContract
    task_invocation: TaskInvocation
    declared_tools: tuple[DeclaredTool, ...]
    output_schema_ref: str
    limits: WorkflowLimits

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> WorkflowDescriptor:
        """Parse a descriptor and reject features unavailable before later gates."""

        mapping = _mapping(value, "descriptor")
        if mapping.get("format_version") != 1:
            raise WorkflowDescriptorError("format_version must be 1")
        _require_empty_list(mapping.get("skills"), "skills")
        declared_tools = _parse_declared_tools(mapping.get("tools"))
        runtime = _mapping(mapping.get("dar_runtime"), "dar_runtime")
        if runtime.get("distribution") != "dynamic-agent-runner":
            raise WorkflowDescriptorError("dar_runtime.distribution is invalid")
        input_contract = _parse_input_contract(mapping.get("input_contract"))
        workspace = _parse_workspace_contract(mapping.get("workspace"))
        task = _parse_task_invocation(mapping.get("task_invocation"))
        if task.allowed_tool_ids != tuple(tool.tool_id for tool in declared_tools):
            raise WorkflowDescriptorError(
                "task_invocation.allowed_tool_ids must exactly match declared tools"
            )
        output = _mapping(mapping.get("output"), "output")
        output_schema_ref = _text(output.get("schema_ref"), "output.schema_ref")
        if output_schema_ref != task.terminal_output_schema_ref:
            raise WorkflowDescriptorError(
                "output.schema_ref must match task_invocation.terminal_output_schema_ref"
            )
        limits = _mapping(mapping.get("limits"), "limits")
        return cls(
            package_id=_text(mapping.get("package_id"), "package_id"),
            purpose=_text(mapping.get("purpose"), "purpose"),
            required_dar_version=_text(
                runtime.get("required_version"), "dar_runtime.required_version"
            ),
            model_profile_requirement=_text(
                _mapping(mapping.get("model"), "model").get("profile_requirement"),
                "model.profile_requirement",
            ),
            workspace=workspace,
            input_contract=input_contract,
            task_invocation=task,
            declared_tools=declared_tools,
            output_schema_ref=output_schema_ref,
            limits=WorkflowLimits(_positive_int(limits.get("max_steps"), "max_steps")),
        )


def validate_no_tool_runtime_nodes(
    descriptor: WorkflowDescriptor, nodes: Sequence[RuntimeNode]
) -> None:
    """Reject a graph whose tool exposure escapes its task-specific declaration."""

    declared = {tool.tool_id for tool in descriptor.declared_tools}
    if not declared and descriptor.task_invocation.max_total_tool_calls != 0:
        raise WorkflowDescriptorError(
            "no-tool descriptor must set max_total_tool_calls to 0"
        )
    for node in nodes:
        exposed = set(node.available_tools)
        if node.tool_id:
            exposed.add(node.tool_id)
        if not exposed.issubset(declared):
            raise WorkflowDescriptorError(
                f"runtime node {node.id!r} exposes an undeclared tool"
            )


def _parse_input_contract(value: object) -> InputContract:
    mapping = _mapping(value, "input_contract")
    if mapping.get("mode") != "hybrid":
        raise WorkflowDescriptorError("input_contract.mode must be hybrid")
    if mapping.get("structured_input_schema") is not None:
        raise WorkflowDescriptorError(
            "structured_input_schema is unavailable in no-tool v1"
        )
    if mapping.get("field_precedence") != "original_prompt":
        raise WorkflowDescriptorError(
            "input_contract.field_precedence must be original_prompt"
        )
    return InputContract(
        mode="hybrid",
        additional_context_max_bytes=_positive_int(
            mapping.get("additional_context_max_bytes"), "additional_context_max_bytes"
        ),
        field_precedence="original_prompt",
    )


def _parse_workspace_contract(value: object) -> WorkspaceContract:
    mapping = _mapping(value, "workspace")
    accepted_input_types = _string_list(
        mapping.get("accepted_input_types"), "workspace.accepted_input_types"
    )
    if len(set(accepted_input_types)) != len(accepted_input_types):
        raise WorkflowDescriptorError("workspace.accepted_input_types must be unique")
    scratch_access = mapping.get("scratch_access")
    if scratch_access != "none":
        raise WorkflowDescriptorError("workspace.scratch_access is unavailable")
    return WorkspaceContract(
        accepted_input_types=accepted_input_types,
        scratch_access=scratch_access,
    )


def _parse_task_invocation(value: object) -> TaskInvocation:
    mapping = _mapping(value, "task_invocation")
    allowed_tool_ids = _string_list(mapping.get("allowed_tool_ids"), "allowed_tool_ids")
    if len(set(allowed_tool_ids)) != len(allowed_tool_ids):
        raise WorkflowDescriptorError("allowed_tool_ids must be unique")
    max_total_tool_calls = mapping.get("max_total_tool_calls")
    if not isinstance(max_total_tool_calls, int) or isinstance(
        max_total_tool_calls, bool
    ):
        raise WorkflowDescriptorError(
            "max_total_tool_calls must be a non-negative integer"
        )
    if not allowed_tool_ids and max_total_tool_calls != 0:
        raise WorkflowDescriptorError(
            "max_total_tool_calls must be 0 for a no-tool descriptor"
        )
    if allowed_tool_ids and not 0 < max_total_tool_calls <= 16:
        raise WorkflowDescriptorError(
            "max_total_tool_calls is outside the bounded limit"
        )
    return TaskInvocation(
        entrypoint=_text(mapping.get("entrypoint"), "task_invocation.entrypoint"),
        allowed_tool_ids=allowed_tool_ids,
        max_total_tool_calls=max_total_tool_calls,
        allowed_structured_input_fields=_string_list(
            mapping.get("allowed_structured_input_fields"),
            "allowed_structured_input_fields",
        ),
        allowed_artifact_roles=_string_list(
            mapping.get("allowed_artifact_roles"), "allowed_artifact_roles"
        ),
        terminal_output_schema_ref=_text(
            mapping.get("terminal_output_schema_ref"), "terminal_output_schema_ref"
        ),
    )


def _parse_declared_tools(value: object) -> tuple[DeclaredTool, ...]:
    if not isinstance(value, list):
        raise WorkflowDescriptorError("tools must be a list")
    tools: list[DeclaredTool] = []
    seen: set[str] = set()
    for raw_tool in value:
        mapping = _mapping(raw_tool, "tools entry")
        tool_id = _text(mapping.get("id"), "tool.id")
        if tool_id in seen:
            raise WorkflowDescriptorError("declared tool ids must be unique")
        if mapping.get("kind") != "mcp":
            raise WorkflowDescriptorError("declared tool kind must be mcp")
        if mapping.get("side_effect") != "read":
            raise WorkflowDescriptorError("declared MCP tools must be read-only")
        tools.append(
            DeclaredTool(
                tool_id=tool_id,
                remote_tool_name=_text(
                    mapping.get("remote_tool_name"), "tool.remote_tool_name"
                ),
            )
        )
        seen.add(tool_id)
    return tuple(tools)


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WorkflowDescriptorError(f"{name} must be a mapping")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise WorkflowDescriptorError(f"{name} must be a non-empty string")
    return value


def _positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise WorkflowDescriptorError(f"{name} must be a positive integer")
    return value


def _require_empty_list(value: object, name: str) -> None:
    if not isinstance(value, list) or value:
        raise WorkflowDescriptorError(f"{name} must be an empty list")


def _string_list(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise WorkflowDescriptorError(f"{name} must be a list of non-empty strings")
    return tuple(value)
