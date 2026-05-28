"""Validation engine for loaded dynamic-agent runtime artifacts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from dynamic_agent_runner.errors import WorkflowValidationError
from dynamic_agent_runner.behavior import effective_node_behavior, skill_catalog
from dynamic_agent_runner.models import (
    LoadedAgentWorkflow,
    PRIMITIVE_NODE_KINDS,
    RuntimeManifest,
    RuntimeNode,
    ToolDefinition,
    ToolExposure,
    ToolIndex,
)
from dynamic_agent_runner.prompt_cache import prompt_cache_policy_from_value

SUPPORTED_FORMAT_VERSION = 1
SUPPORTED_PACKAGE_TYPE = "dynamic_agent_design"
SUPPORTED_DECISION_SUBTYPES = ("tool_response_compare", "simple_check", "llm_route")
SUPPORTED_EDGE_KINDS = (
    "sequential",
    "branch",
    "loopback",
    "parallel_fanout",
    "parallel_join",
    "event",
    "capability",
)
SUPPORTED_TOOL_INDEX_TYPE = "agent_runtime_tool_index"
SUPPORTED_OVERRIDE_TYPE = "dynamic_agent_runtime_overrides"
PROMPT_REPLACE_FIELDS = {
    "system",
    "developer",
    "user",
    "user_template",
    "output_schema_ref",
}
PROMPT_STRING_FIELDS = {"system", "developer", "user", "user_template"}
REQUIRED_RUNTIME_FIELDS = (
    "format_version",
    "package_type",
    "package_id",
    "entrypoint",
    "packaging",
    "nodes",
    "edges",
)


def validate_agent_workflow(
    workflow: LoadedAgentWorkflow,
    *,
    tool_registry: Any | None = None,
) -> None:
    """Validate a loaded workflow artifact bundle before execution."""

    validate_runtime_manifest(
        workflow.runtime_manifest,
        workflow.tool_index,
        tool_registry=tool_registry,
    )
    if workflow.tool_index is not None:
        validate_tool_index(workflow.tool_index)
    if workflow.runtime_overrides is not None:
        validate_runtime_behavior_overrides(workflow)
    else:
        validate_manifest_skill_references(workflow)


def validate_runtime_behavior_overrides(workflow: LoadedAgentWorkflow) -> None:
    """Validate runtime prompt and skill overrides against a loaded workflow."""

    overrides = workflow.runtime_overrides
    if overrides is None:
        return
    errors: list[str] = []
    if overrides.format_version != SUPPORTED_FORMAT_VERSION:
        errors.append(
            "unsupported behavior override format_version "
            f"{overrides.format_version!r}; expected {SUPPORTED_FORMAT_VERSION!r}"
        )
    if overrides.override_type != SUPPORTED_OVERRIDE_TYPE:
        errors.append(
            "unsupported behavior override override_type "
            f"{overrides.override_type!r}; expected {SUPPORTED_OVERRIDE_TYPE!r}"
        )
    catalog = skill_catalog(workflow)
    _extend(errors, _override_skill_definition_errors(overrides))
    node_map = {node.id: node for node in workflow.runtime_manifest.nodes if node.id}
    _extend(errors, _node_behavior_override_errors(overrides, node_map, catalog))
    _extend(errors, _effective_skill_reference_errors(workflow, catalog))
    _extend(errors, _effective_prompt_errors(workflow))
    if errors:
        raise WorkflowValidationError(
            _format_errors("runtime behavior overrides", errors)
        )


def validate_manifest_skill_references(workflow: LoadedAgentWorkflow) -> None:
    """Validate base node `skill_refs` without behavior overrides."""

    errors = _effective_skill_reference_errors(workflow, skill_catalog(workflow))
    if errors:
        raise WorkflowValidationError(_format_errors("runtime manifest", errors))


def validate_runtime_manifest(
    manifest: RuntimeManifest,
    tool_index: ToolIndex | None = None,
    *,
    tool_registry: Any | None = None,
) -> None:
    """Validate manifest fields, enums, and intra-manifest relationships."""

    errors: list[str] = []
    _extend(errors, _missing_runtime_fields(manifest))
    _extend(errors, _unsupported_runtime_enums(manifest))
    _extend(errors, _node_id_errors(manifest.nodes))
    _extend(errors, _edge_reference_errors(manifest))
    _extend(errors, _tool_definition_errors(manifest.tools, "runtime manifest tool"))
    _extend(errors, _tool_reference_errors(manifest, tool_index, tool_registry))
    _extend(errors, _llm_prompt_errors(manifest.nodes))
    _extend(errors, _prompt_cache_policy_errors(manifest))
    if errors:
        raise WorkflowValidationError(_format_errors("runtime manifest", errors))


def validate_tool_index(tool_index: ToolIndex) -> None:
    """Validate an external reusable tool index."""

    errors: list[str] = []
    if tool_index.format_version != SUPPORTED_FORMAT_VERSION:
        errors.append(
            "unsupported tool index format_version "
            f"{tool_index.format_version!r}; expected {SUPPORTED_FORMAT_VERSION!r}"
        )
    if tool_index.index_type != SUPPORTED_TOOL_INDEX_TYPE:
        errors.append(
            "unsupported tool index index_type "
            f"{tool_index.index_type!r}; expected {SUPPORTED_TOOL_INDEX_TYPE!r}"
        )
    if not tool_index.tools:
        errors.append("tool index must define at least one tool")
    for index, tool in enumerate(tool_index.tools):
        if not tool.id:
            errors.append(f"tool index tool at position {index} is missing id")
    _extend(errors, _tool_definition_errors(tool_index.tools, "tool index tool"))
    for index, skill in enumerate(tool_index.skills):
        if not skill.id:
            errors.append(f"tool index skill at position {index} is missing id")
    if errors:
        raise WorkflowValidationError(_format_errors("tool index", errors))


def _override_skill_definition_errors(overrides: Any) -> list[str]:
    errors: list[str] = []
    for skill in (*overrides.added_skills, *overrides.replacement_skills):
        if not skill.id:
            errors.append("behavior override skill is missing id")
        if skill.raw.get("instructions") is None:
            errors.append(
                f"behavior override skill {skill.id!r} is missing instructions"
            )
    return errors


def _node_behavior_override_errors(
    overrides: Any,
    node_map: Mapping[str, RuntimeNode],
    catalog: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    for node_id, node_override in overrides.node_overrides.items():
        node = node_map.get(node_id)
        if node is None:
            errors.append(f"behavior override targets unknown node {node_id!r}")
            continue
        if node.kind != "llm_step":
            errors.append(f"behavior override targets non-llm_step node {node_id!r}")
            continue
        _extend(errors, _prompt_override_errors(node_id, node_override.prompt))
        _extend(
            errors,
            _skill_reference_override_errors(
                node_id, node_override.skill_refs, catalog
            ),
        )
    return errors


def _prompt_override_errors(
    node_id: str,
    prompt_override: Any,
) -> list[str]:
    if prompt_override is None:
        return []
    errors: list[str] = []
    for field in prompt_override.replace:
        if field not in PROMPT_REPLACE_FIELDS:
            errors.append(
                f"prompt override for node {node_id!r} replaces unsupported field "
                f"{field!r}"
            )
    for operation_name, fields in (
        ("prepends", prompt_override.prepend),
        ("appends", prompt_override.append),
    ):
        for field in fields:
            if field not in PROMPT_STRING_FIELDS:
                errors.append(
                    f"prompt override for node {node_id!r} {operation_name} "
                    f"unsupported field {field!r}"
                )
    return errors


def _skill_reference_override_errors(
    node_id: str,
    skill_override: Any,
    catalog: Mapping[str, Any],
) -> list[str]:
    if skill_override is None:
        return []
    errors: list[str] = []
    referenced = set(skill_override.add) | set(skill_override.remove)
    if skill_override.only is not None:
        referenced.update(skill_override.only)
    for skill_id in sorted(referenced - set(catalog)):
        errors.append(
            f"skill override for node {node_id!r} references unknown skill {skill_id!r}"
        )
    return errors


def _effective_skill_reference_errors(
    workflow: LoadedAgentWorkflow,
    catalog: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    for node in workflow.runtime_manifest.nodes:
        if node.kind != "llm_step":
            continue
        behavior = effective_node_behavior(node, workflow)
        for skill_id in behavior.skill_refs:
            if skill_id not in catalog:
                errors.append(
                    f"llm_step node {node.id!r} references unknown skill {skill_id!r}"
                )
    return errors


def _effective_prompt_errors(workflow: LoadedAgentWorkflow) -> list[str]:
    errors: list[str] = []
    for node in workflow.runtime_manifest.nodes:
        if node.kind != "llm_step":
            continue
        prompt = effective_node_behavior(node, workflow).prompt
        if not prompt.get("user_template") and not prompt.get("user"):
            errors.append(
                f"llm_step node {node.id!r} effective prompt must define "
                "user_template or user"
            )
    return errors


def _missing_runtime_fields(manifest: RuntimeManifest) -> list[str]:
    return [
        f"missing required field: {field_name}"
        for field_name in REQUIRED_RUNTIME_FIELDS
        if field_name not in manifest.raw or manifest.raw.get(field_name) is None
    ]


def _unsupported_runtime_enums(manifest: RuntimeManifest) -> list[str]:
    errors: list[str] = []
    if manifest.format_version != SUPPORTED_FORMAT_VERSION:
        errors.append(
            "unsupported format_version "
            f"{manifest.format_version!r}; expected {SUPPORTED_FORMAT_VERSION!r}"
        )
    if manifest.package_type != SUPPORTED_PACKAGE_TYPE:
        errors.append(
            "unsupported package_type "
            f"{manifest.package_type!r}; expected {SUPPORTED_PACKAGE_TYPE!r}"
        )
    for node in manifest.nodes:
        if node.kind not in PRIMITIVE_NODE_KINDS:
            errors.append(f"node {node.id!r} has unsupported kind {node.kind!r}")
        if (
            node.kind == "decision_step"
            and node.decision_subtype is not None
            and node.decision_subtype not in SUPPORTED_DECISION_SUBTYPES
        ):
            errors.append(
                f"decision node {node.id!r} has unsupported decision_subtype "
                f"{node.decision_subtype!r}"
            )
    for edge in manifest.edges:
        if edge.edge_kind not in SUPPORTED_EDGE_KINDS:
            errors.append(
                f"edge {edge.source!r}->{edge.target!r} has unsupported "
                f"edge_kind {edge.edge_kind!r}"
            )
    return errors


def _node_id_errors(nodes: Iterable[RuntimeNode]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, node in enumerate(nodes):
        if not node.id:
            errors.append(f"node at position {index} is missing id")
            continue
        if node.id in seen:
            errors.append(f"duplicate node id: {node.id}")
        seen.add(node.id)
    return errors


def _edge_reference_errors(manifest: RuntimeManifest) -> list[str]:
    errors: list[str] = []
    node_ids = {node.id for node in manifest.nodes if node.id}
    if manifest.entrypoint and manifest.entrypoint not in node_ids:
        errors.append(f"entrypoint {manifest.entrypoint!r} does not reference a node")
    for index, edge in enumerate(manifest.edges):
        if not edge.source:
            errors.append(f"edge at position {index} is missing source")
        elif edge.source not in node_ids:
            errors.append(f"edge source {edge.source!r} does not reference a node")
        if not edge.target:
            errors.append(f"edge at position {index} is missing target")
        elif edge.target not in node_ids:
            errors.append(f"edge target {edge.target!r} does not reference a node")
    return errors


def _tool_reference_errors(
    manifest: RuntimeManifest,
    tool_index: ToolIndex | None,
    tool_registry: Any | None,
) -> list[str]:
    errors: list[str] = []
    if tool_registry is not None:
        for node in manifest.nodes:
            if node.kind != "tool_use_step":
                continue
            if not node.tool_id:
                errors.append(f"tool_use_step node {node.id!r} is missing tool_id")
                continue
            try:
                tool_registry.get_tool(node.tool_id)
            except Exception as exc:  # noqa: BLE001 - protocol may raise custom errors.
                errors.append(
                    f"tool_use_step node {node.id!r} references unavailable "
                    f"registry tool {node.tool_id!r}: {exc}"
                )
        return errors

    tool_ids = {tool.id for tool in manifest.tools if tool.id}
    if tool_index is not None:
        tool_ids.update(tool.id for tool in tool_index.tools if tool.id)
    for node in manifest.nodes:
        if node.kind == "tool_use_step" and node.tool_id not in tool_ids:
            errors.append(
                f"tool_use_step node {node.id!r} references unknown metadata "
                f"tool {node.tool_id!r}"
            )
    return errors


def _tool_definition_errors(
    tools: Iterable[ToolDefinition],
    label: str,
) -> list[str]:
    errors: list[str] = []
    for index, tool in enumerate(tools):
        if not isinstance(tool.exposure, ToolExposure):
            errors.append(
                f"{label} {tool.id!r} at position {index} has unsupported exposure "
                f"{tool.exposure!r}"
            )
    return errors


def _llm_prompt_errors(nodes: Iterable[RuntimeNode]) -> list[str]:
    errors: list[str] = []
    for node in nodes:
        if node.kind != "llm_step":
            continue
        if "prompt" not in node.raw and "prompt_source" not in node.raw:
            errors.append(
                f"llm_step node {node.id!r} must define prompt or prompt_source"
            )
    return errors


def _prompt_cache_policy_errors(manifest: RuntimeManifest) -> list[str]:
    try:
        prompt_cache_policy_from_value(manifest.execution_policy.get("prompt_cache"))
    except Exception as exc:  # noqa: BLE001 - normalized into validation errors.
        return [str(exc)]
    return []


def _extend(target: list[str], values: Iterable[str]) -> None:
    target.extend(values)


def _format_errors(artifact_name: str, errors: Iterable[str]) -> str:
    details = "; ".join(errors)
    return f"Invalid {artifact_name}: {details}"
