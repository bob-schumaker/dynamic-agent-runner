"""Workflow executor for validated dynamic-agent runtime artifacts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from dynamic_agent_runner.errors import WorkflowExecutionError
from dynamic_agent_runner.models import LoadedAgentWorkflow, RuntimeEdge, RuntimeNode
from dynamic_agent_runner.openai_client import (
    ModelResponse,
    OpenAIClientAdapter,
    OpenAIMessage,
    build_openai_request,
)
from dynamic_agent_runner.registry import ToolRegistry, ToolResult


@dataclass(frozen=True)
class NodeExecution:
    """Execution record for a completed runtime node."""

    node_id: str
    kind: str
    output: Any = None
    error: str | None = None


@dataclass
class WorkflowExecutionState:
    """Mutable execution state accumulated while a workflow runs."""

    prompt: str
    node_inputs: dict[str, Any] = field(default_factory=dict)
    node_outputs: dict[str, Any] = field(default_factory=dict)
    tool_results: dict[str, ToolResult] = field(default_factory=dict)
    executions: list[NodeExecution] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    final_result: Any = None


@dataclass(frozen=True)
class WorkflowResult:
    """Successful workflow execution result."""

    final_result: Any
    state: WorkflowExecutionState


def execute_workflow(
    workflow: LoadedAgentWorkflow,
    *,
    prompt: str,
    tool_registry: ToolRegistry | None = None,
    model_adapter: OpenAIClientAdapter | None = None,
    max_steps: int | None = None,
) -> WorkflowResult:
    """Execute a validated workflow from a user prompt."""

    if not prompt:
        raise WorkflowExecutionError("workflow execution requires a non-empty prompt")
    manifest = workflow.runtime_manifest
    nodes = _node_map(tuple(manifest.nodes))
    if not manifest.entrypoint or manifest.entrypoint not in nodes:
        raise WorkflowExecutionError("workflow entrypoint does not reference a node")
    edges_by_source = _edges_by_source(tuple(manifest.edges))
    adapter = model_adapter or OpenAIClientAdapter()
    state = WorkflowExecutionState(prompt=prompt)
    current_node_id: str | None = manifest.entrypoint
    limit = max_steps or _max_steps(manifest.execution_policy) or (len(nodes) + 10)

    for _step_index in range(limit):
        if current_node_id is None:
            state.final_result = _last_output(state)
            return WorkflowResult(final_result=state.final_result, state=state)
        node = nodes[current_node_id]
        output = _execute_node(node, workflow, state, tool_registry, adapter)
        state.node_outputs[current_node_id] = output
        state.executions.append(
            NodeExecution(node_id=current_node_id, kind=str(node.kind), output=output)
        )
        current_node_id = _next_node_id(
            node, output, edges_by_source.get(current_node_id, ())
        )

    raise WorkflowExecutionError(f"workflow exceeded maximum step count {limit}")


def _execute_node(
    node: RuntimeNode,
    workflow: LoadedAgentWorkflow,
    state: WorkflowExecutionState,
    registry: ToolRegistry | None,
    adapter: OpenAIClientAdapter,
) -> Any:
    if node.kind == "llm_step":
        return _execute_llm_step(node, workflow, state, registry, adapter)
    if node.kind == "tool_use_step":
        return _execute_tool_step(node, state, registry)
    if node.kind == "decision_step":
        return _execute_decision_step(node, state)
    raise WorkflowExecutionError(f"unsupported node kind {node.kind!r}")


def _execute_llm_step(
    node: RuntimeNode,
    workflow: LoadedAgentWorkflow,
    state: WorkflowExecutionState,
    registry: ToolRegistry | None,
    adapter: OpenAIClientAdapter,
) -> ModelResponse:
    messages = _render_messages(node, state)
    tools: list[dict[str, Any]] = []
    if node.available_tools:
        if registry is None:
            raise WorkflowExecutionError(
                f"llm_step node {node.id!r} exposes tools but no registry was provided"
            )
        tools = registry.to_openai_tools(
            tool.id for tool in registry.list_tools_for_node(node)
        )
    request = build_openai_request(
        model=_model_name(node, workflow),
        messages=messages,
        tools=tools,
        tool_choice=node.raw.get("tool_choice"),
        response_format=_mapping_or_none(node.raw.get("response_format")),
        **_model_parameters(node),
    )
    state.node_inputs[str(node.id)] = request.to_kwargs()
    return adapter.create_response(request)


def _execute_tool_step(
    node: RuntimeNode,
    state: WorkflowExecutionState,
    registry: ToolRegistry | None,
) -> ToolResult:
    if registry is None:
        raise WorkflowExecutionError(
            f"tool_use_step node {node.id!r} requires a tool registry"
        )
    if not node.tool_id:
        raise WorkflowExecutionError(
            f"tool_use_step node {node.id!r} is missing tool_id"
        )
    arguments = _tool_arguments(node, state)
    state.node_inputs[str(node.id)] = arguments
    result = registry.invoke_tool(node.tool_id, arguments)
    state.tool_results[str(node.id)] = result
    if not result.success and _failure_behavior(node) == "error":
        error = result.error or f"tool {node.tool_id!r} failed"
        state.errors.append(error)
        raise WorkflowExecutionError(error)
    _record_outputs(node, result.output, state)
    return result


def _execute_decision_step(node: RuntimeNode, state: WorkflowExecutionState) -> str:
    if node.decision_subtype != "llm_route":
        raise WorkflowExecutionError(
            f"decision_step node {node.id!r} has unsupported decision_subtype "
            f"{node.decision_subtype!r}"
        )
    route = _resolve_value(node.raw.get("route_from") or "last", state)
    if isinstance(route, ModelResponse):
        route = route.content
    route_text = _route_from_value(route)
    if not route_text:
        raise WorkflowExecutionError(
            f"decision_step node {node.id!r} produced no route"
        )
    return route_text


def _render_messages(
    node: RuntimeNode, state: WorkflowExecutionState
) -> tuple[OpenAIMessage, ...]:
    prompt_data = node.raw.get("prompt")
    if not isinstance(prompt_data, Mapping):
        prompt_data = {
            "user_template": str(node.raw.get("prompt_source") or "{prompt}")
        }
    context = _format_context(state)
    messages: list[OpenAIMessage] = []
    for role in ("system", "developer"):
        value = prompt_data.get(role)
        if value is not None:
            messages.append(
                OpenAIMessage(role=role, content=_format_text(str(value), context))
            )
    user_template = (
        prompt_data.get("user_template") or prompt_data.get("user") or "{prompt}"
    )
    messages.append(
        OpenAIMessage(role="user", content=_format_text(str(user_template), context))
    )
    return tuple(messages)


def _tool_arguments(node: RuntimeNode, state: WorkflowExecutionState) -> dict[str, Any]:
    arguments: dict[str, Any] = {}
    raw_inputs = node.raw.get("inputs")
    if isinstance(raw_inputs, Mapping):
        arguments.update(dict(raw_inputs))
    inputs_from = node.raw.get("inputs_from")
    if isinstance(inputs_from, Mapping):
        for argument_name, source in inputs_from.items():
            arguments[str(argument_name)] = _resolve_value(source, state)
    elif inputs_from is not None:
        value = _resolve_value(inputs_from, state)
        if isinstance(value, Mapping):
            arguments.update(value)
        else:
            arguments["input"] = value
    return arguments


def _record_outputs(
    node: RuntimeNode, output: Any, state: WorkflowExecutionState
) -> None:
    outputs = node.raw.get("outputs")
    if isinstance(outputs, Mapping):
        state_key = outputs.get("state_key") or outputs.get("key")
        if state_key:
            state.node_outputs[str(state_key)] = output


def _next_node_id(
    node: RuntimeNode,
    output: Any,
    edges: Sequence[RuntimeEdge],
) -> str | None:
    if not edges:
        return None
    control_edges = [
        edge for edge in edges if edge.edge_kind in {"sequential", "branch"}
    ]
    if not control_edges:
        edge_kinds = ", ".join(sorted({str(edge.edge_kind) for edge in edges}))
        raise WorkflowExecutionError(
            f"node {node.id!r} has unsupported outgoing edge kind(s): {edge_kinds}"
        )
    if len(control_edges) == 1 and control_edges[0].edge_kind == "sequential":
        return control_edges[0].target
    if node.kind == "decision_step":
        route = str(output)
        for edge in control_edges:
            if edge.edge_kind == "branch" and _edge_condition(edge) == route:
                return edge.target
        raise WorkflowExecutionError(f"no branch edge matched route {route!r}")
    sequential = [edge for edge in control_edges if edge.edge_kind == "sequential"]
    if len(sequential) == 1:
        return sequential[0].target
    raise WorkflowExecutionError(
        f"node {node.id!r} has unsupported outgoing edge configuration"
    )


def _node_map(nodes: Sequence[RuntimeNode]) -> dict[str, RuntimeNode]:
    return {str(node.id): node for node in nodes if node.id is not None}


def _edges_by_source(
    edges: Sequence[RuntimeEdge],
) -> dict[str, tuple[RuntimeEdge, ...]]:
    grouped: dict[str, list[RuntimeEdge]] = {}
    for edge in edges:
        if edge.source is None:
            continue
        grouped.setdefault(edge.source, []).append(edge)
    return {source: tuple(values) for source, values in grouped.items()}


def _model_name(node: RuntimeNode, workflow: LoadedAgentWorkflow) -> str:
    value = node.raw.get("model") or workflow.runtime_manifest.execution_policy.get(
        "model"
    )
    if value is None:
        value = workflow.runtime_manifest.execution_policy.get("default_model")
    if value is None:
        raise WorkflowExecutionError(f"llm_step node {node.id!r} is missing model")
    return str(value)


def _model_parameters(node: RuntimeNode) -> dict[str, Any]:
    parameters = node.raw.get("model_parameters")
    return dict(parameters) if isinstance(parameters, Mapping) else {}


def _mapping_or_none(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _format_context(state: WorkflowExecutionState) -> dict[str, Any]:
    context: dict[str, Any] = {
        "prompt": state.prompt,
        "node_outputs": state.node_outputs,
        "tool_results": state.tool_results,
    }
    for key, value in state.node_outputs.items():
        if isinstance(value, ModelResponse):
            context[key] = value.content
        elif isinstance(value, ToolResult):
            context[key] = value.output
        else:
            context[key] = value
    return context


def _format_text(template: str, context: Mapping[str, Any]) -> str:
    try:
        return template.format(**context)
    except KeyError as exc:
        raise WorkflowExecutionError(f"missing prompt input {exc.args[0]!r}") from exc


def _resolve_value(source: Any, state: WorkflowExecutionState) -> Any:
    if source == "prompt":
        return state.prompt
    if source == "last":
        return _last_output(state)
    if isinstance(source, str):
        if source in state.node_outputs:
            return _unwrap_output(state.node_outputs[source])
        if source.startswith("node_outputs."):
            return _resolve_path(
                state.node_outputs, source.removeprefix("node_outputs.")
            )
        if source.startswith("tool_results."):
            return _resolve_path(
                state.tool_results, source.removeprefix("tool_results.")
            )
    return source


def _resolve_path(root: Any, path: str) -> Any:
    value = root
    for part in path.split("."):
        value = _read_value(value, part)
    return _unwrap_output(value)


def _read_value(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _unwrap_output(value: Any) -> Any:
    if isinstance(value, ModelResponse):
        return value.content
    if isinstance(value, ToolResult):
        return value.output
    return value


def _last_output(state: WorkflowExecutionState) -> Any:
    if not state.executions:
        return None
    return _unwrap_output(state.executions[-1].output)


def _route_from_value(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        try:
            decoded = json.loads(stripped)
        except json.JSONDecodeError:
            return stripped
        return _route_from_value(decoded)
    if isinstance(value, Mapping):
        route = value.get("route") or value.get("decision") or value.get("next")
        return str(route) if route is not None else None
    return str(value) if value is not None else None


def _edge_condition(edge: RuntimeEdge) -> str | None:
    condition = edge.condition or edge.raw.get("route") or edge.raw.get("when")
    return str(condition) if condition is not None else None


def _failure_behavior(node: RuntimeNode) -> str:
    return str(node.raw.get("failure_behavior") or "error")


def _max_steps(execution_policy: Mapping[str, Any]) -> int | None:
    value = execution_policy.get("max_steps") or execution_policy.get("maximum_steps")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
