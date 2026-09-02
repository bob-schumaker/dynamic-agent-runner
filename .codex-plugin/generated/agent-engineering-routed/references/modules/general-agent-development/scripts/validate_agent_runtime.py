#!/usr/bin/env python3
"""Validate agent-runtime.yaml manifests for the agent-development skill.

The helper prefers PyYAML when available and otherwise falls back to Ruby's
standard YAML parser when `ruby` is present. The semantic checks are
repository-local conventions that JSON Schema cannot express alone.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - environment dependent
    yaml = None

VALID_NODE_KINDS = {"llm_step", "tool_use_step", "decision_step"}
VALID_DECISION_SUBTYPES = {"tool_response_compare", "simple_check", "llm_route"}
VALID_EDGE_KINDS = {
    "sequential",
    "branch",
    "loopback",
    "parallel_fanout",
    "parallel_join",
    "event",
    "capability",
}
VALID_PACKAGING_MODES = {"hybrid_bundle", "inline_only", "bundled_only"}
VALID_SKILL_BINDING_USAGES = {
    "instruction_context",
    "tool_adapter",
    "policy_context",
    "output_formatter",
    "shared_reference",
}
VALID_TOOL_TYPES = {
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
VALID_TOOL_SIDE_EFFECTS = {"none", "read", "write", "mutate", "destructive"}
VALID_HANDOFF_KINDS = {"ownership_transfer"}
VALID_DELEGATION_MODES = {"bounded_subtask"}
VALID_APPROVAL_SENSITIVITIES = {
    "low_risk_read",
    "medium_risk_write",
    "high_risk_write",
    "destructive_action",
    "human_review_required",
}
VALID_RESUMABILITY = {"expected", "optional", "not_supported", "unknown"}
VALID_PROMPT_CACHE_STRATEGIES = {"stable_prefix"}
VALID_PROMPT_CACHE_KEY_HINTS = {
    "package_id",
    "package_id_and_version",
    "none",
    "runtime_default",
}
VALID_PROMPT_CACHE_PREFIX_PARTS = {
    "system",
    "developer",
    "skill_instructions",
    "tool_schemas",
    "role_definitions",
    "output_contracts",
    "workflow_structure",
}
VALID_PROMPT_CACHE_VARIABLE_PARTS = {
    "user_prompt",
    "run_state",
    "retrieved_context",
    "tool_results",
}
VALID_MODEL_REQUIRED_CAPABILITIES = {
    "supports_structured",
    "supports_functions",
    "embeddings",
    "supports_vision",
    "input_modalities",
    "supports_json_mode",
    "code_reasoning",
    "math_reasoning",
}
VALID_REASONING_LEVELS = {"minimal", "low", "medium", "high", "extended"}
VALID_REASONING_TASK_TYPES = {"classification", "extraction", "generation", "planning"}
VALID_REASONING_TASK_SUBTYPES = {
    "critique",
    "synthesis",
    "tool_selection",
    "route_selection",
}
VALID_UNCERTAINTY_HANDLING = {
    "answer_with_caveats",
    "ask_clarification",
    "escalate",
}
VALID_EXPECTED_INPUT_SIZES = {"small", "medium", "large", "very_large", "unknown"}
VALID_OUTPUT_FORMATS = {"free_text", "structured_json", "schema_ref", "tool_call"}
VALID_EVIDENCE_CITATIONS = {"required", "preferred", "not_needed"}
VALID_SENSITIVITY_VALUES = {"low", "medium", "high"}
VALID_DETERMINISM_VALUES = {"preferred", "balanced", "creative"}
VALID_DATA_BOUNDARIES = {
    "local_only",
    "private_runtime",
    "provider_allowed",
    "unknown",
}
VALID_FALLBACK_ACTIONS = {
    "use_lower_capability",
    "use_higher_capability",
    "escalate",
}
VALID_EXIT_ON_EXHAUSTION = {
    "finalize_with_caveats",
    "escalate",
    "fail_closed",
    "return_partial",
}
PROMPT_CACHE_EXTENSION_PART_RE = re.compile(r"^x-[A-Za-z0-9_-]+$")
LEGACY_FLAT_OPTIONAL_FIELDS = {
    "execution_policy",
    "state",
    "patterns_present",
    "participant_groups",
    "modes",
    "phases",
    "roles",
    "runtime_surface",
    "workspace_boundary",
    "completion_contract",
    "result_surfaces",
    "permission_profile",
    "approval_channels",
    "action_policy",
    "sandbox_enforcement",
    "network_policy",
    "mutation_safety",
    "tool_exposure",
    "context_pipeline",
    "instruction_authority",
    "trace_bundle",
    "evidence_model",
    "event_contracts",
    "goals",
    "experimental_capabilities",
}
SUPPORTED_EXTENSION_IDS: set[str] = set()


class ValidationError(Exception):
    """Raised for validation failures."""


def load_manifest(path: Path) -> dict[str, Any]:
    if yaml is not None:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        data = load_manifest_with_ruby(path)
    if not isinstance(data, dict):
        raise ValidationError("manifest root must be a mapping")
    return data


def load_manifest_with_ruby(path: Path) -> Any:
    command = [
        "ruby",
        "-ryaml",
        "-rjson",
        "-e",
        "puts JSON.generate(YAML.load_file(ARGV.fetch(0)))",
        str(path),
    ]
    try:
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ValidationError(
            "PyYAML is not available and ruby was not found; install PyYAML or "
            "run YAML syntax validation with another parser."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise ValidationError(f"YAML parser failed: {exc.stderr.strip()}") from exc
    return json.loads(result.stdout)


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def ids(items: Any, label: str, errors: list[str]) -> set[str]:
    if items is None:
        return set()
    require(isinstance(items, list), f"{label} must be a list", errors)
    if not isinstance(items, list):
        return set()
    seen: set[str] = set()
    for index, item in enumerate(items):
        require(isinstance(item, dict), f"{label}[{index}] must be a mapping", errors)
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        require(
            isinstance(item_id, str) and item_id,
            f"{label}[{index}] needs id",
            errors,
        )
        if isinstance(item_id, str) and item_id:
            require(item_id not in seen, f"duplicate {label} id: {item_id}", errors)
            seen.add(item_id)
    return seen


def iter_bindings(container: dict[str, Any]) -> list[dict[str, Any]]:
    bindings = container.get("skill_bindings", [])
    if bindings is None:
        return []
    if not isinstance(bindings, list):
        return []
    return [binding for binding in bindings if isinstance(binding, dict)]


def validate_required_manifest_fields(data: dict[str, Any], errors: list[str]) -> None:
    require(data.get("format_version") == 1, "format_version must be 1", errors)
    require(
        data.get("package_type") == "dynamic_agent_design",
        "package_type must be dynamic_agent_design",
        errors,
    )
    for field in ("package_id", "entrypoint", "packaging", "nodes", "edges"):
        require(field in data, f"missing required field: {field}", errors)


def grouped_map(data: dict[str, Any], field: str, errors: list[str]) -> dict[str, Any]:
    value = data.get(field, {})
    if value is None:
        return {}
    require(isinstance(value, dict), f"{field} must be a mapping", errors)
    if not isinstance(value, dict):
        return {}
    return value


def validate_no_legacy_flat_fields(data: dict[str, Any], errors: list[str]) -> None:
    for field in sorted(LEGACY_FLAT_OPTIONAL_FIELDS.intersection(data)):
        errors.append(
            f"legacy flat optional field {field} is not supported; "
            "use runtime, metadata, or extensions"
        )


def validate_extensions(data: dict[str, Any], errors: list[str]) -> None:
    extensions = grouped_map(data, "extensions", errors)
    for extension_id, extension in extensions.items():
        label = f"extensions.{extension_id}"
        require(isinstance(extension, dict), f"{label} must be a mapping", errors)
        if not isinstance(extension, dict):
            continue
        required = extension.get("required")
        require(
            isinstance(required, bool),
            f"{label}.required must be true or false",
            errors,
        )
        config = extension.get("config")
        require(isinstance(config, dict), f"{label}.config must be a mapping", errors)
        if required is True and extension_id not in SUPPORTED_EXTENSION_IDS:
            errors.append(f"unsupported required extension {extension_id}")


def validate_packaging(data: dict[str, Any], errors: list[str]) -> None:
    packaging = data.get("packaging")
    require(isinstance(packaging, dict), "packaging must be a mapping", errors)
    if not isinstance(packaging, dict):
        return
    require(
        packaging.get("mode") in VALID_PACKAGING_MODES,
        "packaging.mode must be hybrid_bundle, inline_only, or bundled_only",
        errors,
    )
    if packaging.get("mode") == "hybrid_bundle":
        require(
            isinstance(packaging.get("skill_bundle_dir"), str)
            and bool(packaging.get("skill_bundle_dir")),
            "hybrid_bundle requires packaging.skill_bundle_dir",
            errors,
        )


def prompt_cache_metadata(
    data: dict[str, Any], errors: list[str]
) -> dict[str, Any] | None:
    runtime = grouped_map(data, "runtime", errors)
    execution_policy = runtime.get("execution_policy")
    if execution_policy is None:
        return None
    if not isinstance(execution_policy, dict):
        errors.append("runtime.execution_policy must be a mapping")
        return None

    prompt_cache = execution_policy.get("prompt_cache")
    if prompt_cache is None:
        return None
    if not isinstance(prompt_cache, dict):
        errors.append("runtime.execution_policy.prompt_cache must be a mapping")
        return None
    return prompt_cache


def validate_prompt_cache_scalar_fields(
    prompt_cache: dict[str, Any], errors: list[str]
) -> None:
    if "enabled" in prompt_cache:
        require(
            isinstance(prompt_cache.get("enabled"), bool),
            "runtime.execution_policy.prompt_cache.enabled must be true or false",
            errors,
        )
    if "strategy" in prompt_cache:
        require(
            prompt_cache.get("strategy") in VALID_PROMPT_CACHE_STRATEGIES,
            "runtime.execution_policy.prompt_cache.strategy must be stable_prefix",
            errors,
        )
    if "min_prefix_tokens" in prompt_cache:
        min_prefix_tokens = prompt_cache.get("min_prefix_tokens")
        require(
            isinstance(min_prefix_tokens, int) and min_prefix_tokens > 0,
            "runtime.execution_policy.prompt_cache.min_prefix_tokens must be a positive integer",
            errors,
        )
    if "cache_key_hint" in prompt_cache:
        require(
            prompt_cache.get("cache_key_hint") in VALID_PROMPT_CACHE_KEY_HINTS,
            "runtime.execution_policy.prompt_cache.cache_key_hint has invalid value",
            errors,
        )


def validate_prompt_cache_list_fields(
    prompt_cache: dict[str, Any], errors: list[str]
) -> None:
    allowed_parts_by_field = {
        "prefix_parts": VALID_PROMPT_CACHE_PREFIX_PARTS,
        "variable_parts": VALID_PROMPT_CACHE_VARIABLE_PARTS,
    }
    for field, allowed_parts in allowed_parts_by_field.items():
        value = prompt_cache.get(field)
        if value is None:
            continue
        require(
            isinstance(value, list) and all(isinstance(item, str) for item in value),
            f"runtime.execution_policy.prompt_cache.{field} must be a list of strings",
            errors,
        )
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, str):
                continue
            require(
                item in allowed_parts or PROMPT_CACHE_EXTENSION_PART_RE.match(item),
                f"runtime.execution_policy.prompt_cache.{field} has unsupported part {item}",
                errors,
            )


def validate_prompt_cache(data: dict[str, Any], errors: list[str]) -> None:
    prompt_cache = prompt_cache_metadata(data, errors)
    if prompt_cache is None:
        return
    validate_prompt_cache_scalar_fields(prompt_cache, errors)
    validate_prompt_cache_list_fields(prompt_cache, errors)
    if "provider_hints" in prompt_cache:
        require(
            isinstance(prompt_cache.get("provider_hints"), dict),
            "runtime.execution_policy.prompt_cache.provider_hints must be a mapping",
            errors,
        )


def state_artifact_items(data: dict[str, Any], errors: list[str]) -> Any:
    runtime = grouped_map(data, "runtime", errors)
    state = runtime.get("state")
    if state is None:
        return []
    if not isinstance(state, dict):
        errors.append("runtime.state must be a mapping")
        return []
    return state.get("artifacts", [])


def metadata_patterns(data: dict[str, Any], errors: list[str]) -> set[str]:
    metadata = grouped_map(data, "metadata", errors)
    patterns = metadata.get("patterns_present", [])
    if patterns is None:
        return set()
    require(
        isinstance(patterns, list) and all(isinstance(item, str) for item in patterns),
        "metadata.patterns_present must be a list of strings",
        errors,
    )
    if not isinstance(patterns, list):
        return set()
    return {pattern for pattern in patterns if isinstance(pattern, str)}


def runtime_execution_policy(
    data: dict[str, Any], errors: list[str]
) -> dict[str, Any] | None:
    runtime = grouped_map(data, "runtime", errors)
    execution_policy = runtime.get("execution_policy")
    if execution_policy is None:
        return None
    if not isinstance(execution_policy, dict):
        errors.append("runtime.execution_policy must be a mapping")
        return None
    return execution_policy


def has_loopback_edge(data: dict[str, Any]) -> bool:
    edges = data.get("edges", [])
    if not isinstance(edges, list):
        return False
    return any(
        isinstance(edge, dict) and edge.get("edge_kind") == "loopback" for edge in edges
    )


def validate_exit_strategy(data: dict[str, Any], errors: list[str]) -> None:
    execution_policy = runtime_execution_policy(data, errors)
    if execution_policy is None:
        errors.append("runtime.execution_policy is required")
        return

    exit_strategy = execution_policy.get("exit_strategy")
    require(
        isinstance(exit_strategy, dict),
        "runtime.execution_policy.exit_strategy must be a mapping",
        errors,
    )
    if not isinstance(exit_strategy, dict):
        return

    terminal_conditions = exit_strategy.get("terminal_conditions")
    require(
        isinstance(terminal_conditions, list)
        and bool(terminal_conditions)
        and all(isinstance(item, str) and item.strip() for item in terminal_conditions),
        "runtime.execution_policy.exit_strategy.terminal_conditions must be a non-empty list of strings",
        errors,
    )
    require(
        exit_strategy.get("on_exhaustion") in VALID_EXIT_ON_EXHAUSTION,
        "runtime.execution_policy.exit_strategy.on_exhaustion has invalid value",
        errors,
    )
    require(
        isinstance(exit_strategy.get("ambiguous_completion"), str)
        and bool(exit_strategy.get("ambiguous_completion", "").strip()),
        "runtime.execution_policy.exit_strategy.ambiguous_completion must be a non-empty string",
        errors,
    )

    if "max_steps" in execution_policy:
        max_steps = execution_policy.get("max_steps")
        require(
            isinstance(max_steps, int) and max_steps > 0,
            "runtime.execution_policy.max_steps must be a positive integer",
            errors,
        )

    if has_loopback_edge(data):
        max_iterations = execution_policy.get("max_iterations")
        require(
            isinstance(max_iterations, int) and max_iterations > 0,
            "loopback edges require runtime.execution_policy.max_iterations as a positive integer",
            errors,
        )
        require(
            isinstance(execution_policy.get("max_steps"), int)
            and execution_policy.get("max_steps") > 0,
            "loopback edges require runtime.execution_policy.max_steps as a positive integer",
            errors,
        )


def has_model_safe_observation_artifact(artifacts: Any) -> bool:
    if not isinstance(artifacts, list):
        return False
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        artifact_id = artifact.get("id")
        description = artifact.get("description")
        if not isinstance(artifact_id, str) or not isinstance(description, str):
            continue
        if "observation" in artifact_id and "model-safe" in description.lower():
            return True
    return False


def validate_react_loop(data: dict[str, Any], errors: list[str]) -> None:
    if "react_loop" not in metadata_patterns(data, errors):
        return

    execution_policy = runtime_execution_policy(data, errors)
    max_iterations = None
    if execution_policy is not None:
        max_iterations = execution_policy.get("max_iterations")
    require(
        isinstance(max_iterations, int) and max_iterations > 0,
        "react_loop requires runtime.execution_policy.max_iterations as a positive integer",
        errors,
    )

    nodes = data.get("nodes", [])
    if not isinstance(nodes, list):
        nodes = []
    edges = data.get("edges", [])
    if not isinstance(edges, list):
        edges = []

    require(
        any(
            isinstance(edge, dict) and edge.get("edge_kind") == "loopback"
            for edge in edges
        ),
        "react_loop requires at least one loopback edge",
        errors,
    )
    require(
        any(
            isinstance(node, dict)
            and node.get("kind") == "llm_step"
            and bool(node.get("available_tools"))
            for node in nodes
        ),
        "react_loop requires at least one llm_step with available_tools",
        errors,
    )
    require(
        any(
            isinstance(node, dict) and node.get("kind") == "tool_use_step"
            for node in nodes
        ),
        "react_loop requires at least one tool_use_step",
        errors,
    )
    require(
        any(
            isinstance(node, dict) and node.get("kind") == "decision_step"
            for node in nodes
        ),
        "react_loop requires at least one decision_step for continuation or termination",
        errors,
    )
    llm_route_ids = {
        node.get("id")
        for node in nodes
        if isinstance(node, dict)
        and node.get("kind") == "decision_step"
        and node.get("decision_subtype") == "llm_route"
    }
    tool_node_ids = {
        node.get("id")
        for node in nodes
        if isinstance(node, dict) and node.get("kind") == "tool_use_step"
    }
    terminal_llm_ids = {
        node.get("id")
        for node in nodes
        if isinstance(node, dict)
        and node.get("kind") == "llm_step"
        and not node.get("available_tools")
    }
    llm_with_tools_ids = {
        node.get("id")
        for node in nodes
        if isinstance(node, dict)
        and node.get("kind") == "llm_step"
        and bool(node.get("available_tools"))
    }
    require(
        bool(llm_route_ids),
        "react_loop requires an llm_route decision gate before tool use",
        errors,
    )
    require(
        any(
            isinstance(edge, dict)
            and edge.get("edge_kind") == "branch"
            and edge.get("from") in llm_route_ids
            and edge.get("to") in tool_node_ids
            and edge.get("condition") == "tool"
            for edge in edges
        ),
        "react_loop requires an llm_route branch to tool use with condition tool",
        errors,
    )
    require(
        any(
            isinstance(edge, dict)
            and edge.get("edge_kind") == "branch"
            and edge.get("from") in llm_route_ids
            and edge.get("to") in terminal_llm_ids
            and edge.get("condition") == "final"
            for edge in edges
        ),
        "react_loop requires an llm_route branch to final output with condition final",
        errors,
    )
    require(
        not any(
            isinstance(edge, dict)
            and edge.get("edge_kind") == "sequential"
            and edge.get("from") in llm_with_tools_ids
            and edge.get("to") in tool_node_ids
            for edge in edges
        ),
        "react_loop must not force tool use with an unconditional llm_step->tool_use_step edge",
        errors,
    )
    require(
        has_model_safe_observation_artifact(state_artifact_items(data, errors)),
        "react_loop requires a model-safe observation state artifact",
        errors,
    )


def validate_entrypoint(entrypoint: Any, node_ids: set[str], errors: list[str]) -> None:
    if isinstance(entrypoint, str):
        require(
            entrypoint in node_ids,
            f"entrypoint references missing node: {entrypoint}",
            errors,
        )


def validate_skill_bindings(
    owner_label: str,
    container: dict[str, Any],
    skill_ids: set[str],
    errors: list[str],
) -> None:
    for binding in iter_bindings(container):
        skill_id = binding.get("skill_id")
        usage = binding.get("usage")
        require(
            skill_id in skill_ids,
            f"{owner_label} references missing skill {skill_id}",
            errors,
        )
        require(
            usage in VALID_SKILL_BINDING_USAGES,
            f"{owner_label} has invalid skill usage {usage}",
            errors,
        )


def validate_tools(
    data: dict[str, Any], skill_ids: set[str], errors: list[str]
) -> None:
    tools = data.get("tools", [])
    if not isinstance(tools, list):
        return
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        tool_id = tool.get("id", "<unknown>")
        require(
            isinstance(tool.get("description_for_llm"), str)
            and bool(tool.get("description_for_llm", "").strip()),
            f"tool {tool_id} needs description_for_llm",
            errors,
        )
        require(
            tool.get("side_effect") in VALID_TOOL_SIDE_EFFECTS,
            f"tool {tool_id} has invalid side_effect",
            errors,
        )
        tool_type = tool.get("tool_type")
        if tool_type is not None:
            require(
                tool_type in VALID_TOOL_TYPES,
                f"tool {tool_id} has invalid tool_type {tool_type}",
                errors,
            )
        validate_skill_bindings(f"tool {tool_id}", tool, skill_ids, errors)


def validate_metadata_handoffs(
    metadata: dict[str, Any], role_ids: set[str], errors: list[str]
) -> None:
    handoffs = metadata.get("handoffs")
    if handoffs is None:
        return
    require(isinstance(handoffs, list), "metadata.handoffs must be a list", errors)
    if not isinstance(handoffs, list):
        return
    for index, handoff in enumerate(handoffs):
        label = f"metadata.handoffs[{index}]"
        require(isinstance(handoff, dict), f"{label} must be a mapping", errors)
        if not isinstance(handoff, dict):
            continue
        handoff_id = handoff.get("id")
        require(
            isinstance(handoff_id, str) and bool(handoff_id),
            f"{label} needs id",
            errors,
        )
        kind = handoff.get("kind")
        require(
            kind in VALID_HANDOFF_KINDS,
            f"{label} has invalid kind {kind}",
            errors,
        )
        from_role = handoff.get("from_role")
        to_role = handoff.get("to_role")
        require(
            isinstance(from_role, str) and bool(from_role),
            f"{label} needs from_role",
            errors,
        )
        require(
            isinstance(to_role, str) and bool(to_role),
            f"{label} needs to_role",
            errors,
        )
        if role_ids and isinstance(from_role, str):
            require(
                from_role in role_ids,
                f"{label} references missing from_role {from_role}",
                errors,
            )
        if role_ids and isinstance(to_role, str):
            require(
                to_role in role_ids,
                f"{label} references missing to_role {to_role}",
                errors,
            )
        trigger = handoff.get("trigger")
        if trigger is not None:
            require(
                isinstance(trigger, str), f"{label}.trigger must be a string", errors
            )
        carries = handoff.get("carries")
        if carries is not None:
            require(
                isinstance(carries, list)
                and all(isinstance(item, str) for item in carries),
                f"{label}.carries must be a list of strings",
                errors,
            )


def validate_metadata_delegated_agents(
    metadata: dict[str, Any], tool_ids: set[str], role_ids: set[str], errors: list[str]
) -> None:
    delegated_agents = metadata.get("delegated_agents")
    if delegated_agents is None:
        return
    require(
        isinstance(delegated_agents, list),
        "metadata.delegated_agents must be a list",
        errors,
    )
    if not isinstance(delegated_agents, list):
        return
    for index, delegated_agent in enumerate(delegated_agents):
        label = f"metadata.delegated_agents[{index}]"
        require(
            isinstance(delegated_agent, dict),
            f"{label} must be a mapping",
            errors,
        )
        if not isinstance(delegated_agent, dict):
            continue
        delegated_id = delegated_agent.get("id")
        require(
            isinstance(delegated_id, str) and bool(delegated_id),
            f"{label} needs id",
            errors,
        )
        tool_id = delegated_agent.get("tool_id")
        require(
            isinstance(tool_id, str) and bool(tool_id),
            f"{label} needs tool_id",
            errors,
        )
        if isinstance(tool_id, str):
            require(
                tool_id in tool_ids,
                f"{label} references missing tool_id {tool_id}",
                errors,
            )
        delegation_mode = delegated_agent.get("delegation_mode")
        require(
            delegation_mode in VALID_DELEGATION_MODES,
            f"{label} has invalid delegation_mode {delegation_mode}",
            errors,
        )
        returns_to = delegated_agent.get("returns_to")
        require(
            isinstance(returns_to, str) and bool(returns_to),
            f"{label} needs returns_to",
            errors,
        )
        if role_ids and isinstance(returns_to, str):
            require(
                returns_to in role_ids,
                f"{label} references missing returns_to role {returns_to}",
                errors,
            )
        result_contract = delegated_agent.get("result_contract")
        if result_contract is not None:
            require(
                isinstance(result_contract, dict),
                f"{label}.result_contract must be a mapping",
                errors,
            )
            if isinstance(result_contract, dict):
                result_type = result_contract.get("type")
                require(
                    isinstance(result_type, str) and bool(result_type),
                    f"{label}.result_contract.type must be a non-empty string",
                    errors,
                )


def validate_approval_interaction_target(
    target: Any, label: str, tool_ids: set[str], errors: list[str]
) -> None:
    require(isinstance(target, dict), f"{label}.target must be a mapping", errors)
    if not isinstance(target, dict):
        return
    tool_id = target.get("tool_id")
    require(
        isinstance(tool_id, str) and bool(tool_id),
        f"{label}.target.tool_id must be a non-empty string",
        errors,
    )
    if isinstance(tool_id, str):
        require(
            tool_id in tool_ids,
            f"{label} references missing target.tool_id {tool_id}",
            errors,
        )


def validate_approval_interaction_fields(
    interaction: dict[str, Any], label: str, errors: list[str]
) -> None:
    approval_sensitivity = interaction.get("approval_sensitivity")
    if approval_sensitivity is not None:
        require(
            approval_sensitivity in VALID_APPROVAL_SENSITIVITIES,
            f"{label} has invalid approval_sensitivity {approval_sensitivity}",
            errors,
        )
    approval_message = interaction.get("approval_message")
    if approval_message is not None:
        require(
            isinstance(approval_message, str),
            f"{label}.approval_message must be a string",
            errors,
        )
    if "interruptible" in interaction:
        require(
            isinstance(interaction.get("interruptible"), bool),
            f"{label}.interruptible must be true or false",
            errors,
        )
    resumability = interaction.get("resumability")
    if resumability is not None:
        require(
            resumability in VALID_RESUMABILITY,
            f"{label} has invalid resumability {resumability}",
            errors,
        )


def validate_metadata_approval_interactions(
    metadata: dict[str, Any], tool_ids: set[str], errors: list[str]
) -> None:
    approval_interactions = metadata.get("approval_interactions")
    if approval_interactions is None:
        return
    require(
        isinstance(approval_interactions, list),
        "metadata.approval_interactions must be a list",
        errors,
    )
    if not isinstance(approval_interactions, list):
        return
    for index, interaction in enumerate(approval_interactions):
        label = f"metadata.approval_interactions[{index}]"
        require(isinstance(interaction, dict), f"{label} must be a mapping", errors)
        if not isinstance(interaction, dict):
            continue
        validate_approval_interaction_target(
            interaction.get("target"), label, tool_ids, errors
        )
        validate_approval_interaction_fields(interaction, label, errors)


def validate_portable_taxonomy_metadata(
    metadata: dict[str, Any], tool_ids: set[str], role_ids: set[str], errors: list[str]
) -> None:
    validate_metadata_handoffs(metadata, role_ids, errors)
    validate_metadata_delegated_agents(metadata, tool_ids, role_ids, errors)
    validate_metadata_approval_interactions(metadata, tool_ids, errors)


def validate_node_scope_refs(
    node: dict[str, Any],
    node_id: Any,
    phase_ids: set[str],
    mode_ids: set[str],
    role_ids: set[str],
    errors: list[str],
) -> None:
    phase = node.get("phase")
    if phase is not None and phase_ids:
        require(
            phase in phase_ids,
            f"node {node_id} references missing phase {phase}",
            errors,
        )
    role = node.get("role")
    if role is not None and role_ids:
        require(
            role in role_ids, f"node {node_id} references missing role {role}", errors
        )
    mode_scope = node.get("mode_scope", [])
    if isinstance(mode_scope, list) and mode_ids:
        for mode in mode_scope:
            require(
                mode == "all" or mode in mode_ids,
                f"node {node_id} references missing mode {mode}",
                errors,
            )


def validate_llm_step(node: dict[str, Any], node_id: Any, errors: list[str]) -> None:
    require(
        isinstance(node.get("prompt"), dict)
        or isinstance(node.get("prompt_source"), str),
        f"llm_step {node_id} needs prompt or prompt_source",
        errors,
    )


def validate_tool_use_step(
    node: dict[str, Any],
    node_id: Any,
    tool_ids: set[str],
    errors: list[str],
) -> None:
    tool_id = node.get("tool_id")
    require(
        tool_id in tool_ids,
        f"tool_use_step {node_id} references missing tool {tool_id}",
        errors,
    )


def validate_decision_step(
    node: dict[str, Any], node_id: Any, errors: list[str]
) -> None:
    subtype = node.get("decision_subtype")
    require(
        subtype in VALID_DECISION_SUBTYPES,
        f"decision_step {node_id} has invalid subtype {subtype}",
        errors,
    )
    require(
        isinstance(node.get("decision_contract"), dict),
        f"decision_step {node_id} needs decision_contract",
        errors,
    )
    if subtype == "llm_route":
        require(
            isinstance(node.get("prompt"), dict),
            f"llm_route {node_id} needs prompt",
            errors,
        )


def validate_node_kind_specifics(
    node: dict[str, Any],
    node_id: Any,
    kind: Any,
    tool_ids: set[str],
    errors: list[str],
) -> None:
    if kind == "llm_step":
        validate_llm_step(node, node_id, errors)
    if kind == "tool_use_step":
        validate_tool_use_step(node, node_id, tool_ids, errors)
    if kind == "decision_step":
        validate_decision_step(node, node_id, errors)


def validate_available_tools(
    node: dict[str, Any],
    node_id: Any,
    tool_ids: set[str],
    errors: list[str],
) -> None:
    for available in node.get("available_tools", []) or []:
        if isinstance(available, dict):
            tool_id = available.get("tool_id")
            require(
                tool_id in tool_ids,
                f"node {node_id} references missing available tool {tool_id}",
                errors,
            )


def validate_prompt_output_contract(
    node: dict[str, Any],
    node_id: Any,
    output_contract_ids: set[str],
    errors: list[str],
) -> None:
    prompt = node.get("prompt")
    if not isinstance(prompt, dict):
        return
    output_schema_ref = prompt.get("output_schema_ref")
    if output_schema_ref not in (None, "null") and output_contract_ids:
        require(
            output_schema_ref in output_contract_ids,
            f"node {node_id} references missing output contract {output_schema_ref}",
            errors,
        )


def validate_optional_mapping(
    value: Any, label: str, errors: list[str]
) -> dict[str, Any] | None:
    if value is None:
        return None
    require(isinstance(value, dict), f"{label} must be a mapping", errors)
    if not isinstance(value, dict):
        return None
    return value


def validate_optional_enum(
    container: dict[str, Any],
    field: str,
    allowed: set[str],
    label: str,
    errors: list[str],
) -> None:
    value = container.get(field)
    if value is None:
        return
    require(value in allowed, f"{label}.{field} has invalid value {value}", errors)


def validate_model_required_capabilities(
    requirements: dict[str, Any], label: str, errors: list[str]
) -> None:
    capabilities = requirements.get("required_capabilities")
    if capabilities is None:
        return
    if not (
        isinstance(capabilities, list)
        and all(isinstance(item, str) for item in capabilities)
    ):
        errors.append(f"{label}.required_capabilities must be a list of strings")
        return
    for capability in capabilities:
        require(
            capability in VALID_MODEL_REQUIRED_CAPABILITIES,
            f"{label}.required_capabilities has unsupported value {capability}",
            errors,
        )


def validate_model_reasoning_profile(
    requirements: dict[str, Any], label: str, errors: list[str]
) -> None:
    reasoning = validate_optional_mapping(
        requirements.get("reasoning_profile"),
        f"{label}.reasoning_profile",
        errors,
    )
    if reasoning is None:
        return
    reasoning_label = f"{label}.reasoning_profile"
    validate_optional_enum(
        reasoning, "level", VALID_REASONING_LEVELS, reasoning_label, errors
    )
    validate_optional_enum(
        reasoning, "task_type", VALID_REASONING_TASK_TYPES, reasoning_label, errors
    )
    validate_optional_enum(
        reasoning,
        "task_subtype",
        VALID_REASONING_TASK_SUBTYPES,
        reasoning_label,
        errors,
    )
    validate_optional_enum(
        reasoning,
        "uncertainty_handling",
        VALID_UNCERTAINTY_HANDLING,
        reasoning_label,
        errors,
    )


def validate_model_context_requirements(
    requirements: dict[str, Any], label: str, errors: list[str]
) -> None:
    context = validate_optional_mapping(
        requirements.get("context_requirements"),
        f"{label}.context_requirements",
        errors,
    )
    if context is None:
        return
    context_label = f"{label}.context_requirements"
    validate_optional_enum(
        context,
        "expected_input_size",
        VALID_EXPECTED_INPUT_SIZES,
        context_label,
        errors,
    )
    context_window = context.get("context_window")
    if context_window is not None:
        require(
            context_window == "unknown"
            or (isinstance(context_window, int) and context_window > 0),
            f"{label}.context_requirements.context_window must be a positive integer or unknown",
            errors,
        )
    retrieved_context = context.get("needs_retrieved_context")
    if retrieved_context is not None:
        require(
            isinstance(retrieved_context, bool) or retrieved_context == "conditional",
            f"{label}.context_requirements.needs_retrieved_context must be true, false, or conditional",
            errors,
        )


def prompt_output_schema_ref(node: dict[str, Any]) -> Any:
    prompt = node.get("prompt")
    if not isinstance(prompt, dict):
        return None
    return prompt.get("output_schema_ref")


def validate_model_output_requirements(
    node: dict[str, Any],
    requirements: dict[str, Any],
    label: str,
    output_contract_ids: set[str],
    errors: list[str],
) -> None:
    output = validate_optional_mapping(
        requirements.get("output_requirements"),
        f"{label}.output_requirements",
        errors,
    )
    if output is None:
        return
    output_label = f"{label}.output_requirements"
    validate_optional_enum(output, "format", VALID_OUTPUT_FORMATS, output_label, errors)
    validate_optional_enum(
        output, "evidence_citations", VALID_EVIDENCE_CITATIONS, output_label, errors
    )
    schema_ref = output.get("schema_ref")
    if schema_ref not in (None, "null"):
        require(
            isinstance(schema_ref, str) and bool(schema_ref.strip()),
            f"{label}.output_requirements.schema_ref must be a non-empty string",
            errors,
        )
        if isinstance(schema_ref, str) and output_contract_ids:
            require(
                schema_ref in output_contract_ids,
                f"{label}.output_requirements references missing output contract {schema_ref}",
                errors,
            )
    prompt_schema_ref = prompt_output_schema_ref(node)
    if prompt_schema_ref not in (None, "null") and schema_ref not in (None, "null"):
        require(
            prompt_schema_ref == schema_ref,
            f"node {node.get('id', '<unknown>')} prompt output_schema_ref must match model_requirements.output_requirements.schema_ref",
            errors,
        )


def validate_model_operational_preferences(
    requirements: dict[str, Any], label: str, errors: list[str]
) -> None:
    preferences = validate_optional_mapping(
        requirements.get("operational_preferences"),
        f"{label}.operational_preferences",
        errors,
    )
    if preferences is None:
        return
    preferences_label = f"{label}.operational_preferences"
    validate_optional_enum(
        preferences,
        "latency_sensitivity",
        VALID_SENSITIVITY_VALUES,
        preferences_label,
        errors,
    )
    validate_optional_enum(
        preferences,
        "cost_sensitivity",
        VALID_SENSITIVITY_VALUES,
        preferences_label,
        errors,
    )
    validate_optional_enum(
        preferences, "determinism", VALID_DETERMINISM_VALUES, preferences_label, errors
    )
    validate_optional_enum(
        preferences, "data_boundary", VALID_DATA_BOUNDARIES, preferences_label, errors
    )


def validate_model_fallback_policy(
    requirements: dict[str, Any], label: str, errors: list[str]
) -> None:
    fallback = validate_optional_mapping(
        requirements.get("fallback_policy"),
        f"{label}.fallback_policy",
        errors,
    )
    if fallback is None:
        return
    fallback_label = f"{label}.fallback_policy"
    validate_optional_enum(
        fallback, "if_unavailable", VALID_FALLBACK_ACTIONS, fallback_label, errors
    )
    validate_optional_enum(
        fallback,
        "minimum_acceptable_level",
        VALID_REASONING_LEVELS,
        fallback_label,
        errors,
    )


def validate_model_requirements(
    node: dict[str, Any],
    node_id: Any,
    kind: Any,
    output_contract_ids: set[str],
    errors: list[str],
) -> None:
    requirements = node.get("model_requirements")
    if requirements is None:
        return
    require(
        kind == "llm_step",
        f"non-llm_step node {node_id} must not define model_requirements",
        errors,
    )
    label = f"node {node_id} model_requirements"
    requirements = validate_optional_mapping(requirements, label, errors)
    if requirements is None:
        return
    validate_model_required_capabilities(requirements, label, errors)
    validate_model_reasoning_profile(requirements, label, errors)
    validate_model_context_requirements(requirements, label, errors)
    validate_model_output_requirements(
        node, requirements, label, output_contract_ids, errors
    )
    validate_model_operational_preferences(requirements, label, errors)
    validate_model_fallback_policy(requirements, label, errors)


def validate_node_artifact_refs(
    node: dict[str, Any],
    node_id: Any,
    state_ids: set[str],
    output_contract_ids: set[str],
    errors: list[str],
) -> None:
    for field in ("inputs_from", "outputs"):
        values = node.get(field, []) or []
        if isinstance(values, list) and state_ids:
            for value in values:
                require(
                    value in state_ids or value in output_contract_ids,
                    f"node {node_id} {field} references unknown artifact {value}",
                    errors,
                )


def validate_node(
    node: dict[str, Any],
    phase_ids: set[str],
    mode_ids: set[str],
    role_ids: set[str],
    skill_ids: set[str],
    tool_ids: set[str],
    state_ids: set[str],
    output_contract_ids: set[str],
    errors: list[str],
) -> None:
    node_id = node.get("id", "<unknown>")
    kind = node.get("kind")
    require(kind in VALID_NODE_KINDS, f"node {node_id} has invalid kind {kind}", errors)
    validate_node_scope_refs(node, node_id, phase_ids, mode_ids, role_ids, errors)
    validate_node_kind_specifics(node, node_id, kind, tool_ids, errors)
    validate_available_tools(node, node_id, tool_ids, errors)
    validate_skill_bindings(f"node {node_id}", node, skill_ids, errors)
    validate_prompt_output_contract(node, node_id, output_contract_ids, errors)
    validate_model_requirements(node, node_id, kind, output_contract_ids, errors)
    validate_node_artifact_refs(node, node_id, state_ids, output_contract_ids, errors)


def validate_nodes(
    data: dict[str, Any],
    phase_ids: set[str],
    mode_ids: set[str],
    role_ids: set[str],
    skill_ids: set[str],
    tool_ids: set[str],
    state_ids: set[str],
    output_contract_ids: set[str],
    errors: list[str],
) -> None:
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        return
    for node in nodes:
        if isinstance(node, dict):
            validate_node(
                node,
                phase_ids,
                mode_ids,
                role_ids,
                skill_ids,
                tool_ids,
                state_ids,
                output_contract_ids,
                errors,
            )


def validate_edges(data: dict[str, Any], node_ids: set[str], errors: list[str]) -> None:
    edges = data.get("edges")
    if not isinstance(edges, list):
        return
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = edge.get("from")
        target = edge.get("to")
        edge_kind = edge.get("edge_kind")
        require(
            source in node_ids, f"edge references missing from node {source}", errors
        )
        require(target in node_ids, f"edge references missing to node {target}", errors)
        require(
            edge_kind in VALID_EDGE_KINDS,
            f"edge {source}->{target} has invalid edge_kind {edge_kind}",
            errors,
        )
        if edge_kind == "branch":
            require(
                "condition" in edge,
                f"branch edge {source}->{target} needs condition",
                errors,
            )


def validate_manifest(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    validate_required_manifest_fields(data, errors)
    validate_no_legacy_flat_fields(data, errors)
    validate_packaging(data, errors)
    validate_extensions(data, errors)
    validate_prompt_cache(data, errors)
    validate_exit_strategy(data, errors)
    validate_react_loop(data, errors)

    metadata = grouped_map(data, "metadata", errors)

    skill_ids = ids(data.get("skills", []), "skills", errors)
    tool_ids = ids(data.get("tools", []), "tools", errors)
    node_ids = ids(data.get("nodes"), "nodes", errors)
    phase_ids = ids(metadata.get("phases", []), "metadata.phases", errors)
    mode_ids = ids(metadata.get("modes", []), "metadata.modes", errors)
    role_ids = ids(metadata.get("roles", []), "metadata.roles", errors)
    state_ids = ids(
        state_artifact_items(data, errors), "runtime.state.artifacts", errors
    )
    output_contract_ids = ids(
        data.get("output_contracts", []), "output_contracts", errors
    )

    validate_entrypoint(data.get("entrypoint"), node_ids, errors)
    validate_tools(data, skill_ids, errors)
    validate_portable_taxonomy_metadata(metadata, tool_ids, role_ids, errors)
    validate_nodes(
        data,
        phase_ids,
        mode_ids,
        role_ids,
        skill_ids,
        tool_ids,
        state_ids,
        output_contract_ids,
        errors,
    )
    validate_edges(data, node_ids, errors)
    return errors


def validate_mermaid(path: Path, data: dict[str, Any]) -> list[str]:
    if not path.exists():
        return [f"Mermaid file not found: {path}"]
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    for node in data.get("nodes", []) or []:
        if isinstance(node, dict):
            node_id = node.get("id")
            if isinstance(node_id, str):
                require(
                    node_id in text, f"Mermaid graph missing node id {node_id}", errors
                )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--mermaid", type=Path)
    args = parser.parse_args()

    try:
        data = load_manifest(args.manifest)
        errors = validate_manifest(data)
        if args.mermaid is not None:
            errors.extend(validate_mermaid(args.mermaid, data))
    except ValidationError as exc:
        errors = [str(exc)]

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"validated {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
