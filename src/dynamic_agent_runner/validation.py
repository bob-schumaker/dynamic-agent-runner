"""Validation engine for loaded dynamic-agent runtime artifacts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from dynamic_agent_runner.errors import WorkflowValidationError
from dynamic_agent_runner.behavior import effective_node_behavior, skill_catalog
from dynamic_agent_runner.models import (
    LoadedAgentWorkflow,
    ManifestObject,
    PRIMITIVE_NODE_KINDS,
    RuntimeManifest,
    RuntimeNode,
    ToolDefinition,
    ToolExposure,
    ToolIndex,
    ToolType,
)
from dynamic_agent_runner.prompt_cache import prompt_cache_policy_from_value
from dynamic_agent_runner.skill_sources import (
    SUPPORTED_SKILL_SOURCE_KINDS,
    SUPPORTED_SKILL_SOURCE_PROMPT_ROLES,
    SkillSourceResolutionError,
    enforce_node_skill_source_budget,
    resolve_package_bundled_skill_source,
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
SUPPORTED_OVERRIDE_TYPE = "dynamic_agent_runtime_overrides"
SUPPORTED_TOOL_TYPES = {
    "file_read",
    "file_write",
    "web_search",
    "web_fetch",
    "shell_command",
    "code_execution",
    "structured_data_query",
    "external_api",
    "agent_tool",
    "human_approval",
}
RAG_PATTERN_IDS = {"rag", "embedding_retrieval", "graph_retrieval", "graphrag"}
SUPPORTED_RAG_RETRIEVAL_MODES = {
    "keyword",
    "lexical_keyword",
    "structured",
    "embedding_semantic",
    "graph",
    "hybrid",
    "unknown",
}
SUPPORTED_RAG_ORCHESTRATION_MODES = {
    "basic_rag",
    "lexical_retrieval",
    "semantic_retrieval",
    "hybrid_retrieval",
    "graph_retrieval",
    "graphrag",
    "agentic_rag",
    "adaptive_retrieval",
    "unknown",
}
SUPPORTED_RAG_CAPABILITY_VALUES = {
    "required",
    "optional",
    "not_applicable",
    "unknown",
}
SUPPORTED_RAG_OWNER_VALUES = {"runtime", "host", "external_service", "unknown"}
SUPPORTED_RAG_RERANKING_VALUES = {
    "none",
    "model",
    "vector_score",
    "graph_score",
    "hybrid",
    "caller_adapter",
    "unknown",
}
SUPPORTED_RAG_FUSION_VALUES = {
    "none",
    "rrf",
    "weighted",
    "score_normalized",
    "caller_adapter",
    "unknown",
}
SUPPORTED_RAG_COMPRESSION_VALUES = {
    "none",
    "extractive",
    "semantic",
    "caller_adapter",
    "unknown",
}
SUPPORTED_RAG_CORRECTION_VALUES = {"none", "optional", "required", "unknown"}
SUPPORTED_RAG_FRESHNESS_VALUES = {"on_write", "scheduled", "manual", "unknown"}
SUPPORTED_RAG_CONTEXT_ASSEMBLY_TARGETS = {"prepare_model_input", "external"}
SUPPORTED_RAG_PERMISSION_FILTERING_VALUES = {
    "required",
    "optional",
    "not_applicable",
    "unknown",
}
SUPPORTED_RAG_PERMISSION_FAILURE_VALUES = {
    "fail_closed",
    "fail_open",
    "degraded",
    "unknown",
}
SUPPORTED_RAG_SOURCE_REGISTRY_VALUES = {
    "runtime",
    "host",
    "external_service",
    "caller_supplied",
    "unknown",
}
SUPPORTED_RAG_REFRESH_MODE_VALUES = {"on_write", "scheduled", "manual", "unknown"}
SUPPORTED_RAG_STALE_STATE_VALUES = {
    "fresh",
    "stale_but_allowed",
    "stale_blocked",
    "unknown",
}
SUPPORTED_RAG_CACHE_VALUES = {
    "disabled",
    "optional",
    "required",
    "metadata_only",
    "unknown",
}
SUPPORTED_RAG_DEGRADED_STATES = {
    "stale_but_allowed",
    "partial_results",
    "missing_optional_retriever",
    "cache_unavailable",
    "permission_filter_unavailable",
    "graph_store_unavailable",
    "unknown",
}
SUPPORTED_MODEL_REQUIRED_CAPABILITIES = {
    "structured_output",
    "tool_calling",
    "embeddings",
    "long_context",
    "multimodal_input",
    "json_mode",
    "citation_generation",
    "code_reasoning",
    "math_reasoning",
}
SUPPORTED_REASONING_LEVELS = {"minimal", "low", "medium", "high", "extended"}
SUPPORTED_REASONING_TASK_TYPES = {
    "classification",
    "extraction",
    "generation",
    "planning",
    "synthesis",
    "critique",
    "tool_selection",
    "route_selection",
    "code_reasoning",
    "math_reasoning",
}
SUPPORTED_UNCERTAINTY_HANDLING = {
    "answer_with_caveats",
    "ask_clarification",
    "escalate",
}
SUPPORTED_EXPECTED_INPUT_SIZES = {"small", "medium", "large", "very_large", "unknown"}
SUPPORTED_OUTPUT_FORMATS = {"free_text", "structured_json", "schema_ref", "tool_call"}
SUPPORTED_EVIDENCE_CITATIONS = {"required", "preferred", "not_needed"}
SUPPORTED_SENSITIVITY_VALUES = {"low", "medium", "high"}
SUPPORTED_DETERMINISM_VALUES = {"preferred", "balanced", "creative"}
SUPPORTED_DATA_BOUNDARIES = {
    "local_only",
    "private_runtime",
    "provider_allowed",
    "unknown",
}
SUPPORTED_FALLBACK_ACTIONS = {
    "use_lower_capability",
    "use_higher_capability",
    "escalate",
}
SUPPORTED_GUARDRAIL_PHASES = {"input", "output", "tool_input", "tool_output"}
SUPPORTED_GUARDRAIL_BEHAVIORS = {"abort", "reject_content"}
SUPPORTED_MCP_REGISTRY_SOURCE_STATUSES = {"active", "degraded", "failed", "disabled"}
SUPPORTED_MCP_TOOL_CACHE_VALUES = {"enabled", "disabled", "refresh_on_startup"}
SUPPORTED_MCP_OPERATION_LOCKING_VALUES = {"none", "per_server", "global"}
SUPPORTED_MCP_MEMORY_POLLUTION_VALUES = {"low", "medium", "high"}
SUPPORTED_MCP_STARTUP_MODES = {"strict", "degraded"}
SUPPORTED_MCP_RECONNECT_VALUES = {"disabled", "manual", "automatic"}
SUPPORTED_TOOL_USE_COMPLETION_RUN_AGAIN_VALUES = {
    "default",
    "required",
    "disabled",
}
SUPPORTED_TOOL_USE_COMPLETION_STOP_ON_TOOL_VALUES = {
    "default",
    "enabled",
    "disabled",
}
SUPPORTED_TOOL_USE_COMPLETION_FINAL_OUTPUT_VALUES = {
    "default",
    "tool_result",
    "state_field",
}
SUPPORTED_APPROVAL_INTERRUPTION_MODE_VALUES = {
    "metadata_only",
    "pause_on_approval",
    "reject_on_missing_approval",
}
SUPPORTED_APPROVAL_INTERRUPTION_PERSIST_VALUES = {
    "none",
    "in_memory",
    "external_checkpoint",
}
SUPPORTED_APPROVAL_INTERRUPTION_RESUME_FROM_VALUES = {
    "tool_call",
    "approval_decision",
    "workflow_restart",
}
SUPPORTED_ASYNC_SESSION_MODE_VALUES = {
    "metadata_only",
    "reuse_existing",
    "create_or_resume",
}
SUPPORTED_ASYNC_SESSION_PERSIST_VALUES = {
    "none",
    "in_memory",
    "external_checkpoint",
}
SUPPORTED_ASYNC_SESSION_HISTORY_VALUES = {
    "none",
    "last_turn",
    "full",
    "summary",
}
SUPPORTED_SANDBOX_RUNTIME_MODE_VALUES = {
    "metadata_only",
    "per_run_workspace",
    "shared_workspace",
}
SUPPORTED_SANDBOX_RUNTIME_FILESYSTEM_VALUES = {
    "read_only",
    "workspace_write",
    "full_access",
}
SUPPORTED_SANDBOX_RUNTIME_PERSIST_WORKSPACE_VALUES = {
    "none",
    "per_run",
    "named_session",
}
SUPPORTED_SANDBOX_RUNTIME_COMMAND_POLICY_VALUES = {
    "forbid",
    "allow_list",
    "caller_controlled",
}
SUPPORTED_SKILL_SOURCE_ALLOWED_SOURCES = set(SUPPORTED_SKILL_SOURCE_KINDS)
SUPPORTED_SKILL_SOURCE_PROMPT_ROLE_VALUES = set(SUPPORTED_SKILL_SOURCE_PROMPT_ROLES)
SUPPORTED_HANDOFF_ON_HANDOFF_VALUES = {"switch_active_profile"}
SUPPORTED_HANDOFF_NESTED_HISTORY_VALUES = {"preserve", "drop", "filtered"}
SUPPORTED_AGENT_AS_TOOL_OUTPUT_MODE_VALUES = {
    "default",
    "tool_result",
    "state_field",
}
SUPPORTED_CONTEXT_COMPACTION_SCOPES = {"current_run", "session", "node"}
SUPPORTED_CONTEXT_COMPACTION_IMPLEMENTATIONS = {
    "metadata_only",
    "basic",
    "rolling_summary",
    "provider",
}
SUPPORTED_CONTEXT_COMPACTION_STRATEGIES = {
    "basic",
    "rolling_summary",
    "provider",
    "off",
}
SUPPORTED_CONTEXT_COMPACTION_MODES = {"auto", "manual", "off"}
SUPPORTED_CONTEXT_COMPACTION_MANUAL_MODES = {"disabled", "allowed", "required"}
SUPPORTED_CONTEXT_COMPACTION_TRIGGERS = {
    "token_threshold",
    "reserve_tokens",
    "manual",
    "none",
}
SUPPORTED_CONTEXT_RESET_BEHAVIORS = {"none", "new_window"}
SUPPORTED_CONTEXT_COMPRESSION_PROFILES = {
    "balanced",
    "fast",
    "exact",
    "semantic",
    "recency_weighted",
    "instruction_weighted",
}
SUPPORTED_CONTEXT_SELECTION_STRATEGIES = {
    "deterministic_overlap",
    "injected_semantic",
    "none",
}
SUPPORTED_CONTEXT_LIFECYCLE_STAGES = {
    "validate",
    "segment",
    "score",
    "place",
    "select",
    "assemble",
    "compress",
    "omit",
    "report",
}
SUPPORTED_CONTEXT_METRICS = {
    "lane_utilization",
    "information_density",
    "redundancy_ratio",
    "coverage_completeness",
    "compression_ratio",
    "processing_duration",
    "summary_fidelity",
}
SUPPORTED_CONTEXT_LANE_BUDGET_FIELDS = {
    "pinned_tokens",
    "current_turn_tokens",
    "recent_turn_tokens",
    "summary_tokens",
    "selected_turn_tokens",
    "file_context_tokens",
}
REACT_LOOP_PATTERN_ID = "react_loop"
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
    validate_loaded_package_structure(workflow)


def validate_loaded_package_structure(workflow: LoadedAgentWorkflow) -> None:
    """Validate canonical package-directory structure and bundled skill paths."""

    package_root = workflow.package_root
    if package_root is None:
        return

    errors: list[str] = []
    skill_bundle_root = (
        Path(workflow.skill_bundle_root) if workflow.skill_bundle_root else None
    )
    requires_skill_bundle_root = any(
        _skill_requires_bundle_root(skill) for skill in workflow.runtime_manifest.skills
    )
    if (
        requires_skill_bundle_root
        and skill_bundle_root is not None
        and not skill_bundle_root.is_dir()
    ):
        errors.append(
            f"package skill-bundle directory does not exist: {skill_bundle_root}"
        )

    for skill in workflow.runtime_manifest.skills:
        _extend(
            errors,
            _bundled_skill_path_errors(skill, skill_bundle_root),
        )
    _extend(errors, _skill_source_resolution_source_errors(workflow))

    if errors:
        raise WorkflowValidationError(_format_errors("agent package", errors))


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
    _extend(errors, _legacy_root_field_errors(manifest))
    _extend(errors, _extension_errors(manifest))
    _extend(errors, _node_id_errors(manifest.nodes))
    _extend(errors, _edge_reference_errors(manifest))
    _extend(errors, _tool_definition_errors(manifest.tools, "runtime manifest tool"))
    _extend(errors, _tool_reference_errors(manifest, tool_index, tool_registry))
    _extend(errors, _llm_prompt_errors(manifest.nodes))
    _extend(errors, _context_pipeline_attachment_errors(manifest.nodes))
    _extend(errors, _model_requirements_errors(manifest))
    _extend(errors, _rag_pipeline_errors(manifest))
    _extend(errors, _react_loop_errors(manifest))
    _extend(errors, _tool_use_completion_policy_errors(manifest))
    _extend(errors, _approval_interruption_policy_errors(manifest))
    _extend(errors, _async_session_policy_errors(manifest))
    _extend(errors, _sandbox_runtime_policy_errors(manifest))
    _extend(errors, _skill_source_resolution_policy_errors(manifest))
    _extend(errors, _handoff_metadata_errors(manifest))
    _extend(errors, _agent_as_tool_metadata_errors(manifest))
    _extend(errors, _prompt_cache_policy_errors(manifest))
    _extend(errors, _file_context_policy_errors(manifest))
    _extend(errors, _guardrail_declaration_errors(manifest))
    _extend(errors, _mcp_registry_source_errors(manifest))
    _extend(errors, _mcp_lifecycle_diagnostics_errors(manifest))
    _extend(errors, _prepare_model_input_context_policy_errors(manifest))
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


def _bundled_skill_path_errors(skill: Any, skill_bundle_root: Path | None) -> list[str]:
    errors: list[str] = []
    skill_id = skill.id or "<unknown>"
    bundled_path = _bundled_path_value(skill.raw)
    if bundled_path is not None:
        if skill_bundle_root is None:
            errors.append(
                f"skill {skill_id!r} declares bundled_path but packaging.skill_bundle_dir is missing"
            )
        else:
            _extend(
                errors,
                _bundled_path_target_errors(
                    bundled_path,
                    skill_bundle_root,
                    label=f"skill {skill_id!r}",
                ),
            )

    for index, support_file in enumerate(_support_file_items(skill.raw)):
        support_bundled_path = _bundled_path_value(support_file)
        if support_bundled_path is None:
            continue
        if skill_bundle_root is None:
            errors.append(
                "skill "
                f"{skill_id!r} support file at position {index} declares bundled_path "
                "but packaging.skill_bundle_dir is missing"
            )
            continue
        support_label = support_file.get("id") or support_file.get("name") or str(index)
        _extend(
            errors,
            _bundled_path_target_errors(
                support_bundled_path,
                skill_bundle_root,
                label=f"skill {skill_id!r} support file {support_label!r}",
            ),
        )
    return errors


def _skill_requires_bundle_root(skill: Any) -> bool:
    if _bundled_path_value(skill.raw) is not None:
        return True
    return any(
        _bundled_path_value(support_file) is not None
        for support_file in _support_file_items(skill.raw)
    )


def _support_file_items(raw_skill: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = raw_skill.get("support_files")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _bundled_path_value(raw_value: Mapping[str, Any]) -> str | None:
    value = raw_value.get("bundled_path")
    if value is None:
        return None
    return str(value)


def _bundled_path_target_errors(
    bundled_path: str,
    skill_bundle_root: Path,
    *,
    label: str,
) -> list[str]:
    errors: list[str] = []
    relative_path = Path(bundled_path)
    if relative_path.is_absolute():
        errors.append(f"{label} bundled_path must be relative: {bundled_path!r}")
        return errors

    candidate = skill_bundle_root / relative_path
    try:
        candidate.relative_to(skill_bundle_root)
    except ValueError:
        errors.append(
            f"{label} bundled_path escapes package skill-bundle directory: {bundled_path!r}"
        )
        return errors

    if not candidate.is_file():
        errors.append(
            f"{label} bundled_path not found in package skill-bundle: {candidate}"
        )
    return errors


def _skill_source_resolution_source_errors(workflow: LoadedAgentWorkflow) -> list[str]:
    policy_metadata = workflow.runtime_manifest.skill_source_resolution_policy
    if policy_metadata is None or not policy_metadata.enabled:
        return []

    boundary_error = _skill_source_resolution_boundary_error(workflow)
    if boundary_error is not None:
        return [boundary_error]

    return _enabled_skill_source_resolution_source_errors(workflow)


def _skill_source_resolution_boundary_error(
    workflow: LoadedAgentWorkflow,
) -> str | None:
    if workflow.package_root is None:
        return "runtime.execution_policy.skill_source_resolution requires a package-loaded workflow"
    if workflow.skill_bundle_root is None:
        return "runtime.execution_policy.skill_source_resolution requires packaging.skill_bundle_dir"
    return None


def _enabled_skill_source_resolution_source_errors(
    workflow: LoadedAgentWorkflow,
) -> list[str]:
    errors: list[str] = []
    policy_metadata = workflow.runtime_manifest.skill_source_resolution_policy
    assert policy_metadata is not None
    assert workflow.skill_bundle_root is not None
    policy = policy_metadata.to_policy()
    catalog = skill_catalog(workflow)
    for node in workflow.runtime_manifest.nodes:
        if node.kind != "llm_step":
            continue
        errors.extend(
            _node_skill_source_resolution_errors(
                node=node,
                workflow=workflow,
                catalog=catalog,
                policy=policy,
            )
        )
    return errors


def _node_skill_source_resolution_errors(
    *,
    node: RuntimeNode,
    workflow: LoadedAgentWorkflow,
    catalog: Mapping[str, ManifestObject],
    policy: Any,
) -> list[str]:
    errors: list[str] = []
    resolved_sources = []
    assert workflow.skill_bundle_root is not None
    behavior = effective_node_behavior(node, workflow)
    for skill_id in behavior.skill_refs:
        skill = catalog.get(skill_id)
        if skill is None:
            continue
        if skill.raw.get("instructions") is not None:
            continue
        try:
            resolved_sources.append(
                resolve_package_bundled_skill_source(
                    skill_id=skill_id,
                    raw_skill=skill.raw,
                    package_id=workflow.runtime_manifest.package_id,
                    skill_bundle_root=workflow.skill_bundle_root,
                    policy=policy,
                )
            )
        except SkillSourceResolutionError as exc:
            errors.append(str(exc))
    try:
        enforce_node_skill_source_budget(
            tuple(resolved_sources),
            policy=policy,
            node_id=str(node.id),
        )
    except SkillSourceResolutionError as exc:
        errors.append(str(exc))
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


def _legacy_root_field_errors(manifest: RuntimeManifest) -> list[str]:
    return [
        f"legacy root field {field_name!r} must move into grouped runtime "
        "or metadata sections"
        for field_name in manifest.legacy_root_fields
    ]


def _extension_errors(manifest: RuntimeManifest) -> list[str]:
    errors: list[str] = []
    for extension_id, extension in manifest.extensions.items():
        if not isinstance(extension, Mapping):
            errors.append(f"malformed extension {extension_id!r}: expected mapping")
            continue
        required = extension.get("required", False)
        if not isinstance(required, bool):
            errors.append(
                f"malformed extension {extension_id!r}: required must be boolean"
            )
            continue
        config = extension.get("config", {})
        if not isinstance(config, Mapping):
            errors.append(
                f"malformed extension {extension_id!r}: config must be mapping"
            )
            continue
        if extension_id in {
            "guardrails",
            "mcp_registry_sources",
            "mcp_lifecycle_diagnostics",
        }:
            continue
        if required:
            errors.append(f"required unsupported extension {extension_id!r}")
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
        if tool.tool_type is not None and not isinstance(tool.tool_type, ToolType):
            errors.append(
                f"{label} {tool.id!r} at position {index} has unsupported tool_type "
                f"{tool.tool_type!r}"
            )
        if not isinstance(tool.exposure, ToolExposure):
            errors.append(
                f"{label} {tool.id!r} at position {index} has unsupported exposure "
                f"{tool.exposure!r}"
            )
    return errors


def _guardrail_declaration_errors(manifest: RuntimeManifest) -> list[str]:
    errors: list[str] = []
    raw_guardrails = None
    if isinstance(manifest.extensions.get("guardrails"), Mapping):
        raw_guardrails = manifest.extensions.get("guardrails")
    if raw_guardrails is None:
        return errors
    declarations = raw_guardrails.get("declarations")
    if declarations is not None and not isinstance(declarations, list):
        errors.append("guardrails declarations must be a list")
        return errors
    for index, declaration in enumerate(manifest.guardrails):
        if not declaration.id:
            errors.append(f"guardrail declaration at position {index} is missing id")
        if declaration.phase not in SUPPORTED_GUARDRAIL_PHASES:
            errors.append(
                f"guardrail declaration {declaration.id!r} has unsupported phase "
                f"{declaration.phase!r}"
            )
        if declaration.behavior_on_tripwire not in SUPPORTED_GUARDRAIL_BEHAVIORS:
            errors.append(
                f"guardrail declaration {declaration.id!r} has unsupported "
                "behavior_on_tripwire "
                f"{declaration.behavior_on_tripwire!r}"
            )
        if (
            declaration.behavior_on_tripwire == "reject_content"
            and declaration.message is None
        ):
            errors.append(
                f"guardrail declaration {declaration.id!r} with reject_content "
                "must define message or reject_content_message"
            )
    return errors


def _mcp_registry_source_errors(manifest: RuntimeManifest) -> list[str]:
    errors: list[str] = []
    raw_registry_sources = manifest.extensions.get("mcp_registry_sources")
    if raw_registry_sources is None:
        return errors
    if not isinstance(raw_registry_sources, Mapping):
        return ["mcp_registry_sources extension must be a mapping"]
    raw_sources = raw_registry_sources.get("sources")
    if raw_sources is not None and not isinstance(raw_sources, list):
        return ["mcp_registry_sources.sources must be a list"]
    for index, source in enumerate(manifest.mcp_registry_sources):
        _extend(errors, _mcp_registry_source_entry_errors(index, source))
    return errors


def _mcp_registry_source_entry_errors(index: int, source: Any) -> list[str]:
    errors: list[str] = []
    source_id = source.id
    if not source_id:
        errors.append(f"mcp registry source at position {index} is missing id")
    if not source.server:
        errors.append(f"mcp registry source {source_id!r} must define server")
    _append_unsupported_mcp_registry_source_value(
        errors,
        source_id,
        field_name="status",
        value=source.status,
        supported=SUPPORTED_MCP_REGISTRY_SOURCE_STATUSES,
    )
    _append_unsupported_mcp_registry_source_value(
        errors,
        source_id,
        field_name="tool_cache",
        value=source.tool_cache,
        supported=SUPPORTED_MCP_TOOL_CACHE_VALUES,
    )
    _append_unsupported_mcp_registry_source_value(
        errors,
        source_id,
        field_name="operation_locking",
        value=source.operation_locking,
        supported=SUPPORTED_MCP_OPERATION_LOCKING_VALUES,
    )
    _append_unsupported_mcp_registry_source_value(
        errors,
        source_id,
        field_name="memory_pollution",
        value=source.memory_pollution,
        supported=SUPPORTED_MCP_MEMORY_POLLUTION_VALUES,
    )
    if source.disabled is None:
        errors.append(
            f"mcp registry source {source_id!r} must define disabled as boolean"
        )
    return errors


def _append_unsupported_mcp_registry_source_value(
    errors: list[str],
    source_id: str | None,
    *,
    field_name: str,
    value: str | None,
    supported: set[str],
) -> None:
    if value not in supported:
        errors.append(
            f"mcp registry source {source_id!r} has unsupported {field_name} {value!r}"
        )


def _mcp_lifecycle_diagnostics_errors(manifest: RuntimeManifest) -> list[str]:
    errors: list[str] = []
    raw_diagnostics = manifest.extensions.get("mcp_lifecycle_diagnostics")
    if raw_diagnostics is None:
        return errors
    if not isinstance(raw_diagnostics, Mapping):
        return ["mcp_lifecycle_diagnostics extension must be a mapping"]
    diagnostics = manifest.mcp_lifecycle_diagnostics
    if diagnostics is None:
        return errors
    if diagnostics.startup_mode not in SUPPORTED_MCP_STARTUP_MODES:
        errors.append(
            "mcp lifecycle diagnostics has unsupported startup_mode "
            f"{diagnostics.startup_mode!r}"
        )
    if diagnostics.reconnect not in SUPPORTED_MCP_RECONNECT_VALUES:
        errors.append(
            "mcp lifecycle diagnostics has unsupported reconnect "
            f"{diagnostics.reconnect!r}"
        )
    for field_name, value in (
        ("cleanup_timeout", diagnostics.cleanup_timeout),
        ("active_servers_state_key", diagnostics.active_servers_state_key),
        ("failed_servers_state_key", diagnostics.failed_servers_state_key),
        ("error_map_state_key", diagnostics.error_map_state_key),
    ):
        if value is None:
            errors.append(f"mcp lifecycle diagnostics must define {field_name}")
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


def _context_pipeline_attachment_errors(nodes: Iterable[RuntimeNode]) -> list[str]:
    errors: list[str] = []
    for node in nodes:
        raw_context_pipeline = node.raw.get("context_pipeline")
        raw_context_sources = node.raw.get("context_sources")
        raw_context_contract = node.raw.get("context_contract")
        if (
            raw_context_pipeline is None
            and raw_context_sources is None
            and raw_context_contract is None
        ):
            continue
        if node.kind != "llm_step":
            errors.append(
                f"non-llm_step node {node.id!r} must not define context_pipeline "
                "attachment metadata"
            )
            continue

        label = f"llm_step node {node.id!r}"
        enabled = False
        if raw_context_pipeline is None:
            errors.append(
                f"{label} context_pipeline attachment requires context_pipeline"
            )
        elif not isinstance(raw_context_pipeline, Mapping):
            errors.append(f"{label} context_pipeline must be a mapping")
        else:
            _validate_optional_bool(raw_context_pipeline, "enabled", label, errors)
            enabled = raw_context_pipeline.get("enabled") is True

        requires_explicit_contract = (
            enabled
            or raw_context_sources is not None
            or raw_context_contract is not None
        )
        if not requires_explicit_contract:
            continue
        if raw_context_sources is None:
            errors.append(
                f"{label} context_pipeline attachment requires context_sources"
            )
        else:
            _append_context_source_errors(errors, label, raw_context_sources)
        if raw_context_contract is None:
            errors.append(
                f"{label} context_pipeline attachment requires context_contract"
            )
        else:
            _append_context_contract_errors(errors, label, raw_context_contract)
    return errors


def _append_context_source_errors(
    errors: list[str],
    label: str,
    context_sources: object,
) -> None:
    if not isinstance(context_sources, list):
        errors.append(f"{label} context_sources must be a list")
        return
    if not context_sources:
        errors.append(f"{label} context_sources must not be empty")
        return
    for index, source in enumerate(context_sources):
        if not isinstance(source, Mapping):
            errors.append(f"{label} context_sources[{index}] must be a mapping")
            continue
        for field_name in ("kind", "source"):
            value = source.get(field_name)
            if not isinstance(value, str):
                errors.append(
                    f"{label} context_sources[{index}].{field_name} must be a string"
                )
            elif not value.strip():
                errors.append(
                    f"{label} context_sources[{index}].{field_name} must not be blank"
                )


def _append_context_contract_errors(
    errors: list[str],
    label: str,
    context_contract: object,
) -> None:
    if not isinstance(context_contract, Mapping):
        errors.append(f"{label} context_contract must be a mapping")
        return

    values: dict[str, str] = {}
    for field_name in ("history_input", "current_prompt_input", "output_slot"):
        value = context_contract.get(field_name)
        if not isinstance(value, str):
            errors.append(f"{label} context_contract.{field_name} must be a string")
            continue
        if not value.strip():
            errors.append(f"{label} context_contract.{field_name} must not be blank")
            continue
        values[field_name] = value

    output_slot = values.get("output_slot")
    if output_slot is None:
        return
    if output_slot in {
        values.get("history_input"),
        values.get("current_prompt_input"),
    }:
        errors.append(
            f"{label} context_contract.output_slot must be distinct from input fields"
        )


def _model_requirements_errors(manifest: RuntimeManifest) -> list[str]:
    errors: list[str] = []
    for node in manifest.nodes:
        if not node.model_requirements:
            continue
        if node.kind != "llm_step":
            errors.append(
                f"non-llm_step node {node.id!r} must not define model_requirements"
            )
            continue
        requirements = node.model_requirements
        _extend(errors, _model_required_capability_errors(node, requirements))
        _validate_reasoning_profile(node, requirements, errors)
        _validate_context_requirements(node, requirements, errors)
        _validate_output_requirements(node, requirements, manifest, errors)
        _validate_operational_preferences(node, requirements, errors)
        _validate_fallback_policy(node, requirements, errors)
    return errors


def _model_required_capability_errors(
    node: RuntimeNode,
    requirements: Mapping[str, Any],
) -> list[str]:
    required_capabilities = requirements.get("required_capabilities")
    if required_capabilities is None:
        return []
    if not _is_string_list(required_capabilities):
        return [
            f"llm_step node {node.id!r} model_requirements.required_capabilities "
            "must be a list of strings"
        ]
    unsupported = sorted(
        set(required_capabilities) - SUPPORTED_MODEL_REQUIRED_CAPABILITIES
    )
    if unsupported:
        return [
            f"llm_step node {node.id!r} model_requirements.required_capabilities "
            f"contains unsupported values {unsupported!r}"
        ]
    return []


def _validate_reasoning_profile(
    node: RuntimeNode,
    requirements: Mapping[str, Any],
    errors: list[str],
) -> None:
    reasoning_profile = _optional_mapping(
        requirements,
        "reasoning_profile",
        f"llm_step node {node.id!r} model_requirements",
        errors,
    )
    if not reasoning_profile:
        return
    label = f"llm_step node {node.id!r} model_requirements.reasoning_profile"
    _validate_optional_enum(
        reasoning_profile, "level", SUPPORTED_REASONING_LEVELS, label, errors
    )
    for field_name in ("task_type", "task_subtype"):
        _validate_optional_enum(
            reasoning_profile, field_name, SUPPORTED_REASONING_TASK_TYPES, label, errors
        )
    _validate_optional_enum(
        reasoning_profile,
        "uncertainty_handling",
        SUPPORTED_UNCERTAINTY_HANDLING,
        label,
        errors,
    )


def _validate_context_requirements(
    node: RuntimeNode,
    requirements: Mapping[str, Any],
    errors: list[str],
) -> None:
    context_requirements = _optional_mapping(
        requirements,
        "context_requirements",
        f"llm_step node {node.id!r} model_requirements",
        errors,
    )
    if not context_requirements:
        return
    label = f"llm_step node {node.id!r} model_requirements.context_requirements"
    _validate_optional_enum(
        context_requirements,
        "expected_input_size",
        SUPPORTED_EXPECTED_INPUT_SIZES,
        label,
        errors,
    )
    _validate_optional_bool_or_value(
        context_requirements, "needs_retrieved_context", {"conditional"}, label, errors
    )
    _validate_optional_positive_int_or_unknown(
        context_requirements, "minimum_context_window", label, errors
    )


def _validate_output_requirements(
    node: RuntimeNode,
    requirements: Mapping[str, Any],
    manifest: RuntimeManifest,
    errors: list[str],
) -> None:
    output_requirements = _optional_mapping(
        requirements,
        "output_requirements",
        f"llm_step node {node.id!r} model_requirements",
        errors,
    )
    if not output_requirements:
        return
    label = f"llm_step node {node.id!r} model_requirements.output_requirements"
    _validate_optional_enum(
        output_requirements, "format", SUPPORTED_OUTPUT_FORMATS, label, errors
    )
    _validate_optional_enum(
        output_requirements,
        "evidence_citations",
        SUPPORTED_EVIDENCE_CITATIONS,
        label,
        errors,
    )
    _validate_model_requirement_schema_ref(node, output_requirements, manifest, errors)


def _validate_model_requirement_schema_ref(
    node: RuntimeNode,
    output_requirements: Mapping[str, Any],
    manifest: RuntimeManifest,
    errors: list[str],
) -> None:
    schema_ref = output_requirements.get("schema_ref")
    if schema_ref not in (None, "null") and manifest.output_contracts:
        schema_ref_text = str(schema_ref)
        if schema_ref_text not in manifest.output_contracts:
            errors.append(
                f"llm_step node {node.id!r} model_requirements.output_requirements "
                f"references missing output contract {schema_ref_text!r}"
            )
    prompt_schema_ref = _prompt_output_schema_ref(node)
    if (
        prompt_schema_ref is not None
        and schema_ref not in (None, "null")
        and str(schema_ref) != prompt_schema_ref
    ):
        errors.append(
            f"llm_step node {node.id!r} prompt output_schema_ref {prompt_schema_ref!r} "
            "must match model_requirements.output_requirements.schema_ref "
            f"{str(schema_ref)!r}"
        )


def _validate_operational_preferences(
    node: RuntimeNode,
    requirements: Mapping[str, Any],
    errors: list[str],
) -> None:
    operational_preferences = _optional_mapping(
        requirements,
        "operational_preferences",
        f"llm_step node {node.id!r} model_requirements",
        errors,
    )
    if not operational_preferences:
        return
    label = f"llm_step node {node.id!r} model_requirements.operational_preferences"
    for field_name in ("latency_sensitivity", "cost_sensitivity"):
        _validate_optional_enum(
            operational_preferences,
            field_name,
            SUPPORTED_SENSITIVITY_VALUES,
            label,
            errors,
        )
    _validate_optional_enum(
        operational_preferences,
        "determinism",
        SUPPORTED_DETERMINISM_VALUES,
        label,
        errors,
    )
    _validate_optional_enum(
        operational_preferences,
        "data_boundary",
        SUPPORTED_DATA_BOUNDARIES,
        label,
        errors,
    )


def _validate_fallback_policy(
    node: RuntimeNode,
    requirements: Mapping[str, Any],
    errors: list[str],
) -> None:
    fallback_policy = _optional_mapping(
        requirements,
        "fallback_policy",
        f"llm_step node {node.id!r} model_requirements",
        errors,
    )
    if not fallback_policy:
        return
    label = f"llm_step node {node.id!r} model_requirements.fallback_policy"
    _validate_optional_enum(
        fallback_policy, "if_unavailable", SUPPORTED_FALLBACK_ACTIONS, label, errors
    )
    _validate_optional_enum(
        fallback_policy,
        "minimum_acceptable_level",
        SUPPORTED_REASONING_LEVELS,
        label,
        errors,
    )


def _rag_pipeline_errors(manifest: RuntimeManifest) -> list[str]:
    errors: list[str] = []
    patterns = set(manifest.patterns_present)
    rag_patterns = patterns & RAG_PATTERN_IDS
    if not manifest.rag_pipeline:
        if rag_patterns:
            errors.append(
                "metadata.rag_pipeline is required when metadata.patterns_present "
                f"includes RAG patterns {sorted(rag_patterns)!r}"
            )
        return errors
    pipeline = manifest.rag_pipeline
    if not rag_patterns:
        errors.append(
            "metadata.rag_pipeline requires metadata.patterns_present to include "
            "'rag' or a retrieval-specific RAG pattern"
        )
    _validate_rag_pipeline_fields(pipeline, errors)
    _validate_rag_pattern_requirements(patterns, pipeline, errors)
    return errors


def _react_loop_errors(manifest: RuntimeManifest) -> list[str]:
    patterns = set(manifest.patterns_present)
    if REACT_LOOP_PATTERN_ID not in patterns:
        return []

    errors: list[str] = []
    max_iterations = manifest.execution_policy.get("max_iterations")
    if (
        not isinstance(max_iterations, int)
        or isinstance(max_iterations, bool)
        or max_iterations <= 0
    ):
        errors.append(
            "react_loop requires runtime.execution_policy.max_iterations to be a "
            "positive integer"
        )

    if not any(edge.edge_kind == "loopback" for edge in manifest.edges):
        errors.append("react_loop requires at least one loopback edge")

    if not manifest.state:
        errors.append(
            "react_loop requires runtime.state metadata for observation-state tracking"
        )

    node_kinds = {node.kind for node in manifest.nodes}
    if "llm_step" not in node_kinds or "tool_use_step" not in node_kinds:
        errors.append(
            "react_loop requires at least one llm_step and one tool_use_step node"
        )

    return errors


def _tool_use_completion_policy_errors(manifest: RuntimeManifest) -> list[str]:
    policy = manifest.execution_policy.get("tool_use_completion")
    if policy is None:
        return []
    if not isinstance(policy, Mapping):
        return ["runtime.execution_policy.tool_use_completion must be a mapping"]

    errors: list[str] = []
    label = "runtime.execution_policy.tool_use_completion"
    _validate_optional_enum(
        policy,
        "run_again",
        SUPPORTED_TOOL_USE_COMPLETION_RUN_AGAIN_VALUES,
        label,
        errors,
    )
    _validate_optional_enum(
        policy,
        "stop_on_tool",
        SUPPORTED_TOOL_USE_COMPLETION_STOP_ON_TOOL_VALUES,
        label,
        errors,
    )
    _validate_optional_enum(
        policy,
        "final_output",
        SUPPORTED_TOOL_USE_COMPLETION_FINAL_OUTPUT_VALUES,
        label,
        errors,
    )

    final_output = policy.get("final_output")
    state_key = policy.get("final_output_state_key")
    if state_key is not None and not isinstance(state_key, str):
        errors.append(f"{label}.final_output_state_key must be a string")
    if isinstance(state_key, str) and not state_key.strip():
        errors.append(f"{label}.final_output_state_key must not be blank")
    if final_output == "state_field" and not isinstance(state_key, str):
        errors.append(
            f"{label}.final_output_state_key is required when final_output is 'state_field'"
        )
    if final_output != "state_field" and state_key is not None:
        errors.append(
            f"{label}.final_output_state_key is only allowed when final_output is 'state_field'"
        )
    return errors


def _handoff_metadata_errors(manifest: RuntimeManifest) -> list[str]:
    raw_handoffs = manifest.metadata.get("handoffs")
    if raw_handoffs is None:
        return []
    if not isinstance(raw_handoffs, list):
        return ["metadata.handoffs must be a list"]

    errors: list[str] = []
    for index, handoff in enumerate(manifest.handoffs):
        _extend(errors, _handoff_entry_errors(index, handoff))
    return errors


def _approval_interruption_policy_errors(manifest: RuntimeManifest) -> list[str]:
    policy = manifest.execution_policy.get("approval_interruption")
    if policy is None:
        return []
    if not isinstance(policy, Mapping):
        return ["runtime.execution_policy.approval_interruption must be a mapping"]

    errors: list[str] = []
    label = "runtime.execution_policy.approval_interruption"
    _validate_approval_interruption_enums(policy, label, errors)
    _validate_approval_interruption_state_key_types(policy, label, errors)
    _validate_approval_interruption_persistence(policy, label, errors)

    return errors


def _async_session_policy_errors(manifest: RuntimeManifest) -> list[str]:
    policy = manifest.execution_policy.get("async_session")
    if policy is None:
        return []
    if not isinstance(policy, Mapping):
        return ["runtime.execution_policy.async_session must be a mapping"]

    errors: list[str] = []
    label = "runtime.execution_policy.async_session"
    _validate_optional_enum(
        policy,
        "mode",
        SUPPORTED_ASYNC_SESSION_MODE_VALUES,
        label,
        errors,
    )
    _validate_optional_enum(
        policy,
        "persist",
        SUPPORTED_ASYNC_SESSION_PERSIST_VALUES,
        label,
        errors,
    )
    _validate_optional_enum(
        policy,
        "history",
        SUPPORTED_ASYNC_SESSION_HISTORY_VALUES,
        label,
        errors,
    )
    _validate_async_session_state_key_types(policy, label, errors)
    _validate_async_session_persistence(policy, label, errors)
    return errors


def _sandbox_runtime_policy_errors(manifest: RuntimeManifest) -> list[str]:
    policy = manifest.execution_policy.get("sandbox_runtime")
    if policy is None:
        return []
    if not isinstance(policy, Mapping):
        return ["runtime.execution_policy.sandbox_runtime must be a mapping"]

    errors: list[str] = []
    label = "runtime.execution_policy.sandbox_runtime"
    _validate_optional_enum(
        policy,
        "mode",
        SUPPORTED_SANDBOX_RUNTIME_MODE_VALUES,
        label,
        errors,
    )
    _validate_optional_enum(
        policy,
        "filesystem",
        SUPPORTED_SANDBOX_RUNTIME_FILESYSTEM_VALUES,
        label,
        errors,
    )
    _validate_optional_enum(
        policy,
        "persist_workspace",
        SUPPORTED_SANDBOX_RUNTIME_PERSIST_WORKSPACE_VALUES,
        label,
        errors,
    )
    _validate_optional_enum(
        policy,
        "command_policy",
        SUPPORTED_SANDBOX_RUNTIME_COMMAND_POLICY_VALUES,
        label,
        errors,
    )
    _validate_sandbox_runtime_state_key_types(policy, label, errors)
    _validate_sandbox_runtime_consistency(policy, label, errors)
    return errors


def _skill_source_resolution_policy_errors(manifest: RuntimeManifest) -> list[str]:
    policy = manifest.execution_policy.get("skill_source_resolution")
    if policy is None:
        return []
    if not isinstance(policy, Mapping):
        return ["runtime.execution_policy.skill_source_resolution must be a mapping"]

    errors: list[str] = []
    label = "runtime.execution_policy.skill_source_resolution"
    _validate_optional_bool(policy, "enabled", label, errors)
    _validate_optional_bool(policy, "load_support_files", label, errors)
    _validate_optional_enum(
        policy,
        "prompt_role",
        SUPPORTED_SKILL_SOURCE_PROMPT_ROLE_VALUES,
        label,
        errors,
    )
    _skill_source_allowed_sources_errors(policy, label, errors)
    _skill_source_size_limit_errors(policy, label, errors)
    if policy.get("load_support_files") is True:
        errors.append(f"{label}.load_support_files is not supported in v1")
    return errors


def _skill_source_allowed_sources_errors(
    policy: Mapping[str, Any],
    label: str,
    errors: list[str],
) -> None:
    allowed_sources = policy.get("allowed_sources")
    if allowed_sources is None:
        return
    if not _is_string_list(allowed_sources):
        errors.append(f"{label}.allowed_sources must be a list of strings")
        return
    if not allowed_sources:
        errors.append(f"{label}.allowed_sources must not be empty when provided")
        return
    unsupported = sorted(
        source
        for source in allowed_sources
        if source not in SUPPORTED_SKILL_SOURCE_ALLOWED_SOURCES
    )
    if unsupported:
        errors.append(
            f"{label}.allowed_sources contains unsupported values {unsupported!r}"
        )


def _skill_source_size_limit_errors(
    policy: Mapping[str, Any],
    label: str,
    errors: list[str],
) -> None:
    for field_name in ("max_skill_bytes", "max_node_skill_bytes"):
        value = policy.get(field_name)
        if value is None:
            continue
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            errors.append(f"{label}.{field_name} must be a positive integer")

    skill_limit = policy.get("max_skill_bytes")
    node_limit = policy.get("max_node_skill_bytes")
    if (
        isinstance(skill_limit, int)
        and not isinstance(skill_limit, bool)
        and isinstance(node_limit, int)
        and not isinstance(node_limit, bool)
        and node_limit < skill_limit
    ):
        errors.append(
            f"{label}.max_node_skill_bytes must be greater than or equal to "
            "max_skill_bytes"
        )


def _validate_async_session_state_key_types(
    policy: Mapping[str, Any],
    label: str,
    errors: list[str],
) -> None:
    for field_name in _async_session_state_key_fields():
        value = policy.get(field_name)
        if value is None:
            continue
        if not isinstance(value, str):
            errors.append(f"{label}.{field_name} must be a string")
            continue
        if not value.strip():
            errors.append(f"{label}.{field_name} must not be blank")


def _validate_async_session_persistence(
    policy: Mapping[str, Any],
    label: str,
    errors: list[str],
) -> None:
    persist = policy.get("persist")
    has_state_key = any(
        policy.get(field_name) is not None
        for field_name in _async_session_state_key_fields()
    )
    if persist == "none" and has_state_key:
        errors.append(
            f"{label} state-key fields are only allowed when persist is not 'none'"
        )
    if persist in {"in_memory", "external_checkpoint"}:
        for field_name in _async_session_required_persisted_fields():
            value = policy.get(field_name)
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    f"{label}.{field_name} is required when persist is {persist!r}"
                )
    history = policy.get("history")
    session_messages_state_key = policy.get("session_messages_state_key")
    if history == "none" and session_messages_state_key is not None:
        errors.append(
            f"{label}.session_messages_state_key is only allowed when history is not 'none'"
        )


def _async_session_state_key_fields() -> tuple[str, ...]:
    return ("session_id_state_key", "session_messages_state_key")


def _async_session_required_persisted_fields() -> tuple[str, ...]:
    return ("session_id_state_key",)


def _validate_approval_interruption_enums(
    policy: Mapping[str, Any],
    label: str,
    errors: list[str],
) -> None:
    _validate_optional_enum(
        policy,
        "mode",
        SUPPORTED_APPROVAL_INTERRUPTION_MODE_VALUES,
        label,
        errors,
    )
    _validate_optional_enum(
        policy,
        "persist",
        SUPPORTED_APPROVAL_INTERRUPTION_PERSIST_VALUES,
        label,
        errors,
    )
    _validate_optional_enum(
        policy,
        "resume_from",
        SUPPORTED_APPROVAL_INTERRUPTION_RESUME_FROM_VALUES,
        label,
        errors,
    )


def _validate_approval_interruption_state_key_types(
    policy: Mapping[str, Any],
    label: str,
    errors: list[str],
) -> None:
    for field_name in _approval_interruption_state_key_fields():
        value = policy.get(field_name)
        if value is None:
            continue
        if not isinstance(value, str):
            errors.append(f"{label}.{field_name} must be a string")
            continue
        if not value.strip():
            errors.append(f"{label}.{field_name} must not be blank")


def _validate_approval_interruption_persistence(
    policy: Mapping[str, Any],
    label: str,
    errors: list[str],
) -> None:
    persist = policy.get("persist")
    has_state_key = any(
        policy.get(field_name) is not None
        for field_name in _approval_interruption_state_key_fields()
    )
    if persist == "none" and has_state_key:
        errors.append(
            f"{label} state-key fields are only allowed when persist is not 'none'"
        )
    if persist in {"in_memory", "external_checkpoint"}:
        for field_name in _approval_interruption_required_persisted_fields():
            value = policy.get(field_name)
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    f"{label}.{field_name} is required when persist is {persist!r}"
                )


def _approval_interruption_state_key_fields() -> tuple[str, ...]:
    return (
        "pending_tool_calls_state_key",
        "pending_approvals_state_key",
        "interruption_state_key",
        "resume_token_state_key",
    )


def _approval_interruption_required_persisted_fields() -> tuple[str, ...]:
    return (
        "pending_tool_calls_state_key",
        "pending_approvals_state_key",
        "interruption_state_key",
    )


def _validate_sandbox_runtime_state_key_types(
    policy: Mapping[str, Any],
    label: str,
    errors: list[str],
) -> None:
    for field_name in _sandbox_runtime_state_key_fields():
        value = policy.get(field_name)
        if value is None:
            continue
        if not isinstance(value, str):
            errors.append(f"{label}.{field_name} must be a string")
            continue
        if not value.strip():
            errors.append(f"{label}.{field_name} must not be blank")


def _validate_sandbox_runtime_consistency(
    policy: Mapping[str, Any],
    label: str,
    errors: list[str],
) -> None:
    persist_workspace = policy.get("persist_workspace")
    has_state_key = any(
        policy.get(field_name) is not None
        for field_name in _sandbox_runtime_state_key_fields()
    )
    if persist_workspace == "none" and has_state_key:
        errors.append(
            f"{label} state-key fields are only allowed when persist_workspace is not 'none'"
        )
    if persist_workspace in {"per_run", "named_session"}:
        for field_name in _sandbox_runtime_required_persisted_fields():
            value = policy.get(field_name)
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    f"{label}.{field_name} is required when persist_workspace is {persist_workspace!r}"
                )
    command_policy = policy.get("command_policy")
    filesystem = policy.get("filesystem")
    if command_policy != "forbid" and filesystem == "read_only":
        errors.append(
            f"{label}.filesystem must not be 'read_only' when command_policy is not 'forbid'"
        )


def _sandbox_runtime_state_key_fields() -> tuple[str, ...]:
    return (
        "writable_root_state_key",
        "working_directory_state_key",
    )


def _sandbox_runtime_required_persisted_fields() -> tuple[str, ...]:
    return (
        "writable_root_state_key",
        "working_directory_state_key",
    )


def _handoff_entry_errors(index: int, handoff: Any) -> list[str]:
    errors: list[str] = []
    handoff_id = handoff.id
    if not handoff_id:
        errors.append(f"handoff metadata at position {index} is missing id")
    if not handoff.target:
        errors.append(f"handoff metadata {handoff_id!r} must define target")
    _append_handoff_enum_error(
        errors,
        handoff_id,
        field_name="on_handoff",
        value=handoff.on_handoff,
        supported=SUPPORTED_HANDOFF_ON_HANDOFF_VALUES,
    )
    _append_non_blank_handoff_field_error(
        errors,
        handoff_id,
        field_name="input_filter",
        value=handoff.input_filter,
    )
    _append_handoff_enum_error(
        errors,
        handoff_id,
        field_name="nested_history",
        value=handoff.nested_history,
        supported=SUPPORTED_HANDOFF_NESTED_HISTORY_VALUES,
    )
    _append_non_blank_handoff_field_error(
        errors,
        handoff_id,
        field_name="enabled_when",
        value=handoff.enabled_when,
    )
    return errors


def _append_handoff_enum_error(
    errors: list[str],
    handoff_id: str | None,
    *,
    field_name: str,
    value: str | None,
    supported: set[str],
) -> None:
    if value is None:
        return
    if value not in supported:
        errors.append(
            f"handoff metadata {handoff_id!r} has unsupported {field_name} {value!r}"
        )


def _append_non_blank_handoff_field_error(
    errors: list[str],
    handoff_id: str | None,
    *,
    field_name: str,
    value: str | None,
) -> None:
    if value is None:
        return
    if not value.strip():
        errors.append(f"handoff metadata {handoff_id!r} {field_name} must not be blank")


def _agent_as_tool_metadata_errors(manifest: RuntimeManifest) -> list[str]:
    errors: list[str] = []
    for node in manifest.nodes:
        raw_agent_tool = node.raw.get("agent_as_tool") or node.raw.get("agent_tool")
        if raw_agent_tool is None:
            continue
        label = f"node {node.id!r} agent-as-tool metadata"
        if not isinstance(raw_agent_tool, Mapping):
            errors.append(f"{label} must be a mapping")
            continue
        if node.kind != "tool_use_step":
            errors.append(f"{label} is only allowed on tool_use_step nodes")
            continue
        agent_as_tool = node.agent_as_tool
        if agent_as_tool is None:
            continue
        if not agent_as_tool.skill_id:
            errors.append(f"{label} must define skill_id")
        if not agent_as_tool.task_boundary:
            errors.append(f"{label} must define task_boundary")
        if agent_as_tool.output_mode is not None:
            if (
                agent_as_tool.output_mode
                not in SUPPORTED_AGENT_AS_TOOL_OUTPUT_MODE_VALUES
            ):
                errors.append(
                    f"{label} has unsupported output_mode {agent_as_tool.output_mode!r}"
                )
    return errors


def _validate_rag_pipeline_fields(
    pipeline: Mapping[str, Any],
    errors: list[str],
) -> None:
    _validate_optional_enum(
        pipeline,
        "orchestration_mode",
        SUPPORTED_RAG_ORCHESTRATION_MODES,
        "metadata.rag_pipeline",
        errors,
    )
    _validate_optional_enum(
        pipeline,
        "retrieval_mode",
        SUPPORTED_RAG_RETRIEVAL_MODES,
        "metadata.rag_pipeline",
        errors,
    )
    for field_name in ("embedding_capability", "graph_capability"):
        _validate_optional_enum(
            pipeline,
            field_name,
            SUPPORTED_RAG_CAPABILITY_VALUES,
            "metadata.rag_pipeline",
            errors,
        )
    for field_name in ("index_owner", "graph_store_owner"):
        _validate_optional_enum(
            pipeline,
            field_name,
            SUPPORTED_RAG_OWNER_VALUES,
            "metadata.rag_pipeline",
            errors,
        )
    _validate_optional_enum(
        pipeline,
        "reranking",
        SUPPORTED_RAG_RERANKING_VALUES,
        "metadata.rag_pipeline",
        errors,
    )
    _validate_optional_enum(
        pipeline,
        "fusion",
        SUPPORTED_RAG_FUSION_VALUES,
        "metadata.rag_pipeline",
        errors,
    )
    _validate_optional_enum(
        pipeline,
        "compression",
        SUPPORTED_RAG_COMPRESSION_VALUES,
        "metadata.rag_pipeline",
        errors,
    )
    _validate_optional_enum(
        pipeline,
        "correction",
        SUPPORTED_RAG_CORRECTION_VALUES,
        "metadata.rag_pipeline",
        errors,
    )
    _validate_optional_enum(
        pipeline,
        "freshness_policy",
        SUPPORTED_RAG_FRESHNESS_VALUES,
        "metadata.rag_pipeline",
        errors,
    )
    _validate_optional_bool(
        pipeline, "provenance_required", "metadata.rag_pipeline", errors
    )
    metadata_filters = pipeline.get("metadata_filters")
    if metadata_filters is not None and not _is_string_list(metadata_filters):
        errors.append(
            "metadata.rag_pipeline.metadata_filters must be a list of strings"
        )
    _validate_rag_retrievers(pipeline, errors)
    _validate_rag_candidate_budget(pipeline, errors)
    _validate_rag_context_assembly(pipeline, errors)
    _validate_rag_permissions(pipeline, errors)
    _validate_rag_source_readiness(pipeline, errors)
    _validate_rag_cache(pipeline, errors)
    _validate_rag_degraded_states(pipeline, errors)


def _validate_rag_retrievers(
    pipeline: Mapping[str, Any],
    errors: list[str],
) -> None:
    retrievers = pipeline.get("retrievers")
    if retrievers is None:
        return
    if not isinstance(retrievers, list):
        errors.append("metadata.rag_pipeline.retrievers must be a list")
        return
    for index, retriever in enumerate(retrievers):
        label = f"metadata.rag_pipeline.retrievers[{index}]"
        if not isinstance(retriever, Mapping):
            errors.append(f"{label} must be a mapping")
            continue
        _validate_optional_nonblank_string(retriever, "id", label, errors)
        _validate_optional_nonblank_string(retriever, "tool_id", label, errors)
        _validate_optional_enum(
            retriever,
            "mode",
            SUPPORTED_RAG_RETRIEVAL_MODES,
            label,
            errors,
        )
        _validate_optional_bool(retriever, "required", label, errors)
        _validate_optional_bool(retriever, "provides_provenance", label, errors)


def _validate_rag_candidate_budget(
    pipeline: Mapping[str, Any],
    errors: list[str],
) -> None:
    candidate_budget = _optional_mapping(
        pipeline, "candidate_budget", "metadata.rag_pipeline", errors
    )
    if candidate_budget is None:
        return
    for field_name in ("stage1_k", "stage2_k", "final_k"):
        _validate_optional_positive_int(
            candidate_budget,
            field_name,
            "metadata.rag_pipeline.candidate_budget",
            errors,
        )


def _validate_rag_context_assembly(
    pipeline: Mapping[str, Any],
    errors: list[str],
) -> None:
    context_assembly = _optional_mapping(
        pipeline, "context_assembly", "metadata.rag_pipeline", errors
    )
    if context_assembly is None:
        _validate_rag_provenance_requirements(pipeline, None, errors)
        return
    _validate_optional_enum(
        context_assembly,
        "target",
        SUPPORTED_RAG_CONTEXT_ASSEMBLY_TARGETS,
        "metadata.rag_pipeline.context_assembly",
        errors,
    )
    _validate_optional_positive_int(
        context_assembly,
        "max_context_tokens",
        "metadata.rag_pipeline.context_assembly",
        errors,
    )
    required_fields = context_assembly.get("required_evidence_fields")
    if required_fields is not None and not _is_string_list(required_fields):
        errors.append(
            "metadata.rag_pipeline.context_assembly.required_evidence_fields "
            "must be a list of strings"
        )
    _validate_rag_provenance_requirements(pipeline, context_assembly, errors)


def _validate_rag_provenance_requirements(
    pipeline: Mapping[str, Any],
    context_assembly: Mapping[str, Any] | None,
    errors: list[str],
) -> None:
    if pipeline.get("provenance_required") is not True:
        return
    required_fields = (
        context_assembly.get("required_evidence_fields")
        if isinstance(context_assembly, Mapping)
        else None
    )
    if _is_string_list(required_fields) and required_fields:
        return
    retrievers = pipeline.get("retrievers")
    if isinstance(retrievers, list):
        for retriever in retrievers:
            if not isinstance(retriever, Mapping):
                continue
            if (
                retriever.get("required") is True
                and retriever.get("provides_provenance") is True
            ):
                return
    errors.append(
        "metadata.rag_pipeline.provenance_required requires "
        "context_assembly.required_evidence_fields or a required provenance retriever"
    )


def _validate_rag_permissions(
    pipeline: Mapping[str, Any],
    errors: list[str],
) -> None:
    permissions = _optional_mapping(
        pipeline, "permissions", "metadata.rag_pipeline", errors
    )
    if permissions is None:
        return
    _validate_optional_enum(
        permissions,
        "permission_filtering",
        SUPPORTED_RAG_PERMISSION_FILTERING_VALUES,
        "metadata.rag_pipeline.permissions",
        errors,
    )
    _validate_optional_enum(
        permissions,
        "permission_failure_policy",
        SUPPORTED_RAG_PERMISSION_FAILURE_VALUES,
        "metadata.rag_pipeline.permissions",
        errors,
    )
    _validate_optional_bool(
        permissions, "audit_required", "metadata.rag_pipeline.permissions", errors
    )


def _validate_rag_source_readiness(
    pipeline: Mapping[str, Any],
    errors: list[str],
) -> None:
    source_readiness = _optional_mapping(
        pipeline, "source_readiness", "metadata.rag_pipeline", errors
    )
    if source_readiness is None:
        return
    _validate_optional_enum(
        source_readiness,
        "source_registry",
        SUPPORTED_RAG_SOURCE_REGISTRY_VALUES,
        "metadata.rag_pipeline.source_readiness",
        errors,
    )
    _validate_optional_enum(
        source_readiness,
        "refresh_mode",
        SUPPORTED_RAG_REFRESH_MODE_VALUES,
        "metadata.rag_pipeline.source_readiness",
        errors,
    )
    _validate_optional_enum(
        source_readiness,
        "stale_state",
        SUPPORTED_RAG_STALE_STATE_VALUES,
        "metadata.rag_pipeline.source_readiness",
        errors,
    )


def _validate_rag_cache(
    pipeline: Mapping[str, Any],
    errors: list[str],
) -> None:
    cache = _optional_mapping(pipeline, "cache", "metadata.rag_pipeline", errors)
    if cache is None:
        return
    for field_name in ("retrieval_results", "semantic_query_cache"):
        _validate_optional_enum(
            cache,
            field_name,
            SUPPORTED_RAG_CACHE_VALUES,
            "metadata.rag_pipeline.cache",
            errors,
        )


def _validate_rag_degraded_states(
    pipeline: Mapping[str, Any],
    errors: list[str],
) -> None:
    degraded_states = pipeline.get("degraded_states")
    if degraded_states is None:
        return
    if not isinstance(degraded_states, list) or not all(
        isinstance(item, str) for item in degraded_states
    ):
        errors.append("metadata.rag_pipeline.degraded_states must be a list of strings")
        return
    unsupported = sorted(set(degraded_states) - SUPPORTED_RAG_DEGRADED_STATES)
    if unsupported:
        errors.append(
            "metadata.rag_pipeline.degraded_states contains unsupported values "
            f"{unsupported!r}"
        )


def _validate_rag_pattern_requirements(
    patterns: set[str],
    pipeline: Mapping[str, Any],
    errors: list[str],
) -> None:
    if "embedding_retrieval" in patterns:
        if pipeline.get("retrieval_mode") not in {"embedding_semantic", "hybrid"}:
            errors.append(
                "embedding_retrieval requires metadata.rag_pipeline.retrieval_mode "
                "embedding_semantic or hybrid"
            )
        if pipeline.get("embedding_capability") != "required":
            errors.append(
                "embedding_retrieval requires metadata.rag_pipeline.embedding_capability "
                "required"
            )
    if "graph_retrieval" in patterns or "graphrag" in patterns:
        if pipeline.get("graph_capability") != "required":
            errors.append(
                "graph retrieval patterns require metadata.rag_pipeline.graph_capability "
                "required"
            )


def _prompt_output_schema_ref(node: RuntimeNode) -> str | None:
    prompt = node.raw.get("prompt")
    if not isinstance(prompt, Mapping):
        return None
    value = prompt.get("output_schema_ref")
    return str(value) if value is not None else None


def _optional_mapping(
    mapping: Mapping[str, Any],
    field_name: str,
    label: str,
    errors: list[str],
) -> Mapping[str, Any] | None:
    value = mapping.get(field_name)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        errors.append(f"{label}.{field_name} must be a mapping")
        return None
    return value


def _validate_optional_enum(
    mapping: Mapping[str, Any],
    field_name: str,
    supported: set[str],
    label: str,
    errors: list[str],
) -> None:
    value = mapping.get(field_name)
    if value is None:
        return
    if value not in supported:
        errors.append(f"{label}.{field_name} has unsupported value {value!r}")


def _validate_optional_bool(
    mapping: Mapping[str, Any],
    field_name: str,
    label: str,
    errors: list[str],
) -> None:
    value = mapping.get(field_name)
    if value is not None and not isinstance(value, bool):
        errors.append(f"{label}.{field_name} must be boolean")


def _validate_optional_nonblank_string(
    mapping: Mapping[str, Any],
    field_name: str,
    label: str,
    errors: list[str],
) -> None:
    value = mapping.get(field_name)
    if value is None:
        return
    if not isinstance(value, str):
        errors.append(f"{label}.{field_name} must be a string")
    elif not value.strip():
        errors.append(f"{label}.{field_name} must not be blank")


def _validate_optional_positive_int(
    mapping: Mapping[str, Any],
    field_name: str,
    label: str,
    errors: list[str],
) -> None:
    value = mapping.get(field_name)
    if value is None:
        return
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        errors.append(f"{label}.{field_name} must be a positive integer")


def _validate_optional_ratio(
    mapping: Mapping[str, Any],
    field_name: str,
    label: str,
    errors: list[str],
) -> None:
    value = mapping.get(field_name)
    if value is None:
        return
    if (
        not isinstance(value, int | float)
        or isinstance(value, bool)
        or value <= 0
        or value > 1
    ):
        errors.append(f"{label}.{field_name} must be a number between 0 and 1")


def _validate_optional_supported_string_list(
    mapping: Mapping[str, Any],
    field_name: str,
    supported: set[str],
    label: str,
    errors: list[str],
) -> None:
    value = mapping.get(field_name)
    if value is None:
        return
    if not _is_string_list(value):
        errors.append(f"{label}.{field_name} must be a list of strings")
        return
    unsupported = sorted(set(value) - supported)
    if unsupported:
        errors.append(
            f"{label}.{field_name} contains unsupported values {unsupported!r}"
        )


def _validate_optional_bool_or_value(
    mapping: Mapping[str, Any],
    field_name: str,
    supported_values: set[str],
    label: str,
    errors: list[str],
) -> None:
    value = mapping.get(field_name)
    if value is None or isinstance(value, bool):
        return
    if value not in supported_values:
        errors.append(
            f"{label}.{field_name} must be boolean or one of {sorted(supported_values)!r}"
        )


def _validate_optional_positive_int_or_unknown(
    mapping: Mapping[str, Any],
    field_name: str,
    label: str,
    errors: list[str],
) -> None:
    value = mapping.get(field_name)
    if value is None or value == "unknown":
        return
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        errors.append(f"{label}.{field_name} must be a positive integer or 'unknown'")


def _is_string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _prompt_cache_policy_errors(manifest: RuntimeManifest) -> list[str]:
    try:
        prompt_cache_policy_from_value(manifest.execution_policy.get("prompt_cache"))
    except Exception as exc:  # noqa: BLE001 - normalized into validation errors.
        return [str(exc)]
    return []


def _prepare_model_input_context_policy_errors(
    manifest: RuntimeManifest,
) -> list[str]:
    policy = manifest.execution_policy.get("prepare_model_input")
    if not isinstance(policy, Mapping):
        return []
    errors: list[str] = []
    label = "runtime.execution_policy.prepare_model_input"
    _context_compaction_auto_errors(policy, label, errors)
    _context_compression_errors(policy, label, errors)
    return errors


def _context_compaction_auto_errors(
    policy: Mapping[str, Any],
    label: str,
    errors: list[str],
) -> None:
    compaction = policy.get("context_compaction")
    if compaction is None:
        return
    if not isinstance(compaction, Mapping):
        errors.append(f"{label}.context_compaction must be a mapping")
        return
    auto = compaction.get("auto")
    if auto is None:
        return
    auto_label = f"{label}.context_compaction.auto"
    if not isinstance(auto, Mapping):
        errors.append(f"{auto_label} must be a mapping")
        return
    _validate_optional_bool(auto, "enabled", auto_label, errors)
    _validate_optional_ratio(auto, "threshold_ratio", auto_label, errors)
    _validate_optional_positive_int(auto, "reserve_tokens", auto_label, errors)
    _validate_optional_enum(
        auto, "scope", SUPPORTED_CONTEXT_COMPACTION_SCOPES, auto_label, errors
    )
    _validate_optional_enum(
        auto,
        "implementation",
        SUPPORTED_CONTEXT_COMPACTION_IMPLEMENTATIONS,
        auto_label,
        errors,
    )
    _validate_optional_enum(
        auto,
        "strategy",
        SUPPORTED_CONTEXT_COMPACTION_STRATEGIES,
        auto_label,
        errors,
    )
    _validate_optional_enum(
        auto, "mode", SUPPORTED_CONTEXT_COMPACTION_MODES, auto_label, errors
    )
    _validate_optional_enum(
        auto,
        "manual_mode",
        SUPPORTED_CONTEXT_COMPACTION_MANUAL_MODES,
        auto_label,
        errors,
    )
    _validate_optional_enum(
        auto, "trigger", SUPPORTED_CONTEXT_COMPACTION_TRIGGERS, auto_label, errors
    )
    _validate_optional_enum(
        auto,
        "reset_behavior",
        SUPPORTED_CONTEXT_RESET_BEHAVIORS,
        auto_label,
        errors,
    )
    if auto.get("reset_behavior") not in (None, "none", "new_window"):
        errors.append(f"{auto_label}.reset_behavior must not request compaction")
    _validate_optional_supported_string_list(
        auto,
        "lifecycle_stages",
        SUPPORTED_CONTEXT_LIFECYCLE_STAGES,
        auto_label,
        errors,
    )
    _validate_optional_supported_string_list(
        auto,
        "metrics",
        SUPPORTED_CONTEXT_METRICS,
        auto_label,
        errors,
    )


def _context_compression_errors(
    policy: Mapping[str, Any],
    label: str,
    errors: list[str],
) -> None:
    compression = policy.get("context_compression")
    if compression is None:
        return
    compression_label = f"{label}.context_compression"
    if not isinstance(compression, Mapping):
        errors.append(f"{compression_label} must be a mapping")
        return
    _validate_optional_enum(
        compression,
        "profile",
        SUPPORTED_CONTEXT_COMPRESSION_PROFILES,
        compression_label,
        errors,
    )
    lanes = compression.get("lanes")
    if lanes is not None:
        _context_lane_budget_errors(lanes, f"{compression_label}.lanes", errors)
    selection = compression.get("selection")
    if selection is not None:
        _context_selection_errors(selection, f"{compression_label}.selection", errors)


def _context_lane_budget_errors(
    lanes: Any,
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(lanes, Mapping):
        errors.append(f"{label} must be a mapping")
        return
    for field_name in SUPPORTED_CONTEXT_LANE_BUDGET_FIELDS:
        _validate_optional_positive_int(lanes, field_name, label, errors)


def _context_selection_errors(
    selection: Any,
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(selection, Mapping):
        errors.append(f"{label} must be a mapping")
        return
    _validate_optional_enum(
        selection,
        "strategy",
        SUPPORTED_CONTEXT_SELECTION_STRATEGIES,
        label,
        errors,
    )
    _validate_optional_positive_int(selection, "max_selected_turns", label, errors)
    _validate_optional_bool(selection, "chronological_reassembly", label, errors)


def _file_context_policy_errors(manifest: RuntimeManifest) -> list[str]:
    policy = manifest.execution_policy.get("prepare_model_input")
    if not isinstance(policy, Mapping):
        return []

    file_context = policy.get("file_context")
    if file_context is None:
        return []
    if not isinstance(file_context, Mapping):
        return [
            "runtime.execution_policy.prepare_model_input.file_context must be a mapping"
        ]

    errors: list[str] = []
    label = "runtime.execution_policy.prepare_model_input.file_context"
    _validate_optional_bool(file_context, "enabled", label, errors)
    roots = _file_context_roots_errors(file_context, label, errors)
    _file_context_bound_errors(file_context, label, errors)
    _file_context_prompt_errors(file_context, label, errors)
    _file_context_required_field_errors(file_context, manifest, label, roots, errors)

    return errors


def _file_context_roots_errors(
    file_context: Mapping[str, Any],
    label: str,
    errors: list[str],
) -> list[str] | None:
    roots = file_context.get("roots")
    if roots is None:
        return None
    if not _is_string_list(roots):
        errors.append(f"{label}.roots must be a list of strings")
        return None
    if not roots:
        errors.append(f"{label}.roots must not be empty when provided")
        return []
    for root in roots:
        if not root.strip():
            errors.append(f"{label}.roots must not contain blank paths")
        if root.startswith("/"):
            errors.append(f"{label}.roots must use package-relative paths")
        if ".." in root.split("/"):
            errors.append(f"{label}.roots must not escape the package root")
    return roots


def _file_context_bound_errors(
    file_context: Mapping[str, Any],
    label: str,
    errors: list[str],
) -> None:
    for field_name in ("max_depth", "max_files", "max_bytes", "max_tokens"):
        _validate_optional_positive_int_or_unknown(
            file_context, field_name, label, errors
        )


def _file_context_prompt_errors(
    file_context: Mapping[str, Any],
    label: str,
    errors: list[str],
) -> None:
    prompt_role = file_context.get("prompt_role")
    if prompt_role is not None and prompt_role not in {"system", "developer"}:
        errors.append(f"{label}.prompt_role has unsupported value {prompt_role!r}")

    header = file_context.get("header")
    if header is not None and not isinstance(header, str):
        errors.append(f"{label}.header must be a string")


def _file_context_required_field_errors(
    file_context: Mapping[str, Any],
    manifest: RuntimeManifest,
    label: str,
    roots: list[str] | None,
    errors: list[str],
) -> None:
    if file_context.get("enabled") is True and manifest.entrypoint and roots is None:
        errors.append(f"{label}.roots is required when file context is enabled")


def _extend(target: list[str], values: Iterable[str]) -> None:
    target.extend(values)


def _format_errors(artifact_name: str, errors: Iterable[str]) -> str:
    details = "; ".join(errors)
    return f"Invalid {artifact_name}: {details}"
