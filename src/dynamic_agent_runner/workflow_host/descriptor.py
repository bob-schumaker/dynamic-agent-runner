"""Machine-validated no-tool workflow descriptors for the G1 base path."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import yaml

from dynamic_agent_runner.models import RuntimeNode
from dynamic_agent_runner.workflow_host.capabilities import (
    CapabilityError,
    CapabilityRequirements,
)
from dynamic_agent_runner.workflow_host.locked_inference import (
    InferenceRoles,
    LockedInferenceError,
    parse_inference_roles,
)


_CAPABILITY_REQUIREMENTS_MIN_DAR_VERSION = (0, 1, 17)


class WorkflowDescriptorError(ValueError):
    """Raised when a package descriptor exceeds the current wrapper gate."""


def load_descriptor_yaml(value: bytes) -> Mapping[str, Any]:
    """Load descriptor YAML while rejecting duplicate keys before conversion."""

    class DuplicateKeyLoader(yaml.SafeLoader):
        pass

    def construct_mapping(
        loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False
    ) -> dict[object, object]:
        mapping: dict[object, object] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in mapping:
                raise WorkflowDescriptorError("descriptor contains duplicate YAML keys")
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping

    DuplicateKeyLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping
    )
    try:
        loaded = yaml.load(value, Loader=DuplicateKeyLoader)
    except yaml.YAMLError as error:
        raise WorkflowDescriptorError("descriptor YAML is invalid") from error
    return _mapping(loaded, "descriptor")


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
    argument_sources: Mapping[str, Mapping[str, ArgumentSourceRule]] = MappingProxyType(
        {}
    )


@dataclass(frozen=True)
class ArgumentSourceRule:
    """Declared acceptable provenance kinds for one model-facing argument."""

    sources: tuple[str, ...]
    authority: bool


@dataclass(frozen=True)
class WorkflowLimits:
    max_steps: int


@dataclass(frozen=True)
class DeclaredTool:
    """One task-specific MCP capability declared by the package."""

    tool_id: str
    remote_tool_name: str
    side_effect: str = "read"
    approval_required: bool = False


@dataclass(frozen=True)
class DeclaredLocalTool:
    """One package-owned deterministic tool asset with finite sealed I/O limits."""

    tool_id: str
    asset_path: str
    accepted_artifact_role: str
    max_input_bytes: int
    max_output_bytes: int
    timeout_seconds: int


@dataclass(frozen=True)
class DeclaredArtifactTool:
    """One reviewed tool that may receive a sealed opaque artifact."""

    tool_id: str
    reviewed_package_name: str
    accepted_artifact_role: str
    max_result_bytes: int


@dataclass(frozen=True)
class DeclaredTerminalOutputValidator:
    """One package-owned post-processing validator for shaped terminal output."""

    asset_path: str
    max_output_bytes: int
    timeout_seconds: int


@dataclass(frozen=True)
class DeclaredTerminalOutputProcessor:
    """One fixed package asset in the private terminal-output chain."""

    asset_path: str
    max_output_bytes: int
    timeout_seconds: int


@dataclass(frozen=True)
class DeclaredInputConverter:
    """One sealed package asset that packs invocation bytes for one runner."""

    converter_id: str
    converter_contract_version: str
    compatible_runner_contract_id: str
    entrypoint: str
    asset_digest: str
    max_input_bytes: int
    max_output_bytes: int
    timeout_seconds: int


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
    declared_skill_ids: tuple[str, ...]
    declared_tools: tuple[DeclaredTool, ...]
    output_schema_ref: str
    limits: WorkflowLimits
    declared_local_tools: tuple[DeclaredLocalTool, ...] = ()
    declared_artifact_tools: tuple[DeclaredArtifactTool, ...] = ()
    terminal_output_validator: DeclaredTerminalOutputValidator | None = None
    terminal_output_processors: tuple[DeclaredTerminalOutputProcessor, ...] = ()
    input_converter: DeclaredInputConverter | None = None
    capability_requirements: CapabilityRequirements | None = None
    capability_requirements_digest: str | None = None
    inference_roles: InferenceRoles | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> WorkflowDescriptor:
        """Parse a descriptor and reject features unavailable before later gates."""

        mapping = _mapping(value, "descriptor")
        if mapping.get("format_version") != 1:
            raise WorkflowDescriptorError("format_version must be 1")
        declared_skill_ids = _parse_declared_skill_ids(mapping.get("skills"))
        declared_tools, declared_local_tools, declared_artifact_tools = (
            _parse_declared_tools(mapping.get("tools"))
        )
        runtime = _mapping(mapping.get("dar_runtime"), "dar_runtime")
        if runtime.get("distribution") != "dynamic-agent-runner":
            raise WorkflowDescriptorError("dar_runtime.distribution is invalid")
        capability_requirements = _parse_capability_requirements(
            mapping.get("capability_requirements"), runtime.get("required_version")
        )
        inference_roles = _parse_inference_roles(mapping.get("inference_roles"))
        if inference_roles is not None and capability_requirements is None:
            raise WorkflowDescriptorError("locked inference requires capabilities")
        input_contract = _parse_input_contract(mapping.get("input_contract"))
        workspace = _parse_workspace_contract(mapping.get("workspace"))
        task = _parse_task_invocation(mapping.get("task_invocation"))
        declared_tool_ids = tuple(
            tool.tool_id
            for tool in (
                *declared_tools,
                *declared_local_tools,
                *declared_artifact_tools,
            )
        )
        if task.allowed_tool_ids != declared_tool_ids:
            raise WorkflowDescriptorError(
                "task_invocation.allowed_tool_ids must exactly match declared tools"
            )
        _validate_side_effect_contract(declared_tools, task)
        output = _mapping(mapping.get("output"), "output")
        output_schema_ref = _text(output.get("schema_ref"), "output.schema_ref")
        terminal_output_validator = _parse_terminal_output_validator(output)
        terminal_output_processors = _parse_terminal_output_processors(output)
        input_converter = _parse_input_converter(mapping.get("input_converter"))
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
            declared_skill_ids=declared_skill_ids,
            declared_tools=declared_tools,
            output_schema_ref=output_schema_ref,
            limits=WorkflowLimits(_positive_int(limits.get("max_steps"), "max_steps")),
            declared_local_tools=declared_local_tools,
            declared_artifact_tools=declared_artifact_tools,
            terminal_output_validator=terminal_output_validator,
            terminal_output_processors=terminal_output_processors,
            input_converter=input_converter,
            capability_requirements=capability_requirements,
            capability_requirements_digest=(
                capability_requirements.digest
                if capability_requirements is not None
                else None
            ),
            inference_roles=inference_roles,
        )


def validate_no_tool_runtime_nodes(
    descriptor: WorkflowDescriptor, nodes: Sequence[RuntimeNode]
) -> None:
    """Reject a graph whose tool exposure escapes its task-specific declaration."""

    declared = {
        tool.tool_id
        for tool in (
            *descriptor.declared_tools,
            *descriptor.declared_local_tools,
            *descriptor.declared_artifact_tools,
        )
    }
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


def validate_runtime_tool_contract(
    descriptor: WorkflowDescriptor, runtime_tools: Sequence[Any]
) -> None:
    """Require runtime tool definitions to exactly match the descriptor."""

    expected = tuple(
        tool.tool_id
        for tool in (
            *descriptor.declared_tools,
            *descriptor.declared_local_tools,
            *descriptor.declared_artifact_tools,
        )
    )
    if tuple(tool.id for tool in runtime_tools) != expected:
        raise WorkflowDescriptorError(
            "runtime tools must exactly match descriptor tools"
        )


def validate_package_skill_contract(
    descriptor: WorkflowDescriptor,
    *,
    runtime_skills: Sequence[Any],
    nodes: Sequence[RuntimeNode],
    packaging: Mapping[str, Any],
    skill_source_resolution: Any | None,
) -> None:
    """Require descriptor skills to be package-local DAR bundled skills."""

    declared = descriptor.declared_skill_ids
    runtime_ids = tuple(skill.id for skill in runtime_skills)
    if runtime_ids != declared:
        raise WorkflowDescriptorError(
            "runtime skills must exactly match descriptor skills"
        )
    if not declared:
        return
    if packaging.get("skill_bundle_dir") != "skill-bundle":
        raise WorkflowDescriptorError("package skills require skill-bundle packaging")
    if (
        skill_source_resolution is None
        or not skill_source_resolution.enabled
        or skill_source_resolution.allowed_sources != ("package_bundle",)
        or skill_source_resolution.load_support_files
    ):
        raise WorkflowDescriptorError(
            "package skills require package_bundle skill source resolution"
        )
    for skill in runtime_skills:
        expected_path = f"skills/{skill.id}/SKILL.md"
        if skill.raw.get("bundled_path") != expected_path:
            raise WorkflowDescriptorError(
                "runtime skill bundled_path must use the package skill-bundle"
            )
        if skill.raw.get("instructions") is not None:
            raise WorkflowDescriptorError("runtime package skills must not be inline")
    referenced = {
        skill_id
        for node in nodes
        if node.kind == "llm_step"
        for skill_id in node.skill_refs
    }
    if referenced != set(declared):
        raise WorkflowDescriptorError(
            "runtime skill_refs must exactly cover descriptor skills"
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


def _parse_declared_skill_ids(value: object) -> tuple[str, ...]:
    skill_ids = _string_list(value, "skills")
    if len(set(skill_ids)) != len(skill_ids):
        raise WorkflowDescriptorError("skills must be unique")
    return skill_ids


def _parse_workspace_contract(value: object) -> WorkspaceContract:
    mapping = _mapping(value, "workspace")
    accepted_input_types = _string_list(
        mapping.get("accepted_input_types"), "workspace.accepted_input_types"
    )
    if len(set(accepted_input_types)) != len(accepted_input_types):
        raise WorkflowDescriptorError("workspace.accepted_input_types must be unique")
    scratch_access = mapping.get("scratch_access")
    if scratch_access not in {"none", "ephemeral"}:
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
        argument_sources=_parse_argument_sources(mapping.get("argument_sources")),
    )


def _parse_terminal_output_validator(
    output: Mapping[str, Any],
) -> DeclaredTerminalOutputValidator | None:
    value = output.get("validator")
    if value is None:
        return None
    validator = _mapping(value, "output.validator")
    if set(validator) != {"asset_path", "max_output_bytes", "timeout_seconds"}:
        raise WorkflowDescriptorError("output validator is invalid")
    asset_path = _text(validator.get("asset_path"), "output.validator.asset_path")
    if asset_path.startswith("/") or ".." in asset_path.split("/"):
        raise WorkflowDescriptorError(
            "output validator asset_path must be package-relative"
        )
    return DeclaredTerminalOutputValidator(
        asset_path=asset_path,
        max_output_bytes=_positive_int(
            validator.get("max_output_bytes"), "output.validator.max_output_bytes"
        ),
        timeout_seconds=_positive_int(
            validator.get("timeout_seconds"), "output.validator.timeout_seconds"
        ),
    )


def _parse_terminal_output_processors(
    output: Mapping[str, Any],
) -> tuple[DeclaredTerminalOutputProcessor, ...]:
    value = output.get("processors", [])
    if not isinstance(value, list) or not value:
        return ()
    processors = []
    for raw in value:
        processor = _mapping(raw, "output processor")
        if set(processor) != {"asset_path", "max_output_bytes", "timeout_seconds"}:
            raise WorkflowDescriptorError("output processor is invalid")
        asset_path = _text(processor.get("asset_path"), "output processor.asset_path")
        if asset_path.startswith("/") or ".." in asset_path.split("/"):
            raise WorkflowDescriptorError(
                "output processor asset_path must be package-relative"
            )
        processors.append(
            DeclaredTerminalOutputProcessor(
                asset_path=asset_path,
                max_output_bytes=_positive_int(
                    processor.get("max_output_bytes"),
                    "output processor.max_output_bytes",
                ),
                timeout_seconds=_positive_int(
                    processor.get("timeout_seconds"), "output processor.timeout_seconds"
                ),
            )
        )
    return tuple(processors)


def _parse_input_converter(value: object) -> DeclaredInputConverter | None:
    if value is None:
        return None
    converter = _mapping(value, "input converter")
    if set(converter) != {
        "converter_id",
        "converter_contract_version",
        "compatible_runner_contract_id",
        "entrypoint",
        "asset_digest",
        "declared_resource_limits",
    }:
        raise WorkflowDescriptorError("input converter is invalid")
    entrypoint = _text(converter.get("entrypoint"), "input converter.entrypoint")
    if entrypoint.startswith("/") or ".." in entrypoint.split("/"):
        raise WorkflowDescriptorError("input converter is invalid")
    if converter.get("converter_contract_version") != "v1":
        raise WorkflowDescriptorError("input converter is invalid")
    if converter.get("compatible_runner_contract_id") != "transformers-generate-v1":
        raise WorkflowDescriptorError("input converter is invalid")
    digest = converter.get("asset_digest")
    if not _is_digest(digest):
        raise WorkflowDescriptorError("input converter is invalid")
    limits = _mapping(
        converter.get("declared_resource_limits"), "input converter limits"
    )
    if set(limits) != {"max_input_bytes", "max_output_bytes", "timeout_seconds"}:
        raise WorkflowDescriptorError("input converter is invalid")
    return DeclaredInputConverter(
        converter_id=_text(
            converter.get("converter_id"), "input converter.converter_id"
        ),
        converter_contract_version="v1",
        compatible_runner_contract_id="transformers-generate-v1",
        entrypoint=entrypoint,
        asset_digest=digest,
        max_input_bytes=_positive_int(
            limits.get("max_input_bytes"), "input converter.max_input_bytes"
        ),
        max_output_bytes=_positive_int(
            limits.get("max_output_bytes"), "input converter.max_output_bytes"
        ),
        timeout_seconds=_positive_int(
            limits.get("timeout_seconds"), "input converter.timeout_seconds"
        ),
    )


def _parse_declared_tools(
    value: object,
) -> tuple[
    tuple[DeclaredTool, ...],
    tuple[DeclaredLocalTool, ...],
    tuple[DeclaredArtifactTool, ...],
]:
    if not isinstance(value, list):
        raise WorkflowDescriptorError("tools must be a list")
    tools: list[DeclaredTool] = []
    local_tools: list[DeclaredLocalTool] = []
    artifact_tools: list[DeclaredArtifactTool] = []
    seen: set[str] = set()
    for raw_tool in value:
        mapping = _mapping(raw_tool, "tools entry")
        tool_id = _text(mapping.get("id"), "tool.id")
        if tool_id in seen:
            raise WorkflowDescriptorError("declared tool ids must be unique")
        kind = mapping.get("kind")
        if kind == "local":
            local_tools.append(_parse_local_tool(mapping, tool_id))
            seen.add(tool_id)
            continue
        if kind == "artifact":
            artifact_tools.append(_parse_artifact_tool(mapping, tool_id))
            seen.add(tool_id)
            continue
        if kind != "mcp":
            raise WorkflowDescriptorError("declared tool kind is invalid")
        side_effect = mapping.get("side_effect")
        if side_effect not in {"read", "write", "delete"}:
            raise WorkflowDescriptorError("declared MCP tool side_effect is invalid")
        if side_effect in {"write", "delete"} and "approval_required" not in mapping:
            raise WorkflowDescriptorError(
                "side-effecting MCP tools must declare approval_required"
            )
        approval_required = mapping.get("approval_required", False)
        if not isinstance(approval_required, bool):
            raise WorkflowDescriptorError("tool.approval_required must be boolean")
        tools.append(
            DeclaredTool(
                tool_id=tool_id,
                remote_tool_name=_text(
                    mapping.get("remote_tool_name"), "tool.remote_tool_name"
                ),
                side_effect=side_effect,
                approval_required=approval_required,
            )
        )
        seen.add(tool_id)
    return tuple(tools), tuple(local_tools), tuple(artifact_tools)


def _parse_local_tool(mapping: Mapping[str, Any], tool_id: str) -> DeclaredLocalTool:
    if set(mapping) != {
        "id",
        "kind",
        "asset_path",
        "accepted_artifact_role",
        "max_input_bytes",
        "max_output_bytes",
        "timeout_seconds",
    }:
        raise WorkflowDescriptorError("declared local tool is invalid")
    asset_path = _text(mapping.get("asset_path"), "tool.asset_path")
    if asset_path.startswith("/") or ".." in asset_path.split("/"):
        raise WorkflowDescriptorError("local tool asset_path must be package-relative")
    return DeclaredLocalTool(
        tool_id=tool_id,
        asset_path=asset_path,
        accepted_artifact_role=_text(
            mapping.get("accepted_artifact_role"), "tool.accepted_artifact_role"
        ),
        max_input_bytes=_positive_int(
            mapping.get("max_input_bytes"), "tool.max_input_bytes"
        ),
        max_output_bytes=_positive_int(
            mapping.get("max_output_bytes"), "tool.max_output_bytes"
        ),
        timeout_seconds=_positive_int(
            mapping.get("timeout_seconds"), "tool.timeout_seconds"
        ),
    )


def _parse_artifact_tool(
    mapping: Mapping[str, Any], tool_id: str
) -> DeclaredArtifactTool:
    if set(mapping) != {
        "id",
        "kind",
        "reviewed_package_name",
        "accepted_artifact_role",
        "max_result_bytes",
    }:
        raise WorkflowDescriptorError("declared artifact tool is invalid")
    accepted_artifact_role = _text(
        mapping.get("accepted_artifact_role"), "tool.accepted_artifact_role"
    )
    if accepted_artifact_role != "opaque_binary_artifact":
        raise WorkflowDescriptorError(
            "artifact tools require opaque_binary_artifact input"
        )
    return DeclaredArtifactTool(
        tool_id=tool_id,
        reviewed_package_name=_text(
            mapping.get("reviewed_package_name"), "tool.reviewed_package_name"
        ),
        accepted_artifact_role=accepted_artifact_role,
        max_result_bytes=_positive_int(
            mapping.get("max_result_bytes"), "tool.max_result_bytes"
        ),
    )


def _parse_argument_sources(
    value: object,
) -> Mapping[str, Mapping[str, ArgumentSourceRule]]:
    if value is None:
        return MappingProxyType({})
    mapping = _mapping(value, "argument_sources")
    result: dict[str, Mapping[str, ArgumentSourceRule]] = {}
    for tool_id, raw_arguments in mapping.items():
        if not isinstance(tool_id, str) or not tool_id:
            raise WorkflowDescriptorError("argument_sources tool id is invalid")
        arguments = _mapping(raw_arguments, "argument_sources tool")
        parsed: dict[str, ArgumentSourceRule] = {}
        for argument_name, raw_rule in arguments.items():
            if not isinstance(argument_name, str) or not argument_name:
                raise WorkflowDescriptorError(
                    "argument_sources argument name is invalid"
                )
            rule = _mapping(raw_rule, "argument_sources argument")
            if set(rule) != {"sources", "authority"}:
                raise WorkflowDescriptorError("argument_sources argument is invalid")
            sources = _string_list(rule.get("sources"), "argument_sources sources")
            if len(set(sources)) != len(sources) or any(
                not _is_argument_source(source) for source in sources
            ):
                raise WorkflowDescriptorError("argument_sources sources are invalid")
            authority = rule.get("authority")
            if not isinstance(authority, bool):
                raise WorkflowDescriptorError("argument_sources authority is invalid")
            parsed[argument_name] = ArgumentSourceRule(sources, authority)
        if not parsed:
            raise WorkflowDescriptorError("argument_sources tool is empty")
        result[tool_id] = MappingProxyType(parsed)
    return MappingProxyType(result)


def _validate_side_effect_contract(
    tools: tuple[DeclaredTool, ...], task: TaskInvocation
) -> None:
    if not set(task.argument_sources).issubset({tool.tool_id for tool in tools}):
        raise WorkflowDescriptorError("argument_sources declares an unknown tool")
    for tool in tools:
        rules = task.argument_sources.get(tool.tool_id, {})
        if tool.side_effect == "read":
            continue
        if not rules:
            raise WorkflowDescriptorError(
                "side-effecting tool requires argument_sources"
            )
        for rule in rules.values():
            if rule.authority and "model_generated_transform" in rule.sources:
                raise WorkflowDescriptorError(
                    "authority argument cannot use model_generated_transform"
                )
            for source in rule.sources:
                _validate_source_reference(source, task)


def _validate_source_reference(source: str, task: TaskInvocation) -> None:
    if (
        source.startswith("sealed_structured_field:")
        and source.split(":", 1)[1] not in task.allowed_structured_input_fields
    ):
        raise WorkflowDescriptorError("argument_sources sealed field is not allowed")
    if (
        source.startswith("artifact_role:")
        and source.split(":", 1)[1] not in task.allowed_artifact_roles
    ):
        raise WorkflowDescriptorError("argument_sources artifact role is not allowed")


def _is_argument_source(value: str) -> bool:
    if value in {"cited_original_prompt_span", "model_generated_transform"}:
        return True
    for prefix in ("sealed_structured_field:", "artifact_role:", "package_constant:"):
        if value.startswith(prefix) and len(value) > len(prefix):
            return True
    return False


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WorkflowDescriptorError(f"{name} must be a mapping")
    return value


def _parse_capability_requirements(
    value: object, required_dar_version: object
) -> CapabilityRequirements | None:
    if value is None:
        return None
    if not _supports_capability_requirements(required_dar_version):
        raise WorkflowDescriptorError(
            "dar_runtime.required_version does not support capability requirements"
        )
    try:
        return CapabilityRequirements.from_mapping(value)
    except CapabilityError as error:
        raise WorkflowDescriptorError("capability requirements are invalid") from error


def _parse_inference_roles(value: object) -> InferenceRoles | None:
    if value is None:
        return None
    try:
        return parse_inference_roles(value)
    except LockedInferenceError as error:
        raise WorkflowDescriptorError("inference roles are invalid") from error


def _supports_capability_requirements(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parts = value.split(".")
    if len(parts) != 3 or any(
        not part.isascii() or not part.isdigit() for part in parts
    ):
        return False
    return (
        tuple(int(part) for part in parts) >= _CAPABILITY_REQUIREMENTS_MIN_DAR_VERSION
    )


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise WorkflowDescriptorError(f"{name} must be a non-empty string")
    return value


def _positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise WorkflowDescriptorError(f"{name} must be a positive integer")
    return value


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _string_list(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise WorkflowDescriptorError(f"{name} must be a list of non-empty strings")
    return tuple(value)
