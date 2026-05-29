"""Workflow executor for validated dynamic-agent runtime artifacts."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeVar
from uuid import uuid4

from dynamic_agent_runner.behavior import effective_node_behavior
from dynamic_agent_runner.context import WorkflowExecutionContext
from dynamic_agent_runner.errors import (
    ModelExecutionError,
    ToolRegistryError,
    WorkflowExecutionError,
)
from dynamic_agent_runner.hooks import (
    ModelHookContext,
    NodeHookContext,
    ToolHookContext,
    WorkflowHookContext,
    WorkflowLifecycleHooks,
    invoke_lifecycle_hook_async,
)
from dynamic_agent_runner.models import (
    ExecutionPlan,
    LoadedAgentWorkflow,
    PreparedNode,
    RuntimeEdge,
    prepare_execution_plan,
)
from dynamic_agent_runner.openai_client import (
    AsyncOpenAIClientAdapter,
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
    run_with_retry_async,
)
from dynamic_agent_runner.token_budget import (
    TokenBudgetPolicy,
    TokenUsageRecord,
    estimate_messages_tokens,
    token_budget_policy_from_value,
)
from dynamic_agent_runner.tracing import TraceEvent, TraceSink, WorkflowTracer


T = TypeVar("T")


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
    run_id: str | None = None
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


async def execute_workflow_async(
    workflow: LoadedAgentWorkflow | WorkflowExecutionContext,
    *,
    prompt: str,
    tool_registry: ToolRegistry | None = None,
    model_adapter: OpenAIClientAdapter | AsyncOpenAIClientAdapter | None = None,
    max_steps: int | None = None,
    trace_sink: TraceSink | None = None,
    prompt_cache: bool | None = None,
    lifecycle_hooks: WorkflowLifecycleHooks | None = None,
    run_id: str | None = None,
) -> WorkflowResult:
    """Execute a validated workflow from a user prompt asynchronously."""

    if not prompt:
        raise WorkflowExecutionError("workflow execution requires a non-empty prompt")
    context = _normalize_execution_context(
        workflow,
        tool_registry=tool_registry,
        model_adapter=model_adapter,
        max_steps=max_steps,
        trace_sink=trace_sink,
        prompt_cache=prompt_cache,
        lifecycle_hooks=lifecycle_hooks,
    )
    plan = prepare_execution_plan(context.workflow)
    nodes = plan.nodes_by_id
    if not plan.entrypoint_id or plan.entrypoint_id not in nodes:
        raise WorkflowExecutionError("workflow entrypoint does not reference a node")
    adapter = context.model_adapter or AsyncOpenAIClientAdapter()
    state = WorkflowExecutionState(prompt=prompt, run_id=run_id or _new_run_id())
    tracer = WorkflowTracer(
        events=state.trace_events,
        sink=context.trace_sink,
        run_id=state.run_id,
    )
    current_node_id: str | None = plan.entrypoint_id
    limit = context.max_steps or plan.max_steps or (len(nodes) + 10)
    tracer.emit(
        "workflow_started",
        payload={"entrypoint": plan.entrypoint_id, "prompt": prompt},
        sensitive_fields=("prompt",),
    )

    try:
        for _step_index in range(limit):
            if current_node_id is None:
                state.final_result = _last_output(state)
                tracer.emit(
                    "workflow_completed",
                    payload={"final_result": state.final_result},
                    sensitive_fields=("final_result",),
                )
                hooks = context.lifecycle_hooks
                await invoke_lifecycle_hook_async(
                    hooks.registered_hook("after_workflow") if hooks else None,
                    WorkflowHookContext(
                        run_id=state.run_id,
                        final_result=state.final_result,
                    ),
                )
                return WorkflowResult(final_result=state.final_result, state=state)
            node = nodes[current_node_id]
            tracer.emit(
                "node_started",
                node_id=str(node.id),
                payload={"kind": node.kind},
            )
            hooks = context.lifecycle_hooks
            await invoke_lifecycle_hook_async(
                hooks.registered_hook("before_node") if hooks else None,
                NodeHookContext(
                    node_id=str(node.id),
                    kind=str(node.kind),
                    run_id=state.run_id,
                ),
            )
            try:
                output = await _execute_node_async(
                    node,
                    plan,
                    state,
                    context.tool_registry,
                    adapter,
                    tracer,
                    context.prompt_cache,
                    hooks,
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
                NodeExecution(
                    node_id=current_node_id, kind=str(node.kind), output=output
                )
            )
            tracer.emit(
                "node_completed",
                node_id=str(node.id),
                payload={"kind": node.kind, "output": _unwrap_output(output)},
                sensitive_fields=("output",),
            )
            await invoke_lifecycle_hook_async(
                hooks.registered_hook("after_node") if hooks else None,
                NodeHookContext(
                    node_id=str(node.id),
                    kind=str(node.kind),
                    output=_unwrap_output(output),
                    run_id=state.run_id,
                ),
            )
            current_node_id = _next_node_id(
                node, output, plan.edges_by_source.get(current_node_id, ())
            )
    except asyncio.CancelledError:
        tracer.emit(
            "workflow_error",
            payload={"error": "workflow cancelled", "cancelled": True},
        )
        hooks = context.lifecycle_hooks
        await invoke_lifecycle_hook_async(
            hooks.registered_hook("after_workflow") if hooks else None,
            WorkflowHookContext(run_id=state.run_id, error="workflow cancelled"),
        )
        raise

    error = f"workflow exceeded maximum step count {limit}"
    tracer.emit("workflow_error", payload={"error": error})
    hooks = context.lifecycle_hooks
    await invoke_lifecycle_hook_async(
        hooks.registered_hook("after_workflow") if hooks else None,
        WorkflowHookContext(run_id=state.run_id, error=error),
    )
    raise WorkflowExecutionError(error)


def execute_workflow(
    workflow: LoadedAgentWorkflow | WorkflowExecutionContext,
    *,
    prompt: str,
    tool_registry: ToolRegistry | None = None,
    model_adapter: OpenAIClientAdapter | AsyncOpenAIClientAdapter | None = None,
    max_steps: int | None = None,
    trace_sink: TraceSink | None = None,
    prompt_cache: bool | None = None,
    lifecycle_hooks: WorkflowLifecycleHooks | None = None,
    run_id: str | None = None,
) -> WorkflowResult:
    """Execute a validated workflow from a user prompt."""

    return _run_async_from_sync(
        lambda: execute_workflow_async(
            workflow,
            prompt=prompt,
            tool_registry=tool_registry,
            model_adapter=model_adapter,
            max_steps=max_steps,
            trace_sink=trace_sink,
            prompt_cache=prompt_cache,
            lifecycle_hooks=lifecycle_hooks,
            run_id=run_id,
        )
    )


def _run_async_from_sync(operation: Callable[[], Awaitable[T]]) -> T:
    """Run an async operation for synchronous callers when no loop is active."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(operation())
    raise WorkflowExecutionError(
        "cannot use synchronous workflow wrapper while an event loop is running; "
        "use the async API instead"
    )


def _normalize_execution_context(
    workflow: LoadedAgentWorkflow | WorkflowExecutionContext,
    *,
    tool_registry: ToolRegistry | None,
    model_adapter: OpenAIClientAdapter | AsyncOpenAIClientAdapter | None,
    max_steps: int | None,
    trace_sink: TraceSink | None,
    prompt_cache: bool | None,
    lifecycle_hooks: WorkflowLifecycleHooks | None,
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
                lifecycle_hooks,
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
        lifecycle_hooks=lifecycle_hooks,
    )


async def _execute_node_async(
    node: PreparedNode,
    plan: ExecutionPlan,
    state: WorkflowExecutionState,
    registry: ToolRegistry | None,
    adapter: OpenAIClientAdapter | AsyncOpenAIClientAdapter,
    tracer: WorkflowTracer,
    prompt_cache: bool | None,
    lifecycle_hooks: WorkflowLifecycleHooks | None,
) -> Any:
    if node.kind == "llm_step":
        return await _execute_llm_step_async(
            node,
            plan,
            state,
            registry,
            adapter,
            tracer,
            prompt_cache,
            lifecycle_hooks,
        )
    if node.kind == "tool_use_step":
        return await _execute_tool_step_async(
            node, state, registry, tracer, lifecycle_hooks
        )
    if node.kind == "decision_step":
        return _execute_decision_step(node, state, tracer)
    raise WorkflowExecutionError(f"unsupported node kind {node.kind!r}")


def _new_run_id() -> str:
    return str(uuid4())


async def _execute_llm_step_async(
    node: PreparedNode,
    plan: ExecutionPlan,
    state: WorkflowExecutionState,
    registry: ToolRegistry | None,
    adapter: OpenAIClientAdapter | AsyncOpenAIClientAdapter,
    tracer: WorkflowTracer,
    prompt_cache: bool | None,
    lifecycle_hooks: WorkflowLifecycleHooks | None,
) -> ModelResponse:
    workflow = plan.workflow
    behavior = effective_node_behavior(node.source_node, workflow)
    message_parts = _render_message_parts(behavior, state)
    messages = tuple(message for _part, message in message_parts)
    tools: list[dict[str, Any]] = []
    if node.available_tools:
        if registry is None:
            raise WorkflowExecutionError(
                f"llm_step node {node.id!r} exposes tools but no registry was provided"
            )
        tools = registry.to_openai_tools(
            tool.id for tool in registry.list_tools_for_node(node.source_node)
        )
    model = _model_name(node)
    _check_prompt_cache(
        workflow,
        message_parts,
        model,
        tracer,
        node,
        prompt_cache=prompt_cache,
    )
    _enforce_token_budget(node, plan, messages, model, state, tracer)
    request = build_openai_request(
        model=model,
        messages=messages,
        tools=tools,
        tool_choice=node.tool_choice,
        response_format=node.response_format,
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
    await invoke_lifecycle_hook_async(
        lifecycle_hooks.registered_hook("before_model") if lifecycle_hooks else None,
        ModelHookContext(
            node_id=str(node.id),
            model=model,
            request=request.to_kwargs(),
            run_id=state.run_id,
        ),
    )
    policy = _model_retry_policy(node, plan)
    try:
        response, attempts = await run_with_retry_async(
            lambda: _create_model_response_async(adapter, request),
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
    await invoke_lifecycle_hook_async(
        lifecycle_hooks.registered_hook("after_model") if lifecycle_hooks else None,
        ModelHookContext(
            node_id=str(node.id),
            model=model,
            request=request.to_kwargs(),
            response=response,
            run_id=state.run_id,
        ),
    )
    _record_prompt_cache_provider_telemetry(response, node, tracer)
    _validate_model_output_contract(node, plan, response, behavior.prompt)
    return response


async def _create_model_response_async(
    adapter: OpenAIClientAdapter | AsyncOpenAIClientAdapter,
    request: Any,
) -> ModelResponse:
    if isinstance(adapter, AsyncOpenAIClientAdapter):
        return await adapter.create_response(request)
    return await asyncio.to_thread(adapter.create_response, request)


def _record_prompt_cache_provider_telemetry(
    response: ModelResponse,
    node: PreparedNode,
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


async def _execute_tool_step_async(
    node: PreparedNode,
    state: WorkflowExecutionState,
    registry: ToolRegistry | None,
    tracer: WorkflowTracer,
    lifecycle_hooks: WorkflowLifecycleHooks | None,
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
        "tool_started",
        node_id=str(node.id),
        payload={"tool_id": node.tool_id, "arguments": arguments},
        sensitive_fields=("arguments",),
    )
    tracer.emit(
        "tool_invocation",
        node_id=str(node.id),
        payload={"tool_id": node.tool_id, "arguments": arguments},
        sensitive_fields=("arguments",),
    )
    await invoke_lifecycle_hook_async(
        lifecycle_hooks.registered_hook("before_tool") if lifecycle_hooks else None,
        ToolHookContext(
            node_id=str(node.id),
            tool_id=str(node.tool_id),
            arguments=arguments,
            run_id=state.run_id,
        ),
    )
    result = await _invoke_tool_with_retry_async(
        node, registry, arguments, state, tracer
    )
    state.tool_results[str(node.id)] = result
    tracer.emit(
        "tool_result",
        node_id=str(node.id),
        payload=result.trace_payload(),
        sensitive_fields=tuple(dict.fromkeys(("output", *result.sensitive_fields))),
    )
    if not result.success and _failure_behavior(node) == "error":
        error = result.error or f"tool {node.tool_id!r} failed"
        state.errors.append(error)
        tracer.emit(
            "tool_finished",
            node_id=str(node.id),
            payload={
                "tool_id": node.tool_id,
                "success": result.success,
                "error": error,
            },
        )
        await invoke_lifecycle_hook_async(
            lifecycle_hooks.registered_hook("after_tool") if lifecycle_hooks else None,
            ToolHookContext(
                node_id=str(node.id),
                tool_id=str(node.tool_id),
                arguments=arguments,
                result=result,
                error=error,
                run_id=state.run_id,
            ),
        )
        raise WorkflowExecutionError(error)
    if not result.success:
        _emit_status_notice(
            tracer,
            node,
            severity="warning",
            code="tool_failure_fallback",
            message=(
                f"tool {node.tool_id!r} failed; continuing due to "
                f"{_failure_behavior(node)} behavior"
            ),
            payload={"tool_id": node.tool_id, "error": result.error},
        )
    tracer.emit(
        "tool_finished",
        node_id=str(node.id),
        payload={
            "tool_id": node.tool_id,
            "success": result.success,
            "error": result.error,
        },
    )
    await invoke_lifecycle_hook_async(
        lifecycle_hooks.registered_hook("after_tool") if lifecycle_hooks else None,
        ToolHookContext(
            node_id=str(node.id),
            tool_id=str(node.tool_id),
            arguments=arguments,
            result=result,
            error=result.error,
            run_id=state.run_id,
        ),
    )
    _record_outputs(node, result, state)
    return result


def _emit_status_notice(
    tracer: WorkflowTracer,
    node: PreparedNode,
    *,
    severity: str,
    code: str,
    message: str,
    payload: Mapping[str, Any] | None = None,
) -> None:
    notice_payload = {
        "severity": severity,
        "code": code,
        "message": message,
    }
    notice_payload.update(dict(payload or {}))
    tracer.emit("status_notice", node_id=str(node.id), payload=notice_payload)


async def _invoke_tool_with_retry_async(
    node: PreparedNode,
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
            result = await registry.invoke_tool_async(str(node.tool_id), arguments)
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
    node: PreparedNode,
    state: WorkflowExecutionState,
    tracer: WorkflowTracer,
) -> str:
    if node.decision_subtype != "llm_route":
        raise WorkflowExecutionError(
            f"decision_step node {node.id!r} has unsupported decision_subtype "
            f"{node.decision_subtype!r}"
        )
    route = _resolve_value(node.route_from, state)
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
    node: PreparedNode,
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


def _tool_arguments(
    node: PreparedNode, state: WorkflowExecutionState
) -> dict[str, Any]:
    arguments: dict[str, Any] = dict(node.inputs)
    inputs_from = node.inputs_from
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
    node: PreparedNode, output: Any, state: WorkflowExecutionState
) -> None:
    outputs = node.outputs
    if isinstance(outputs, Mapping):
        state_key = outputs.get("state_key") or outputs.get("key")
        if state_key:
            state.node_outputs[str(state_key)] = _unwrap_output(output)


def _enforce_token_budget(
    node: PreparedNode,
    plan: ExecutionPlan,
    messages: Sequence[OpenAIMessage],
    model: str,
    state: WorkflowExecutionState,
    tracer: WorkflowTracer,
) -> None:
    policy = _token_budget_policy(node, plan)
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
    node: PreparedNode,
    plan: ExecutionPlan,
    response: ModelResponse,
    prompt: Mapping[str, Any] | None = None,
) -> None:
    contract_ref = _output_schema_ref(node, prompt)
    if not contract_ref:
        return
    contract = plan.output_contracts.get(contract_ref)
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
    node: PreparedNode,
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


def _model_name(node: PreparedNode) -> str:
    if node.model is None:
        raise WorkflowExecutionError(f"llm_step node {node.id!r} is missing model")
    return node.model


def _model_parameters(node: PreparedNode) -> dict[str, Any]:
    return dict(node.model_parameters)


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
            context[key] = value.model_facing_output
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
        return value.model_facing_output
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
    node: PreparedNode,
    prompt: Mapping[str, Any] | None = None,
) -> str | None:
    value = node.output_schema_ref
    if value is None and isinstance(prompt, Mapping):
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


def _validate_decision_route(node: PreparedNode, route: str) -> None:
    allowed_routes = node.allowed_routes
    if not allowed_routes:
        return
    if route not in allowed_routes:
        allowed = ", ".join(sorted(repr(item) for item in allowed_routes))
        raise WorkflowExecutionError(
            f"decision_step node {node.id!r} produced route {route!r} outside "
            f"allowed paths: {allowed}"
        )


def _edge_condition(edge: RuntimeEdge) -> str | None:
    condition = edge.condition or edge.raw.get("route") or edge.raw.get("when")
    return str(condition) if condition is not None else None


def _failure_behavior(node: PreparedNode) -> str:
    return node.failure_behavior


def _model_retry_policy(
    node: PreparedNode,
    plan: ExecutionPlan,
) -> RetryPolicy:
    value = node.retry_policy
    if value is None:
        value = plan.execution_policy.get("model_retry_policy")
    if value is None:
        value = plan.execution_policy.get("retry_policy")
    return retry_policy_from_value(value)


def _token_budget_policy(
    node: PreparedNode,
    plan: ExecutionPlan,
) -> TokenBudgetPolicy:
    value = node.token_budget_policy
    if value is None:
        value = plan.execution_policy.get("token_budget")
    if value is None:
        value = plan.execution_policy.get("token_budget_policy")
    return token_budget_policy_from_value(value)


def _tool_retry_policy(node: PreparedNode, registry: ToolRegistry) -> RetryPolicy:
    value = node.retry_policy
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
    node: PreparedNode,
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
