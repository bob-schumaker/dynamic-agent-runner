"""Workflow executor for validated dynamic-agent runtime artifacts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from dynamic_agent_runner.behavior import effective_node_behavior
from dynamic_agent_runner.context import WorkflowExecutionContext
from dynamic_agent_runner.errors import (
    ModelExecutionError,
    ToolRegistryError,
    WorkflowExecutionError,
)
from dynamic_agent_runner.models import LoadedAgentWorkflow, RuntimeEdge, RuntimeNode
from dynamic_agent_runner.openai_client import (
    ModelResponse,
    OpenAIClientAdapter,
    OpenAIMessage,
    build_openai_request,
)
from dynamic_agent_runner.prompt_cache import (
    build_prompt_cache_observation,
    prompt_cache_policy_from_value,
)
from dynamic_agent_runner.registry import ToolRegistry, ToolResult
from dynamic_agent_runner.retry import (
    RetryPolicy,
    RetryRecord,
    retry_policy_from_value,
    run_with_retry,
)
from dynamic_agent_runner.token_budget import (
    TokenBudgetPolicy,
    TokenUsageRecord,
    estimate_messages_tokens,
    token_budget_policy_from_value,
)
from dynamic_agent_runner.tracing import TraceEvent, TraceSink, WorkflowTracer


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
    retry_records: list[RetryRecord] = field(default_factory=list)
    token_usage: list[TokenUsageRecord] = field(default_factory=list)
    trace_events: list[TraceEvent] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    final_result: Any = None


@dataclass(frozen=True)
class WorkflowResult:
    """Successful workflow execution result."""

    final_result: Any
    state: WorkflowExecutionState


def execute_workflow(
    workflow: LoadedAgentWorkflow | WorkflowExecutionContext,
    *,
    prompt: str,
    tool_registry: ToolRegistry | None = None,
    model_adapter: OpenAIClientAdapter | None = None,
    max_steps: int | None = None,
    trace_sink: TraceSink | None = None,
    prompt_cache: bool | None = None,
) -> WorkflowResult:
    """Execute a validated workflow from a user prompt."""

    if not prompt:
        raise WorkflowExecutionError("workflow execution requires a non-empty prompt")
    context = _normalize_execution_context(
        workflow,
        tool_registry=tool_registry,
        model_adapter=model_adapter,
        max_steps=max_steps,
        trace_sink=trace_sink,
        prompt_cache=prompt_cache,
    )
    manifest = context.workflow.runtime_manifest
    nodes = _node_map(tuple(manifest.nodes))
    if not manifest.entrypoint or manifest.entrypoint not in nodes:
        raise WorkflowExecutionError("workflow entrypoint does not reference a node")
    edges_by_source = _edges_by_source(tuple(manifest.edges))
    adapter = context.model_adapter or OpenAIClientAdapter()
    state = WorkflowExecutionState(prompt=prompt)
    tracer = WorkflowTracer(events=state.trace_events, sink=context.trace_sink)
    current_node_id: str | None = manifest.entrypoint
    limit = (
        context.max_steps or _max_steps(manifest.execution_policy) or (len(nodes) + 10)
    )
    tracer.emit(
        "workflow_started",
        payload={"entrypoint": manifest.entrypoint, "prompt": prompt},
        sensitive_fields=("prompt",),
    )

    for _step_index in range(limit):
        if current_node_id is None:
            state.final_result = _last_output(state)
            tracer.emit(
                "workflow_completed",
                payload={"final_result": state.final_result},
                sensitive_fields=("final_result",),
            )
            return WorkflowResult(final_result=state.final_result, state=state)
        node = nodes[current_node_id]
        tracer.emit(
            "node_started",
            node_id=str(node.id),
            payload={"kind": node.kind},
        )
        try:
            output = _execute_node(
                node,
                context.workflow,
                state,
                context.tool_registry,
                adapter,
                tracer,
                context.prompt_cache,
            )
        except Exception as exc:
            tracer.emit(
                "node_error",
                node_id=str(node.id),
                payload={"kind": node.kind, "error": str(exc)},
            )
            raise
        state.node_outputs[current_node_id] = output
        state.executions.append(
            NodeExecution(node_id=current_node_id, kind=str(node.kind), output=output)
        )
        tracer.emit(
            "node_completed",
            node_id=str(node.id),
            payload={"kind": node.kind, "output": _unwrap_output(output)},
            sensitive_fields=("output",),
        )
        current_node_id = _next_node_id(
            node, output, edges_by_source.get(current_node_id, ())
        )

    error = f"workflow exceeded maximum step count {limit}"
    tracer.emit("workflow_error", payload={"error": error})
    raise WorkflowExecutionError(error)


def _normalize_execution_context(
    workflow: LoadedAgentWorkflow | WorkflowExecutionContext,
    *,
    tool_registry: ToolRegistry | None,
    model_adapter: OpenAIClientAdapter | None,
    max_steps: int | None,
    trace_sink: TraceSink | None,
    prompt_cache: bool | None,
) -> WorkflowExecutionContext:
    if isinstance(workflow, WorkflowExecutionContext):
        if any(
            value is not None
            for value in (
                tool_registry,
                model_adapter,
                max_steps,
                trace_sink,
                prompt_cache,
            )
        ):
            raise WorkflowExecutionError(
                "execution context cannot be combined with runtime keyword arguments"
            )
        return workflow
    return WorkflowExecutionContext(
        workflow=workflow,
        tool_registry=tool_registry,
        model_adapter=model_adapter,
        max_steps=max_steps,
        trace_sink=trace_sink,
        prompt_cache=prompt_cache,
    )


def _execute_node(
    node: RuntimeNode,
    workflow: LoadedAgentWorkflow,
    state: WorkflowExecutionState,
    registry: ToolRegistry | None,
    adapter: OpenAIClientAdapter,
    tracer: WorkflowTracer,
    prompt_cache: bool | None,
) -> Any:
    if node.kind == "llm_step":
        return _execute_llm_step(
            node, workflow, state, registry, adapter, tracer, prompt_cache
        )
    if node.kind == "tool_use_step":
        return _execute_tool_step(node, state, registry, tracer)
    if node.kind == "decision_step":
        return _execute_decision_step(node, state, tracer)
    raise WorkflowExecutionError(f"unsupported node kind {node.kind!r}")


def _execute_llm_step(
    node: RuntimeNode,
    workflow: LoadedAgentWorkflow,
    state: WorkflowExecutionState,
    registry: ToolRegistry | None,
    adapter: OpenAIClientAdapter,
    tracer: WorkflowTracer,
    prompt_cache: bool | None,
) -> ModelResponse:
    behavior = effective_node_behavior(node, workflow)
    message_parts = _render_message_parts(behavior, state)
    messages = tuple(message for _part, message in message_parts)
    tools: list[dict[str, Any]] = []
    if node.available_tools:
        if registry is None:
            raise WorkflowExecutionError(
                f"llm_step node {node.id!r} exposes tools but no registry was provided"
            )
        tools = registry.to_openai_tools(
            tool.id for tool in registry.list_tools_for_node(node)
        )
    model = _model_name(node, workflow)
    _check_prompt_cache(
        workflow,
        message_parts,
        model,
        tracer,
        node,
        prompt_cache=prompt_cache,
    )
    _enforce_token_budget(node, workflow, messages, model, state, tracer)
    request = build_openai_request(
        model=model,
        messages=messages,
        tools=tools,
        tool_choice=node.raw.get("tool_choice"),
        response_format=_mapping_or_none(node.raw.get("response_format")),
        **_model_parameters(node),
    )
    state.node_inputs[str(node.id)] = request.to_kwargs()
    tracer.emit(
        "model_request",
        node_id=str(node.id),
        payload={
            "model": model,
            "message_count": len(messages),
            "tool_count": len(tools),
            "request": request.to_kwargs(),
        },
        sensitive_fields=("request",),
    )
    policy = _model_retry_policy(node, workflow)
    try:
        response, attempts = run_with_retry(
            lambda: adapter.create_response(request),
            policy=_exception_retry_policy(policy, "model_error"),
            retry_exceptions=(ModelExecutionError,),
        )
    except ModelExecutionError as exc:
        _record_retry(
            state,
            node,
            "model",
            attempts=policy.max_attempts if _retries_exceptions(policy) else 1,
            outcome="failure",
            final_error=str(exc),
            tracer=tracer,
        )
        raise
    _record_retry(
        state, node, "model", attempts=attempts, outcome="success", tracer=tracer
    )
    tracer.emit(
        "model_response",
        node_id=str(node.id),
        payload={"response_id": response.response_id, "content": response.content},
        sensitive_fields=("content",),
    )
    _record_prompt_cache_provider_telemetry(response, node, tracer)
    _validate_model_output_contract(node, workflow, response, behavior.prompt)
    return response


def _record_prompt_cache_provider_telemetry(
    response: ModelResponse,
    node: RuntimeNode,
    tracer: WorkflowTracer,
) -> None:
    cached_tokens = _read_path(
        response.raw, ("usage", "input_tokens_details", "cached_tokens")
    )
    if cached_tokens is None:
        cached_tokens = _read_path(
            response.raw, ("usage", "prompt_tokens_details", "cached_tokens")
        )
    if cached_tokens is None:
        return
    tracer.emit(
        "prompt_cache_provider_telemetry",
        node_id=str(node.id),
        payload={"cached_tokens": cached_tokens},
    )


def _read_path(value: Any, path: Sequence[str]) -> Any:
    current = value
    for key in path:
        current = _read_value(current, key)
        if current is None:
            return None
    return current


def _execute_tool_step(
    node: RuntimeNode,
    state: WorkflowExecutionState,
    registry: ToolRegistry | None,
    tracer: WorkflowTracer,
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
    tracer.emit(
        "tool_invocation",
        node_id=str(node.id),
        payload={"tool_id": node.tool_id, "arguments": arguments},
        sensitive_fields=("arguments",),
    )
    result = _invoke_tool_with_retry(node, registry, arguments, state, tracer)
    state.tool_results[str(node.id)] = result
    tracer.emit(
        "tool_result",
        node_id=str(node.id),
        payload={
            "tool_id": node.tool_id,
            "success": result.success,
            "error": result.error,
            "output": result.output,
        },
        sensitive_fields=("output",),
    )
    if not result.success and _failure_behavior(node) == "error":
        error = result.error or f"tool {node.tool_id!r} failed"
        state.errors.append(error)
        raise WorkflowExecutionError(error)
    _record_outputs(node, result.output, state)
    return result


def _invoke_tool_with_retry(
    node: RuntimeNode,
    registry: ToolRegistry,
    arguments: Mapping[str, Any],
    state: WorkflowExecutionState,
    tracer: WorkflowTracer,
) -> ToolResult:
    policy = _tool_retry_policy(node, registry)
    retry_failures = _retries_failures(policy)
    max_attempts = policy.max_attempts if retry_failures else 1
    last_result: ToolResult | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = registry.invoke_tool(str(node.tool_id), arguments)
        except ToolRegistryError as exc:
            _record_retry(
                state,
                node,
                "tool",
                attempts=attempt,
                outcome="failure",
                final_error=str(exc),
                tracer=tracer,
            )
            raise
        last_result = result
        if result.success or not retry_failures:
            _record_retry(
                state,
                node,
                "tool",
                attempts=attempt,
                outcome="success",
                tracer=tracer,
            )
            return result
    if last_result is None:
        raise WorkflowExecutionError(f"tool_use_step node {node.id!r} did not run")
    _record_retry(
        state,
        node,
        "tool",
        attempts=max_attempts,
        outcome="failure",
        final_error=last_result.error,
        tracer=tracer,
    )
    return last_result


def _execute_decision_step(
    node: RuntimeNode,
    state: WorkflowExecutionState,
    tracer: WorkflowTracer,
) -> str:
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
    _validate_decision_route(node, route_text)
    tracer.emit("decision", node_id=str(node.id), payload={"route": route_text})
    return route_text


def _render_messages(
    behavior: Any, state: WorkflowExecutionState
) -> tuple[OpenAIMessage, ...]:
    return tuple(message for _part, message in _render_message_parts(behavior, state))


def _render_message_parts(
    behavior: Any, state: WorkflowExecutionState
) -> tuple[tuple[str, OpenAIMessage], ...]:
    prompt_data = behavior.prompt
    context = _format_context(state)
    messages: list[tuple[str, OpenAIMessage]] = []
    for role in ("system", "developer"):
        value = prompt_data.get(role)
        if value is not None:
            messages.append(
                (
                    role,
                    OpenAIMessage(role=role, content=_format_text(str(value), context)),
                )
            )
    for skill in behavior.skills:
        instructions = skill.raw.get("instructions")
        if instructions is None:
            continue
        role = str(skill.raw.get("prompt_role") or "developer")
        messages.append(
            (
                "skill_instructions",
                OpenAIMessage(
                    role=role, content=_format_text(str(instructions), context)
                ),
            )
        )
    user_template = (
        prompt_data.get("user_template") or prompt_data.get("user") or "{prompt}"
    )
    messages.append(
        (
            "user_prompt",
            OpenAIMessage(
                role="user", content=_format_text(str(user_template), context)
            ),
        )
    )
    return tuple(messages)


def _check_prompt_cache(
    workflow: LoadedAgentWorkflow,
    message_parts: Sequence[tuple[str, OpenAIMessage]],
    model: str,
    tracer: WorkflowTracer,
    node: RuntimeNode,
    *,
    prompt_cache: bool | None,
) -> None:
    raw_policy = workflow.runtime_manifest.execution_policy.get("prompt_cache")
    caller_override = "manifest"
    if prompt_cache is False:
        raw_policy = {"enabled": False}
        caller_override = "disabled"
    elif prompt_cache is True and raw_policy is None:
        raw_policy = {"enabled": True}
        caller_override = "enabled"
    elif raw_policy is None:
        raw_policy = None
        caller_override = "manifest_absent"
    policy = prompt_cache_policy_from_value(raw_policy)
    observation = build_prompt_cache_observation(
        policy=policy,
        message_parts=message_parts,
        model=model,
        caller_override=caller_override,
    )
    if observation is None:
        return
    tracer.emit(
        "prompt_cache_checked",
        node_id=str(node.id),
        payload=observation.payload,
    )


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


def _enforce_token_budget(
    node: RuntimeNode,
    workflow: LoadedAgentWorkflow,
    messages: Sequence[OpenAIMessage],
    model: str,
    state: WorkflowExecutionState,
    tracer: WorkflowTracer,
) -> None:
    policy = _token_budget_policy(node, workflow)
    if not policy.enabled:
        return
    budget_model = policy.model or model
    estimate = estimate_messages_tokens(
        tuple(message.to_mapping() for message in messages),
        model=budget_model,
    )
    exceeded = (
        policy.max_prompt_tokens is not None
        and estimate.token_count > policy.max_prompt_tokens
    )
    record = TokenUsageRecord(
        node_id=str(node.id),
        model=budget_model,
        estimated_prompt_tokens=estimate.token_count,
        max_prompt_tokens=policy.max_prompt_tokens,
        encoding_name=estimate.encoding_name,
        used_fallback_encoding=estimate.used_fallback_encoding,
        exceeded=exceeded,
    )
    state.token_usage.append(record)
    tracer.emit(
        "token_budget_checked",
        node_id=str(node.id),
        payload={
            "model": record.model,
            "estimated_prompt_tokens": record.estimated_prompt_tokens,
            "max_prompt_tokens": record.max_prompt_tokens,
            "encoding_name": record.encoding_name,
            "used_fallback_encoding": record.used_fallback_encoding,
            "exceeded": record.exceeded,
        },
    )
    if exceeded and policy.on_exceed == "error":
        raise WorkflowExecutionError(
            f"llm_step node {node.id!r} estimated prompt tokens "
            f"{estimate.token_count} exceeds budget {policy.max_prompt_tokens}"
        )
    if exceeded:
        raise WorkflowExecutionError(
            f"llm_step node {node.id!r} token budget policy on_exceed "
            f"{policy.on_exceed!r} is not supported"
        )


def _validate_model_output_contract(
    node: RuntimeNode,
    workflow: LoadedAgentWorkflow,
    response: ModelResponse,
    prompt: Mapping[str, Any] | None = None,
) -> None:
    contract_ref = _output_schema_ref(node, prompt)
    if not contract_ref:
        return
    contract = workflow.runtime_manifest.output_contracts.get(contract_ref)
    if not isinstance(contract, Mapping):
        raise WorkflowExecutionError(
            f"llm_step node {node.id!r} references unknown output contract "
            f"{contract_ref!r}"
        )
    required_fields = _required_fields(contract)
    if not required_fields:
        return
    output = _structured_model_output(response)
    if isinstance(output, Mapping):
        missing = [field for field in required_fields if field not in output]
        if missing:
            missing_text = ", ".join(repr(field) for field in missing)
            raise WorkflowExecutionError(
                f"llm_step node {node.id!r} output contract {contract_ref!r} "
                f"missing required field(s): {missing_text}"
            )
        return
    if len(required_fields) == 1 and required_fields[0] == "message":
        if response.content:
            return
    raise WorkflowExecutionError(
        f"llm_step node {node.id!r} output contract {contract_ref!r} requires "
        f"structured output fields: {', '.join(required_fields)}"
    )


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


def _output_schema_ref(
    node: RuntimeNode,
    prompt: Mapping[str, Any] | None = None,
) -> str | None:
    value = node.raw.get("output_schema_ref")
    if value is None and isinstance(prompt, Mapping):
        value = prompt.get("output_schema_ref")
    if value is None:
        prompt = node.raw.get("prompt")
        if isinstance(prompt, Mapping):
            value = prompt.get("output_schema_ref")
    return str(value) if value is not None else None


def _required_fields(contract: Mapping[str, Any]) -> tuple[str, ...]:
    value = contract.get("required_fields") or contract.get("required")
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return tuple(str(item) for item in value)
    schema = contract.get("schema")
    if isinstance(schema, Mapping):
        schema_required = schema.get("required")
        if isinstance(schema_required, Sequence) and not isinstance(
            schema_required, (bytes, bytearray, str)
        ):
            return tuple(str(item) for item in schema_required)
    return ()


def _structured_model_output(response: ModelResponse) -> Mapping[str, Any] | None:
    if isinstance(response.raw, Mapping):
        output = response.raw.get("structured_output") or response.raw.get(
            "output_json"
        )
        if isinstance(output, Mapping):
            return output
    if not response.content:
        return None
    try:
        decoded = json.loads(response.content)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, Mapping) else None


def _validate_decision_route(node: RuntimeNode, route: str) -> None:
    allowed_routes = _allowed_routes(node)
    if not allowed_routes:
        return
    if route not in allowed_routes:
        allowed = ", ".join(sorted(repr(item) for item in allowed_routes))
        raise WorkflowExecutionError(
            f"decision_step node {node.id!r} produced route {route!r} outside "
            f"allowed paths: {allowed}"
        )


def _allowed_routes(node: RuntimeNode) -> set[str]:
    contract = node.raw.get("decision_contract")
    if not isinstance(contract, Mapping):
        return set()
    paths = contract.get("allowed_paths")
    if isinstance(paths, Mapping):
        return {str(key) for key in paths}
    if isinstance(paths, Sequence) and not isinstance(paths, (bytes, bytearray, str)):
        routes: set[str] = set()
        for path in paths:
            if isinstance(path, Mapping):
                value = path.get("id") or path.get("route") or path.get("condition")
            else:
                value = path
            if value is not None:
                routes.add(str(value))
        return routes
    return set()


def _edge_condition(edge: RuntimeEdge) -> str | None:
    condition = edge.condition or edge.raw.get("route") or edge.raw.get("when")
    return str(condition) if condition is not None else None


def _failure_behavior(node: RuntimeNode) -> str:
    return str(node.raw.get("failure_behavior") or "error")


def _model_retry_policy(
    node: RuntimeNode,
    workflow: LoadedAgentWorkflow,
) -> RetryPolicy:
    value = node.raw.get("retry_policy")
    if value is None:
        value = workflow.runtime_manifest.execution_policy.get("model_retry_policy")
    if value is None:
        value = workflow.runtime_manifest.execution_policy.get("retry_policy")
    return retry_policy_from_value(value)


def _token_budget_policy(
    node: RuntimeNode,
    workflow: LoadedAgentWorkflow,
) -> TokenBudgetPolicy:
    value = node.raw.get("token_budget") or node.raw.get("token_budget_policy")
    if value is None:
        value = workflow.runtime_manifest.execution_policy.get("token_budget")
    if value is None:
        value = workflow.runtime_manifest.execution_policy.get("token_budget_policy")
    return token_budget_policy_from_value(value)


def _tool_retry_policy(node: RuntimeNode, registry: ToolRegistry) -> RetryPolicy:
    value = node.raw.get("retry_policy")
    if value is None and node.tool_id:
        value = registry.get_tool(node.tool_id).definition.raw.get("retry_policy")
    return retry_policy_from_value(value)


def _exception_retry_policy(policy: RetryPolicy, retry_name: str) -> RetryPolicy:
    if not _retries_exceptions(policy) and retry_name not in policy.retry_on:
        return RetryPolicy()
    return policy


def _retries_exceptions(policy: RetryPolicy) -> bool:
    return bool({"exception", "model_error"} & set(policy.retry_on))


def _retries_failures(policy: RetryPolicy) -> bool:
    return bool({"failure", "tool_failure"} & set(policy.retry_on))


def _record_retry(
    state: WorkflowExecutionState,
    node: RuntimeNode,
    operation: str,
    *,
    attempts: int,
    outcome: str,
    final_error: str | None = None,
    tracer: WorkflowTracer | None = None,
) -> None:
    record = RetryRecord(
        node_id=str(node.id),
        operation=operation,
        attempts=attempts,
        outcome=outcome,
        final_error=final_error,
    )
    state.retry_records.append(record)
    if tracer is not None:
        tracer.emit(
            "retry_recorded",
            node_id=str(node.id),
            payload={
                "operation": record.operation,
                "attempts": record.attempts,
                "outcome": record.outcome,
                "final_error": record.final_error,
            },
        )


def _max_steps(execution_policy: Mapping[str, Any]) -> int | None:
    value = execution_policy.get("max_steps") or execution_policy.get("maximum_steps")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
