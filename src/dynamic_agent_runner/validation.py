"""Validation engine for loaded dynamic-agent runtime artifacts."""

from __future__ import annotations

from collections.abc import Iterable

from dynamic_agent_runner.errors import WorkflowValidationError
from dynamic_agent_runner.models import (
    LoadedAgentWorkflow,
    PRIMITIVE_NODE_KINDS,
    RuntimeManifest,
    RuntimeNode,
    ToolIndex,
)

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
REQUIRED_RUNTIME_FIELDS = (
    "format_version",
    "package_type",
    "package_id",
    "entrypoint",
    "packaging",
    "nodes",
    "edges",
)


def validate_agent_workflow(workflow: LoadedAgentWorkflow) -> None:
    """Validate a loaded workflow artifact bundle before execution."""

    validate_runtime_manifest(workflow.runtime_manifest, workflow.tool_index)
    if workflow.tool_index is not None:
        validate_tool_index(workflow.tool_index)


def validate_runtime_manifest(
    manifest: RuntimeManifest,
    tool_index: ToolIndex | None = None,
) -> None:
    """Validate manifest fields, enums, and intra-manifest relationships."""

    errors: list[str] = []
    _extend(errors, _missing_runtime_fields(manifest))
    _extend(errors, _unsupported_runtime_enums(manifest))
    _extend(errors, _node_id_errors(manifest.nodes))
    _extend(errors, _edge_reference_errors(manifest))
    _extend(errors, _tool_reference_errors(manifest, tool_index))
    _extend(errors, _llm_prompt_errors(manifest.nodes))
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
    for index, skill in enumerate(tool_index.skills):
        if not skill.id:
            errors.append(f"tool index skill at position {index} is missing id")
    if errors:
        raise WorkflowValidationError(_format_errors("tool index", errors))


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
) -> list[str]:
    errors: list[str] = []
    tool_ids = {tool.id for tool in manifest.tools if tool.id}
    if tool_index is not None:
        tool_ids.update(tool.id for tool in tool_index.tools if tool.id)
    for node in manifest.nodes:
        if node.kind == "tool_use_step" and node.tool_id not in tool_ids:
            errors.append(
                f"tool_use_step node {node.id!r} references unknown tool "
                f"{node.tool_id!r}"
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


def _extend(target: list[str], values: Iterable[str]) -> None:
    target.extend(values)


def _format_errors(artifact_name: str, errors: Iterable[str]) -> str:
    details = "; ".join(errors)
    return f"Invalid {artifact_name}: {details}"
