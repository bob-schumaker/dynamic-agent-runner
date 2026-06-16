"""Workflow executor for validated dynamic-agent runtime artifacts."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar
from uuid import uuid4

from openai_model_registry import ModelRegistry
from openai_model_registry.errors import ModelNotSupportedError

from dynamic_agent_runner.behavior import effective_node_behavior
from dynamic_agent_runner.context import WorkflowExecutionContext
from dynamic_agent_runner.errors import (
    GuardrailExecutionError,
    ModelExecutionError,
    ToolRegistryError,
    WorkflowExecutionError,
)
from dynamic_agent_runner.guardrails import GuardrailDecision, InMemoryGuardrailRegistry
from dynamic_agent_runner.graph_mutation import ContextPruningMutation
from dynamic_agent_runner.hooks import (
    ModelHookContext,
    NodeHookContext,
    ToolHookContext,
    WorkflowHookContext,
    WorkflowLifecycleHooks,
    invoke_lifecycle_hook_async,
)
from dynamic_agent_runner.models import (
    CompiledAgentWorkflow,
    ExecutionPlan,
    LoadedAgentWorkflow,
    PreparedNode,
    RuntimeEdge,
    prepare_execution_plan,
)
from dynamic_agent_runner.openai_client import (
    AsyncOpenAIClientAdapter,
    ModelToolCall,
    ModelResponse,
    OpenAIClientAdapter,
    OpenAIMessage,
    build_openai_request,
)
from dynamic_agent_runner.prompt_cache import (
    build_prompt_cache_observation,
    prompt_cache_policy_from_value,
)
from dynamic_agent_runner.registry import RegisteredTool, ToolRegistry, ToolResult
from dynamic_agent_runner.retry import (
    RetryPolicy,
    RetryRecord,
    retry_policy_from_value,
    run_with_retry_async,
)
from dynamic_agent_runner.skill_sources import (
    RejectedSkillSource,
    SkillSourceResolutionError,
    enforce_node_skill_source_budget,
    resolve_package_bundled_skill_source,
)
from dynamic_agent_runner.token_budget import (
    TokenBudgetPolicy,
    TokenUsageRecord,
    estimate_messages_tokens,
    token_budget_policy_from_value,
)
from dynamic_agent_runner.tracing import TraceEvent, TraceSink, WorkflowTracer


T = TypeVar("T")
ModelAdapter = OpenAIClientAdapter | AsyncOpenAIClientAdapter


@dataclass(frozen=True)
class NodeExecution:
    """Execution record for a completed runtime node."""

    node_id: str
    kind: str
    output: Any = None
    error: str | None = None


class ApprovalInterruptionState(str, Enum):
    """Lifecycle state for an approval interruption."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAILED = "failed"


@dataclass(frozen=True)
class ApprovalInterruption:
    """Structured pause record for an approval-required runtime action."""

    interruption_id: str
    run_id: str
    workflow_id: str
    node_id: str
    tool_id: str | None = None
    action_id: str | None = None
    arguments: Mapping[str, Any] = field(default_factory=dict)
    policy: Mapping[str, Any] = field(default_factory=dict)
    reason: str = ""
    state: ApprovalInterruptionState = ApprovalInterruptionState.PENDING
    schema_version: int = 1


@dataclass
class WorkflowExecutionState:
    """Mutable execution state accumulated while a workflow runs."""

    prompt: str
    run_id: str | None = None
    session_messages: tuple[OpenAIMessage, ...] = field(default_factory=tuple)
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


@dataclass(frozen=True)
class WorkflowInterruptedResult:
    """Workflow execution result returned when approval pauses execution."""

    final_result: None
    state: WorkflowExecutionState
    interruption: ApprovalInterruption


@dataclass(frozen=True)
class PreparedInputMetadata:
    """Preparation-stage metadata for one rendered model input."""

    hierarchy_applied: bool = False
    session_messages_included: int = 0
    session_messages_pruned: int = 0
    context_compaction_applied: bool = False
    file_context_applied: bool = False
    file_context_sources: tuple[str, ...] = ()
    file_context_files_included: int = 0
    file_context_bytes: int = 0
    file_context_estimated_tokens: int = 0
    mutation_applied: bool = False
    mutation_id: str | None = None
    mutation_output_slots: tuple[str, ...] = ()
    skill_sources_loaded: tuple[Mapping[str, Any], ...] = ()
    skill_sources_omitted: tuple[Mapping[str, Any], ...] = ()
    skill_sources_rejected: tuple[Mapping[str, Any], ...] = ()
    turn_count: int = 0
    segment_count: int = 0
    turns: tuple[Mapping[str, Any], ...] = ()
    segments: tuple[Mapping[str, Any], ...] = ()
    context_threshold: Mapping[str, Any] = field(default_factory=dict)
    compression_profile: str | None = None
    lane_budgets: Mapping[str, int] = field(default_factory=dict)
    selection_policy: Mapping[str, Any] = field(default_factory=dict)
    lifecycle_stages: tuple[Mapping[str, Any], ...] = ()
    metrics: tuple[str, ...] = ()


@dataclass(frozen=True)
class _SkillSourcePreparation:
    loaded: tuple[Mapping[str, Any], ...] = ()
    omitted: tuple[Mapping[str, Any], ...] = ()
    rejected: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class _RenderedMessageParts:
    message_parts: tuple[tuple[str, OpenAIMessage], ...]
    skill_source_preparation: _SkillSourcePreparation = field(
        default_factory=_SkillSourcePreparation
    )


@dataclass(frozen=True)
class PreparedModelInput:
    """Rendered model input and named prompt parts for one LLM step."""

    node_id: str
    model: str
    adapter: ModelAdapter
    messages: tuple[OpenAIMessage, ...]
    message_parts: tuple[tuple[str, OpenAIMessage], ...]
    named_parts: Mapping[str, OpenAIMessage]
    prompt: Mapping[str, Any]
    preparation: PreparedInputMetadata = field(default_factory=PreparedInputMetadata)
    model_parameters: Mapping[str, Any] = field(default_factory=dict)
    tool_choice: Any = None
    response_format: Mapping[str, Any] | None = None

    @property
    def part_names(self) -> tuple[str, ...]:
        """Return prompt part names in rendered model-message order."""

        return tuple(part for part, _message in self.message_parts)


async def execute_workflow_async(
    workflow: LoadedAgentWorkflow | CompiledAgentWorkflow | WorkflowExecutionContext,
    *,
    prompt: str,
    tool_registry: ToolRegistry | None = None,
    guardrail_registry: InMemoryGuardrailRegistry | None = None,
    model_adapter: ModelAdapter | Sequence[ModelAdapter] | None = None,
    max_steps: int | None = None,
    trace_sink: TraceSink | None = None,
    prompt_cache: bool | None = None,
    lifecycle_hooks: WorkflowLifecycleHooks | None = None,
    model_adapter_coverage: str | None = None,
    run_id: str | None = None,
) -> WorkflowResult | WorkflowInterruptedResult:
    """Execute a validated workflow from a user prompt asynchronously."""

    if not prompt:
        raise WorkflowExecutionError("workflow execution requires a non-empty prompt")
    context = _normalize_execution_context(
        workflow,
        tool_registry=tool_registry,
        guardrail_registry=guardrail_registry,
        model_adapter=model_adapter,
        max_steps=max_steps,
        trace_sink=trace_sink,
        prompt_cache=prompt_cache,
        lifecycle_hooks=lifecycle_hooks,
        model_adapter_coverage=model_adapter_coverage,
    )
    plan = prepare_execution_plan(context.workflow)
    nodes = plan.nodes_by_id
    if not plan.entrypoint_id or plan.entrypoint_id not in nodes:
        raise WorkflowExecutionError("workflow entrypoint does not reference a node")
    adapters = _normalize_model_adapters(context.model_adapter)
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
        _run_input_guardrails(plan, state, context.guardrail_registry, tracer)
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
                    adapters,
                    tracer,
                    context.prompt_cache,
                    hooks,
                    context.model_adapter_coverage,
                )
            except Exception as exc:
                tracer.emit(
                    "node_error",
                    node_id=str(node.id),
                    payload={"kind": node.kind, "error": str(exc)},
                )
                raise
            if isinstance(output, WorkflowInterruptedResult):
                return output
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
    workflow: LoadedAgentWorkflow | CompiledAgentWorkflow | WorkflowExecutionContext,
    *,
    prompt: str,
    tool_registry: ToolRegistry | None = None,
    guardrail_registry: InMemoryGuardrailRegistry | None = None,
    model_adapter: ModelAdapter | Sequence[ModelAdapter] | None = None,
    max_steps: int | None = None,
    trace_sink: TraceSink | None = None,
    prompt_cache: bool | None = None,
    lifecycle_hooks: WorkflowLifecycleHooks | None = None,
    model_adapter_coverage: str | None = None,
    run_id: str | None = None,
) -> WorkflowResult | WorkflowInterruptedResult:
    """Execute a validated workflow from a user prompt."""

    return _run_async_from_sync(
        lambda: execute_workflow_async(
            workflow,
            prompt=prompt,
            tool_registry=tool_registry,
            guardrail_registry=guardrail_registry,
            model_adapter=model_adapter,
            max_steps=max_steps,
            trace_sink=trace_sink,
            prompt_cache=prompt_cache,
            lifecycle_hooks=lifecycle_hooks,
            model_adapter_coverage=model_adapter_coverage,
            run_id=run_id,
        )
    )


def prepare_model_input(
    node: PreparedNode,
    plan: ExecutionPlan,
    state: WorkflowExecutionState,
    *,
    model_adapters: Sequence[ModelAdapter] | None = None,
    tracer: WorkflowTracer | None = None,
    prompt_cache: bool | None = None,
    model_adapter_coverage: str = "augmented",
) -> PreparedModelInput:
    """Prepare rendered model input for an ``llm_step`` node."""

    workflow = plan.workflow
    behavior = effective_node_behavior(node.source_node, workflow)
    model, adapter = _select_model_and_adapter(
        node,
        model_adapters or (),
        _execution_policy_model_map(plan.execution_policy),
        model_adapter_coverage=model_adapter_coverage,
    )
    render_context, mutation_preparation = _prepare_model_input_render_context(
        node, state
    )
    rendered_parts = _render_message_parts_with_skill_sources(
        behavior,
        state,
        context=render_context,
        workflow=workflow,
        node_id=str(node.id),
    )
    message_parts, preparation = _apply_prepare_model_input_stage(
        rendered_parts.message_parts,
        plan,
        state,
        model=model,
        adapter=adapter,
    )
    preparation = _merge_prepared_input_metadata(preparation, mutation_preparation)
    preparation = _merge_skill_source_preparation(
        preparation,
        rendered_parts.skill_source_preparation,
    )
    messages = tuple(message for _part, message in message_parts)
    if tracer is not None:
        tracer.emit(
            "model_input_prepared",
            node_id=str(node.id),
            payload={
                "part_names": tuple(part for part, _message in message_parts),
                "hierarchy_applied": preparation.hierarchy_applied,
                "session_messages_included": preparation.session_messages_included,
                "session_messages_pruned": preparation.session_messages_pruned,
                "context_compaction_applied": preparation.context_compaction_applied,
                "file_context_applied": preparation.file_context_applied,
                "file_context_sources": preparation.file_context_sources,
                "file_context_files_included": preparation.file_context_files_included,
                "file_context_bytes": preparation.file_context_bytes,
                "file_context_estimated_tokens": preparation.file_context_estimated_tokens,
                "mutation_applied": preparation.mutation_applied,
                "mutation_id": preparation.mutation_id,
                "mutation_output_slots": preparation.mutation_output_slots,
                "skill_sources_loaded": preparation.skill_sources_loaded,
                "skill_sources_omitted": preparation.skill_sources_omitted,
                "skill_sources_rejected": preparation.skill_sources_rejected,
                "turn_count": preparation.turn_count,
                "segment_count": preparation.segment_count,
                "context_threshold": preparation.context_threshold,
                "compression_profile": preparation.compression_profile,
                "lane_budgets": preparation.lane_budgets,
                "selection_policy": preparation.selection_policy,
                "lifecycle_stages": preparation.lifecycle_stages,
                "metrics": preparation.metrics,
            },
        )
    if preparation.skill_sources_rejected:
        raise WorkflowExecutionError(
            f"skill source resolution failed for llm_step node {node.id!r}"
        )
    if tracer is not None:
        _check_prompt_cache(
            workflow,
            message_parts,
            model,
            tracer,
            node,
            prompt_cache=prompt_cache,
        )
        _enforce_token_budget(node, plan, messages, model, state, tracer)
    return PreparedModelInput(
        node_id=str(node.id),
        model=model,
        adapter=adapter,
        messages=messages,
        message_parts=message_parts,
        named_parts=dict(message_parts),
        prompt=behavior.prompt,
        preparation=preparation,
        model_parameters=_model_parameters(node),
        tool_choice=node.tool_choice,
        response_format=node.response_format,
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
    workflow: LoadedAgentWorkflow | CompiledAgentWorkflow | WorkflowExecutionContext,
    *,
    tool_registry: ToolRegistry | None,
    guardrail_registry: InMemoryGuardrailRegistry | None,
    model_adapter: ModelAdapter | Sequence[ModelAdapter] | None,
    max_steps: int | None,
    trace_sink: TraceSink | None,
    prompt_cache: bool | None,
    lifecycle_hooks: WorkflowLifecycleHooks | None,
    model_adapter_coverage: str | None,
) -> WorkflowExecutionContext:
    if isinstance(workflow, WorkflowExecutionContext):
        if any(
            value is not None
            for value in (
                tool_registry,
                guardrail_registry,
                model_adapter,
                max_steps,
                trace_sink,
                prompt_cache,
                lifecycle_hooks,
                model_adapter_coverage,
            )
        ):
            raise WorkflowExecutionError(
                "execution context cannot be combined with runtime keyword arguments"
            )
        _normalize_model_adapter_coverage(workflow.model_adapter_coverage)
        return workflow
    normalized_coverage = _normalize_model_adapter_coverage(model_adapter_coverage)
    return WorkflowExecutionContext(
        workflow=workflow,
        tool_registry=tool_registry,
        guardrail_registry=guardrail_registry,
        model_adapter=model_adapter,
        max_steps=max_steps,
        trace_sink=trace_sink,
        prompt_cache=prompt_cache,
        lifecycle_hooks=lifecycle_hooks,
        model_adapter_coverage=normalized_coverage,
    )


async def _execute_node_async(
    node: PreparedNode,
    plan: ExecutionPlan,
    state: WorkflowExecutionState,
    registry: ToolRegistry | None,
    model_adapters: Sequence[ModelAdapter],
    tracer: WorkflowTracer,
    prompt_cache: bool | None,
    lifecycle_hooks: WorkflowLifecycleHooks | None,
    model_adapter_coverage: str,
) -> Any:
    if node.kind == "llm_step":
        return await _execute_llm_step_async(
            node,
            plan,
            state,
            registry,
            model_adapters,
            tracer,
            prompt_cache,
            lifecycle_hooks,
            model_adapter_coverage,
        )
    if node.kind == "tool_use_step":
        return await _execute_tool_step_async(
            node, plan, state, registry, tracer, lifecycle_hooks
        )
    if node.kind == "decision_step":
        return _execute_decision_step(node, state, tracer)
    raise WorkflowExecutionError(f"unsupported node kind {node.kind!r}")


def _new_run_id() -> str:
    return str(uuid4())


def _new_approval_id() -> str:
    return str(uuid4())


def _approval_required(tool: RegisteredTool) -> bool:
    value = (
        tool.definition.policy.approval_required or tool.definition.approval_required
    )
    return str(value).strip().lower() in {"1", "true", "yes", "required"}


def _tool_policy_payload(tool: RegisteredTool) -> dict[str, str]:
    policy = tool.definition.policy
    payload: dict[str, str] = {}
    for key, value in (
        ("approval_required", policy.approval_required),
        ("side_effect", policy.side_effect),
        ("sandbox", policy.sandbox),
        ("timeout", policy.timeout),
        ("retry_policy", policy.retry_policy),
        ("failure_behavior", policy.failure_behavior),
    ):
        if value is not None:
            payload[key] = str(value)
    return payload


def _run_input_guardrails(
    plan: ExecutionPlan,
    state: WorkflowExecutionState,
    guardrail_registry: InMemoryGuardrailRegistry | None,
    tracer: WorkflowTracer,
) -> None:
    for declaration in plan.workflow.runtime_manifest.guardrails:
        if declaration.phase != "input":
            continue
        guardrail_id = str(declaration.id)
        if guardrail_registry is None or not guardrail_registry.has_guardrail(
            guardrail_id
        ):
            error = f"input guardrail {guardrail_id!r} has no registered adapter"
            tracer.emit(
                "workflow_error",
                payload={"error": error, "guardrail_id": guardrail_id},
            )
            raise GuardrailExecutionError(error)
        tracer.emit(
            "guardrail_started",
            payload={
                "guardrail_id": guardrail_id,
                "phase": "input",
                "subject": state.prompt,
            },
            sensitive_fields=("subject",),
        )
        result = guardrail_registry.run(guardrail_id, state.prompt)
        if result.decision is GuardrailDecision.PASS:
            tracer.emit(
                "guardrail_passed",
                payload={
                    "guardrail_id": guardrail_id,
                    "phase": result.phase,
                    "reason_code": result.reason_code,
                },
            )
            continue
        if result.decision is GuardrailDecision.ABORT:
            error = f"input guardrail {guardrail_id!r} aborted workflow" + (
                f": {result.reason_code}" if result.reason_code else ""
            )
            tracer.emit(
                "guardrail_aborted",
                payload={
                    "guardrail_id": guardrail_id,
                    "phase": result.phase,
                    "reason_code": result.reason_code,
                    "message": result.message,
                },
            )
            tracer.emit(
                "workflow_error",
                payload={"error": error, "guardrail_id": guardrail_id},
            )
            raise GuardrailExecutionError(error)
        error = f"input guardrail {guardrail_id!r} returned unsupported decision"
        tracer.emit(
            "workflow_error",
            payload={"error": error, "guardrail_id": guardrail_id},
        )
        raise GuardrailExecutionError(error)


async def _execute_llm_step_async(
    node: PreparedNode,
    plan: ExecutionPlan,
    state: WorkflowExecutionState,
    registry: ToolRegistry | None,
    model_adapters: Sequence[ModelAdapter],
    tracer: WorkflowTracer,
    prompt_cache: bool | None,
    lifecycle_hooks: WorkflowLifecycleHooks | None,
    model_adapter_coverage: str,
) -> ModelResponse:
    prepared_input = prepare_model_input(
        node,
        plan,
        state,
        model_adapters=model_adapters,
        tracer=tracer,
        prompt_cache=prompt_cache,
        model_adapter_coverage=model_adapter_coverage,
    )
    tools: list[dict[str, Any]] = []
    exposed_tools: tuple[RegisteredTool, ...] = ()
    if node.available_tools:
        if registry is None:
            raise WorkflowExecutionError(
                f"llm_step node {node.id!r} exposes tools but no registry was provided"
            )
        exposed_tools = registry.list_tools_for_node(node.source_node)
        tools = registry.to_openai_tools(tool.id for tool in exposed_tools)
    request = build_openai_request(
        model=prepared_input.model,
        messages=prepared_input.messages,
        tools=tools,
        tool_choice=prepared_input.tool_choice,
        response_format=prepared_input.response_format,
        **prepared_input.model_parameters,
    )
    state.node_inputs[str(node.id)] = request.to_kwargs()
    tracer.emit(
        "model_request",
        node_id=str(node.id),
        payload={
            "model": prepared_input.model,
            "message_count": len(prepared_input.messages),
            "tool_count": len(tools),
            "tool_sources": _tool_sources_payload(exposed_tools),
            "request": request.to_kwargs(),
        },
        sensitive_fields=("request",),
    )
    await invoke_lifecycle_hook_async(
        lifecycle_hooks.registered_hook("before_model") if lifecycle_hooks else None,
        ModelHookContext(
            node_id=str(node.id),
            model=prepared_input.model,
            request=request.to_kwargs(),
            run_id=state.run_id,
        ),
    )
    policy = _model_retry_policy(node, plan)
    try:
        response, attempts = await run_with_retry_async(
            lambda: _create_model_response_async(prepared_input.adapter, request),
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
            model=prepared_input.model,
            request=request.to_kwargs(),
            response=response,
            run_id=state.run_id,
        ),
    )
    _record_prompt_cache_provider_telemetry(response, node, tracer)
    if not _iterative_loop_enabled(plan):
        _validate_model_output_contract(node, plan, response, prepared_input.prompt)
        return response
    loop_output = await _execute_model_tool_loop_async(
        node,
        plan,
        state,
        registry,
        prepared_input,
        response,
        tools,
        exposed_tools,
        tracer,
        lifecycle_hooks,
    )
    if isinstance(loop_output, WorkflowInterruptedResult):
        return loop_output
    response = loop_output
    _validate_model_output_contract(node, plan, response, prepared_input.prompt)
    return response


def _iterative_loop_enabled(plan: ExecutionPlan) -> bool:
    policy = plan.tool_use_completion_policy
    return bool(policy is not None and policy.run_again == "required")


async def _execute_model_tool_loop_async(
    node: PreparedNode,
    plan: ExecutionPlan,
    state: WorkflowExecutionState,
    registry: ToolRegistry | None,
    prepared_input: PreparedModelInput,
    initial_response: ModelResponse,
    tools: Sequence[Mapping[str, Any]],
    exposed_tools: Sequence[RegisteredTool],
    tracer: WorkflowTracer,
    lifecycle_hooks: WorkflowLifecycleHooks | None,
) -> ModelResponse | WorkflowInterruptedResult:
    if not initial_response.tool_calls:
        return initial_response
    if registry is None:
        raise WorkflowExecutionError(
            f"llm_step node {node.id!r} requested tools but no registry was provided"
        )

    response = initial_response
    transcript: list[Mapping[str, Any]] = []
    max_iterations = plan.max_steps or 8
    tracer.emit(
        "model_tool_loop_started",
        node_id=str(node.id),
        payload={"max_iterations": max_iterations, "tool_count": len(exposed_tools)},
    )
    for iteration in range(1, max_iterations + 1):
        if not response.tool_calls:
            _emit_model_tool_loop_stop(
                node,
                plan,
                response,
                tracer,
                iteration=iteration,
                stop_reason="final_model_output",
            )
            return response
        tracer.emit(
            "model_tool_loop_turn_started",
            node_id=str(node.id),
            payload={
                "iteration": iteration,
                "tool_call_count": len(response.tool_calls),
            },
        )
        for tool_call in response.tool_calls:
            tool_call_id = _model_tool_call_id(tool_call, iteration)
            try:
                result = await _invoke_model_tool_call_async(
                    node,
                    plan,
                    tool_call,
                    tool_call_id,
                    iteration,
                    registry,
                    exposed_tools,
                    state,
                    tracer,
                    lifecycle_hooks,
                )
            except WorkflowExecutionError:
                tracer.emit(
                    "model_tool_loop_stopped",
                    node_id=str(node.id),
                    payload={
                        "iteration": iteration,
                        "stop_reason": "tool_failure",
                    },
                )
                raise
            if isinstance(result, WorkflowInterruptedResult):
                tracer.emit(
                    "model_tool_loop_stopped",
                    node_id=str(node.id),
                    payload={
                        "iteration": iteration,
                        "stop_reason": "approval_interruption",
                    },
                )
                return result
            transcript.extend(
                _model_tool_result_messages(tool_call, tool_call_id, result)
            )
        if _stop_on_tool_enabled(plan):
            _emit_model_tool_loop_stop(
                node,
                plan,
                response,
                tracer,
                iteration=iteration,
                stop_reason="stop_on_tool",
            )
            return response
        response = await _request_loop_model_response_async(
            node,
            plan,
            state,
            prepared_input,
            tuple(tools),
            tuple(transcript),
            tracer,
            lifecycle_hooks,
        )
    tracer.emit(
        "model_tool_loop_stopped",
        node_id=str(node.id),
        payload={"iteration": max_iterations, "stop_reason": "max_iterations"},
    )
    raise WorkflowExecutionError(
        f"llm_step node {node.id!r} exceeded iterative tool loop limit {max_iterations}"
    )


async def _request_loop_model_response_async(
    node: PreparedNode,
    plan: ExecutionPlan,
    state: WorkflowExecutionState,
    prepared_input: PreparedModelInput,
    tools: Sequence[Mapping[str, Any]],
    transcript: Sequence[Mapping[str, Any]],
    tracer: WorkflowTracer,
    lifecycle_hooks: WorkflowLifecycleHooks | None,
) -> ModelResponse:
    messages = (*prepared_input.messages, *transcript)
    request = build_openai_request(
        model=prepared_input.model,
        messages=messages,
        tools=tools,
        tool_choice=prepared_input.tool_choice,
        response_format=prepared_input.response_format,
        **prepared_input.model_parameters,
    )
    state.node_inputs[str(node.id)] = request.to_kwargs()
    tracer.emit(
        "model_request",
        node_id=str(node.id),
        payload={
            "model": prepared_input.model,
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
            model=prepared_input.model,
            request=request.to_kwargs(),
            run_id=state.run_id,
        ),
    )
    policy = _model_retry_policy(node, plan)
    try:
        response, attempts = await run_with_retry_async(
            lambda: _create_model_response_async(prepared_input.adapter, request),
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
            model=prepared_input.model,
            request=request.to_kwargs(),
            response=response,
            run_id=state.run_id,
        ),
    )
    _record_prompt_cache_provider_telemetry(response, node, tracer)
    return response


async def _invoke_model_tool_call_async(
    node: PreparedNode,
    plan: ExecutionPlan,
    tool_call: ModelToolCall,
    tool_call_id: str,
    iteration: int,
    registry: ToolRegistry,
    exposed_tools: Sequence[RegisteredTool],
    state: WorkflowExecutionState,
    tracer: WorkflowTracer,
    lifecycle_hooks: WorkflowLifecycleHooks | None,
) -> ToolResult | WorkflowInterruptedResult:
    tool = _exposed_model_tool(tool_call, exposed_tools)
    arguments = _model_tool_arguments(tool_call)
    tracer.emit(
        "model_tool_loop_tool_call",
        node_id=str(node.id),
        payload={
            "iteration": iteration,
            "tool_call_id": tool_call_id,
            "tool_id": tool.id,
            "arguments": arguments,
        },
        sensitive_fields=("arguments",),
    )
    if _approval_required(tool):
        interruption = ApprovalInterruption(
            interruption_id=_new_approval_id(),
            run_id=str(state.run_id),
            workflow_id=str(plan.workflow.runtime_manifest.package_id),
            node_id=str(node.id),
            tool_id=tool.id,
            action_id=tool_call_id,
            arguments=arguments,
            policy=_tool_policy_payload(tool),
            reason=f"model tool {tool.id!r} requires approval",
        )
        tracer.emit(
            "approval_requested",
            node_id=str(node.id),
            payload={
                "interruption_id": interruption.interruption_id,
                "tool_id": tool.id,
                "tool_call_id": tool_call_id,
                "arguments": arguments,
                "policy": interruption.policy,
                "reason": interruption.reason,
            },
            sensitive_fields=("arguments",),
        )
        tracer.emit(
            "approval_paused",
            node_id=str(node.id),
            payload={
                "interruption_id": interruption.interruption_id,
                "tool_id": tool.id,
                "tool_call_id": tool_call_id,
                "state": interruption.state.value,
            },
        )
        return WorkflowInterruptedResult(
            final_result=None,
            state=state,
            interruption=interruption,
        )
    tracer.emit(
        "tool_started",
        node_id=str(node.id),
        payload={
            "tool_id": tool.id,
            "tool_call_id": tool_call_id,
            "arguments": arguments,
        },
        sensitive_fields=("arguments",),
    )
    await invoke_lifecycle_hook_async(
        lifecycle_hooks.registered_hook("before_tool") if lifecycle_hooks else None,
        ToolHookContext(
            node_id=str(node.id),
            tool_id=tool.id,
            arguments=arguments,
            run_id=state.run_id,
        ),
    )
    result = await registry.invoke_tool_async(tool.id, arguments)
    state.tool_results[f"{node.id}.{tool_call_id}"] = result
    tracer.emit(
        "tool_result",
        node_id=str(node.id),
        payload={"tool_call_id": tool_call_id, **result.trace_payload()},
        sensitive_fields=tuple(dict.fromkeys(("output", *result.sensitive_fields))),
    )
    tracer.emit(
        "tool_finished",
        node_id=str(node.id),
        payload={
            "tool_id": tool.id,
            "tool_call_id": tool_call_id,
            "success": result.success,
            "error": result.error,
        },
    )
    await invoke_lifecycle_hook_async(
        lifecycle_hooks.registered_hook("after_tool") if lifecycle_hooks else None,
        ToolHookContext(
            node_id=str(node.id),
            tool_id=tool.id,
            arguments=arguments,
            result=result,
            error=result.error,
            run_id=state.run_id,
        ),
    )
    if not result.success:
        raise WorkflowExecutionError(result.error or f"tool {tool.id!r} failed")
    return result


def _emit_model_tool_loop_stop(
    node: PreparedNode,
    plan: ExecutionPlan,
    response: ModelResponse,
    tracer: WorkflowTracer,
    *,
    iteration: int,
    stop_reason: str,
) -> None:
    tracer.emit(
        "model_tool_loop_stopped",
        node_id=str(node.id),
        payload={"iteration": iteration, "stop_reason": stop_reason},
    )
    policy = plan.tool_use_completion_policy
    tracer.emit(
        "model_tool_loop_final_output",
        node_id=str(node.id),
        payload={
            "final_output": response.content,
            "final_output_policy": policy.final_output if policy else "default",
            "stop_reason": stop_reason,
        },
        sensitive_fields=("final_output",),
    )


def _exposed_model_tool(
    tool_call: ModelToolCall, exposed_tools: Sequence[RegisteredTool]
) -> RegisteredTool:
    for tool in exposed_tools:
        if tool.id == tool_call.name:
            return tool
    raise WorkflowExecutionError(f"model requested unavailable tool {tool_call.name!r}")


def _model_tool_arguments(tool_call: ModelToolCall) -> dict[str, Any]:
    arguments = tool_call.arguments
    if isinstance(arguments, Mapping):
        return dict(arguments)
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise WorkflowExecutionError(
                f"model tool call {tool_call.name!r} arguments must be JSON"
            ) from exc
        if isinstance(parsed, Mapping):
            return dict(parsed)
    raise WorkflowExecutionError(
        f"model tool call {tool_call.name!r} arguments must be an object"
    )


def _model_tool_call_id(tool_call: ModelToolCall, iteration: int) -> str:
    if tool_call.id:
        return tool_call.id
    return f"turn_{iteration}_{tool_call.name}"


def _model_tool_result_messages(
    tool_call: ModelToolCall, tool_call_id: str, result: ToolResult
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    return (
        {
            "role": "assistant",
            "content": f"Tool call {tool_call_id}: {tool_call.name}",
        },
        {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_call.name,
            "content": json.dumps(result.model_facing_output),
        },
    )


def _stop_on_tool_enabled(plan: ExecutionPlan) -> bool:
    policy = plan.tool_use_completion_policy
    return bool(policy is not None and policy.stop_on_tool == "enabled")


def _tool_sources_payload(tools: Sequence[RegisteredTool]) -> dict[str, Any]:
    """Return trace-safe source metadata for model-exposed tools."""

    return {
        tool.id: tool.definition.source.to_mapping()
        for tool in tools
        if tool.definition.source is not None
    }


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
    plan: ExecutionPlan,
    state: WorkflowExecutionState,
    registry: ToolRegistry | None,
    tracer: WorkflowTracer,
    lifecycle_hooks: WorkflowLifecycleHooks | None,
) -> ToolResult | WorkflowInterruptedResult:
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
    tool = registry.get_tool(str(node.tool_id))
    if _approval_required(tool):
        interruption = ApprovalInterruption(
            interruption_id=_new_approval_id(),
            run_id=str(state.run_id),
            workflow_id=str(plan.workflow.runtime_manifest.package_id),
            node_id=str(node.id),
            tool_id=str(node.tool_id),
            arguments=arguments,
            policy=_tool_policy_payload(tool),
            reason=f"tool {node.tool_id!r} requires approval",
        )
        tracer.emit(
            "approval_requested",
            node_id=str(node.id),
            payload={
                "interruption_id": interruption.interruption_id,
                "tool_id": node.tool_id,
                "arguments": arguments,
                "policy": interruption.policy,
                "reason": interruption.reason,
            },
            sensitive_fields=("arguments",),
        )
        tracer.emit(
            "approval_paused",
            node_id=str(node.id),
            payload={
                "interruption_id": interruption.interruption_id,
                "tool_id": node.tool_id,
                "state": interruption.state.value,
            },
        )
        return WorkflowInterruptedResult(
            final_result=None,
            state=state,
            interruption=interruption,
        )
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
    behavior: Any,
    state: WorkflowExecutionState,
    *,
    context: Mapping[str, Any] | None = None,
) -> tuple[tuple[str, OpenAIMessage], ...]:
    return _render_message_parts_with_skill_sources(
        behavior,
        state,
        context=context,
    ).message_parts


def _render_message_parts_with_skill_sources(
    behavior: Any,
    state: WorkflowExecutionState,
    *,
    context: Mapping[str, Any] | None = None,
    workflow: LoadedAgentWorkflow | None = None,
    node_id: str | None = None,
) -> _RenderedMessageParts:
    prompt_data = behavior.prompt
    render_context = dict(context) if context is not None else _format_context(state)
    messages: list[tuple[str, OpenAIMessage]] = []
    for role in ("system", "developer"):
        value = prompt_data.get(role)
        if value is not None:
            messages.append(
                (
                    role,
                    OpenAIMessage(
                        role=role,
                        content=_format_text(str(value), render_context),
                    ),
                )
            )
    skill_messages, skill_source_preparation = _render_skill_instruction_messages(
        behavior,
        render_context,
        workflow=workflow,
        node_id=node_id,
    )
    messages.extend(skill_messages)
    user_template = (
        prompt_data.get("user_template") or prompt_data.get("user") or "{prompt}"
    )
    messages.append(
        (
            "user_prompt",
            OpenAIMessage(
                role="user",
                content=_format_text(str(user_template), render_context),
            ),
        )
    )
    return _RenderedMessageParts(
        message_parts=tuple(messages),
        skill_source_preparation=skill_source_preparation,
    )


def _render_skill_instruction_messages(
    behavior: Any,
    render_context: Mapping[str, Any],
    *,
    workflow: LoadedAgentWorkflow | None,
    node_id: str | None,
) -> tuple[tuple[tuple[str, OpenAIMessage], ...], _SkillSourcePreparation]:
    policy_metadata = (
        workflow.runtime_manifest.skill_source_resolution_policy
        if workflow is not None
        else None
    )
    policy = (
        policy_metadata.to_policy()
        if policy_metadata is not None and policy_metadata.enabled
        else None
    )
    messages: list[tuple[str, OpenAIMessage]] = []
    loaded: list[Mapping[str, Any]] = []
    omitted: list[Mapping[str, Any]] = []
    rejected: list[Mapping[str, Any]] = []
    resolved_sources = []
    for skill in behavior.skills:
        instructions = skill.raw.get("instructions")
        if instructions is not None:
            messages.append(
                _skill_instruction_message(
                    str(skill.raw.get("prompt_role") or "developer"),
                    str(instructions),
                    render_context,
                )
            )
            omitted.append({"skill_id": skill.id, "reason": "inline_instructions"})
            continue
        if policy is None:
            omitted.append({"skill_id": skill.id, "reason": "source_policy_disabled"})
            continue
        if workflow is None or workflow.skill_bundle_root is None:
            rejected.append(
                RejectedSkillSource(
                    skill_id=str(skill.id),
                    reason="missing package skill-bundle root",
                ).redacted_metadata()
            )
            continue
        try:
            resolved = resolve_package_bundled_skill_source(
                skill_id=str(skill.id),
                raw_skill=skill.raw,
                package_id=workflow.runtime_manifest.package_id,
                skill_bundle_root=workflow.skill_bundle_root,
                policy=policy,
            )
        except SkillSourceResolutionError as exc:
            rejected.append(
                RejectedSkillSource(
                    skill_id=str(skill.id),
                    reason=str(exc),
                    bundled_path=(
                        str(skill.raw["bundled_path"])
                        if skill.raw.get("bundled_path") is not None
                        else None
                    ),
                ).redacted_metadata()
            )
            continue
        resolved_sources.append(resolved)
        loaded.append(resolved.redacted_metadata())
        messages.append(
            _skill_instruction_message(
                policy.prompt_role,
                resolved.body,
                render_context,
            )
        )
    if policy is not None and node_id is not None:
        try:
            enforce_node_skill_source_budget(
                tuple(resolved_sources),
                policy=policy,
                node_id=node_id,
            )
        except SkillSourceResolutionError as exc:
            rejected.append({"skill_id": "*", "reason": str(exc)})
    return (
        tuple(messages),
        _SkillSourcePreparation(
            loaded=tuple(loaded),
            omitted=tuple(omitted),
            rejected=tuple(rejected),
        ),
    )


def _skill_instruction_message(
    role: str,
    instructions: str,
    render_context: Mapping[str, Any],
) -> tuple[str, OpenAIMessage]:
    return (
        "skill_instructions",
        OpenAIMessage(
            role=role,
            content=_format_text(instructions, render_context),
        ),
    )


def _prepare_model_input_render_context(
    node: PreparedNode,
    state: WorkflowExecutionState,
) -> tuple[dict[str, Any], PreparedInputMetadata]:
    context = _format_context(state)
    mutation_context = _mutation_render_context(node, state)
    context.update(mutation_context)
    return context, _mutation_preparation_metadata(node, mutation_context)


def _mutation_render_context(
    node: PreparedNode,
    state: WorkflowExecutionState,
) -> dict[str, Any]:
    spec = node.mutation_spec
    if spec is None or spec.kind != "context_pruning":
        return {}
    return ContextPruningMutation(spec).render_context(
        prompt=state.prompt,
        session_messages=state.session_messages,
        resolve_source=lambda binding: _resolve_mutation_render_source(binding, state),
    )


def _mutation_preparation_metadata(
    node: PreparedNode,
    mutation_context: Mapping[str, Any],
) -> PreparedInputMetadata:
    spec = node.mutation_spec
    if spec is None or spec.kind != "context_pruning" or not mutation_context:
        return PreparedInputMetadata()
    return PreparedInputMetadata(
        mutation_applied=True,
        mutation_id=spec.mutation_id,
        mutation_output_slots=tuple(mutation_context.keys()),
    )


def _merge_prepared_input_metadata(
    base: PreparedInputMetadata,
    overlay: PreparedInputMetadata,
) -> PreparedInputMetadata:
    return PreparedInputMetadata(
        hierarchy_applied=base.hierarchy_applied,
        session_messages_included=base.session_messages_included,
        session_messages_pruned=base.session_messages_pruned,
        context_compaction_applied=base.context_compaction_applied,
        file_context_applied=base.file_context_applied,
        file_context_sources=base.file_context_sources,
        file_context_files_included=base.file_context_files_included,
        file_context_bytes=base.file_context_bytes,
        file_context_estimated_tokens=base.file_context_estimated_tokens,
        mutation_applied=overlay.mutation_applied,
        mutation_id=overlay.mutation_id,
        mutation_output_slots=overlay.mutation_output_slots,
        skill_sources_loaded=base.skill_sources_loaded,
        skill_sources_omitted=base.skill_sources_omitted,
        skill_sources_rejected=base.skill_sources_rejected,
        turn_count=base.turn_count,
        segment_count=base.segment_count,
        turns=base.turns,
        segments=base.segments,
        context_threshold=base.context_threshold,
        compression_profile=base.compression_profile,
        lane_budgets=base.lane_budgets,
        selection_policy=base.selection_policy,
        lifecycle_stages=base.lifecycle_stages,
        metrics=base.metrics,
    )


def _merge_skill_source_preparation(
    base: PreparedInputMetadata,
    skill_sources: _SkillSourcePreparation,
) -> PreparedInputMetadata:
    return PreparedInputMetadata(
        hierarchy_applied=base.hierarchy_applied,
        session_messages_included=base.session_messages_included,
        session_messages_pruned=base.session_messages_pruned,
        context_compaction_applied=base.context_compaction_applied,
        file_context_applied=base.file_context_applied,
        file_context_sources=base.file_context_sources,
        file_context_files_included=base.file_context_files_included,
        file_context_bytes=base.file_context_bytes,
        file_context_estimated_tokens=base.file_context_estimated_tokens,
        mutation_applied=base.mutation_applied,
        mutation_id=base.mutation_id,
        mutation_output_slots=base.mutation_output_slots,
        skill_sources_loaded=skill_sources.loaded,
        skill_sources_omitted=skill_sources.omitted,
        skill_sources_rejected=skill_sources.rejected,
        turn_count=base.turn_count,
        segment_count=base.segment_count,
        turns=base.turns,
        segments=base.segments,
        context_threshold=base.context_threshold,
        compression_profile=base.compression_profile,
        lane_budgets=base.lane_budgets,
        selection_policy=base.selection_policy,
        lifecycle_stages=base.lifecycle_stages,
        metrics=base.metrics,
    )


def _resolve_mutation_render_source(
    binding: str | None,
    state: WorkflowExecutionState,
) -> Any:
    if binding is None:
        return None
    return _resolve_value(binding, state)


def _apply_prepare_model_input_stage(
    base_parts: Sequence[tuple[str, OpenAIMessage]],
    plan: ExecutionPlan,
    state: WorkflowExecutionState,
    *,
    model: str,
    adapter: ModelAdapter,
) -> tuple[tuple[tuple[str, OpenAIMessage], ...], PreparedInputMetadata]:
    """Apply optional prepare-stage hierarchy and session shaping."""

    policy = _prepare_model_input_policy(plan.execution_policy)
    if not policy:
        return tuple(base_parts), PreparedInputMetadata()

    result_parts: list[tuple[str, OpenAIMessage]] = []
    hierarchy_applied = False

    for index, content in enumerate(_hierarchy_messages(policy, "system"), start=1):
        result_parts.append(
            (
                f"hierarchy_system_{index}",
                OpenAIMessage(role="system", content=content),
            )
        )
        hierarchy_applied = True

    base_without_user = [part for part in base_parts if part[0] != "user_prompt"]
    user_part = next((part for part in base_parts if part[0] == "user_prompt"), None)
    result_parts.extend(base_without_user)

    for index, content in enumerate(_hierarchy_messages(policy, "developer"), start=1):
        result_parts.append(
            (
                f"hierarchy_developer_{index}",
                OpenAIMessage(role="developer", content=content),
            )
        )
        hierarchy_applied = True

    file_context_messages, file_context_metadata = _file_context_messages(
        plan,
        policy,
        model=model,
    )
    result_parts.extend(file_context_messages)

    kept_session, pruned_session = _pruned_session_messages(
        state.session_messages, policy
    )
    turn_metadata, segment_metadata = _session_turn_diagnostics(state.session_messages)
    context_threshold = _context_threshold_metadata(policy, adapter, model)
    compression_profile = _compression_profile(policy)
    lane_budgets = _lane_budgets(policy)
    selection_policy = _selection_policy(policy)
    lifecycle_stages = _lifecycle_stage_status(policy)
    metrics = _context_metrics(policy)
    context_compaction_applied = False
    if pruned_session:
        summary_message = _compacted_session_message(pruned_session, policy)
        if summary_message is not None:
            result_parts.append(("session_summary", summary_message))
            context_compaction_applied = True

    for index, message in enumerate(kept_session, start=1):
        result_parts.append((f"session_message_{index}", message))

    if user_part is not None:
        result_parts.append(user_part)

    return tuple(result_parts), PreparedInputMetadata(
        hierarchy_applied=hierarchy_applied,
        session_messages_included=len(kept_session),
        session_messages_pruned=len(pruned_session),
        context_compaction_applied=context_compaction_applied,
        file_context_applied=file_context_metadata.file_context_applied,
        file_context_sources=file_context_metadata.file_context_sources,
        file_context_files_included=file_context_metadata.file_context_files_included,
        file_context_bytes=file_context_metadata.file_context_bytes,
        file_context_estimated_tokens=file_context_metadata.file_context_estimated_tokens,
        turn_count=len(turn_metadata),
        segment_count=len(segment_metadata),
        turns=turn_metadata,
        segments=segment_metadata,
        context_threshold=context_threshold,
        compression_profile=compression_profile,
        lane_budgets=lane_budgets,
        selection_policy=selection_policy,
        lifecycle_stages=lifecycle_stages,
        metrics=metrics,
    )


def _prepare_model_input_policy(
    execution_policy: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = execution_policy.get("prepare_model_input")
    return value if isinstance(value, Mapping) else {}


def _session_turn_diagnostics(
    session_messages: Sequence[OpenAIMessage],
) -> tuple[tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
    turns: list[list[OpenAIMessage]] = []
    current: list[OpenAIMessage] = []
    for message in session_messages:
        if message.role == "user" and current:
            turns.append(current)
            current = []
        current.append(message)
    if current:
        turns.append(current)

    turn_metadata: list[Mapping[str, Any]] = []
    segment_metadata: list[Mapping[str, Any]] = []
    for turn_index, turn in enumerate(turns, start=1):
        turn_id = f"turn_{turn_index}"
        lane = "current_turn" if turn_index == len(turns) else "recent_turns"
        turn_metadata.append(
            {
                "turn_id": turn_id,
                "lane": lane,
                "message_count": len(turn),
                "roles": tuple(message.role for message in turn),
                "selection_status": "included",
            }
        )
        for segment_index, message in enumerate(turn, start=1):
            segment_metadata.append(
                {
                    "segment_id": f"{turn_id}_segment_{segment_index}",
                    "turn_id": turn_id,
                    "lane": lane,
                    "role": message.role,
                    "selection_status": "included",
                }
            )
    return tuple(turn_metadata), tuple(segment_metadata)


def _context_threshold_metadata(
    policy: Mapping[str, Any],
    adapter: ModelAdapter,
    model: str,
) -> Mapping[str, Any]:
    auto = _context_compaction_auto_policy(policy)
    if not auto:
        return {}
    threshold_ratio = min(float(auto.get("threshold_ratio", 0.9)), 0.9)
    context_window = _adapter_context_window(adapter, model)
    result: dict[str, Any] = {
        "enabled": auto.get("enabled", False) is True,
        "threshold_ratio": threshold_ratio,
        "context_window": context_window,
        "threshold_tokens": (
            int(context_window * threshold_ratio)
            if isinstance(context_window, int)
            else None
        ),
        "reserve_tokens": auto.get("reserve_tokens"),
        "trigger": str(auto.get("trigger") or "token_threshold"),
        "scope": str(auto.get("scope") or "current_run"),
        "implementation": str(auto.get("implementation") or "metadata_only"),
        "strategy": str(auto.get("strategy") or "basic"),
        "mode": str(auto.get("mode") or "auto"),
        "status": "metadata_only",
    }
    return {key: value for key, value in result.items() if value is not None}


def _context_compaction_auto_policy(policy: Mapping[str, Any]) -> Mapping[str, Any]:
    compaction = policy.get("context_compaction")
    if not isinstance(compaction, Mapping):
        return {}
    auto = compaction.get("auto")
    return auto if isinstance(auto, Mapping) else {}


def _adapter_context_window(adapter: ModelAdapter, model: str) -> int | None:
    context_windows = getattr(adapter, "context_windows", None)
    if isinstance(context_windows, Mapping):
        value = context_windows.get(model)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    return None


def _compression_profile(policy: Mapping[str, Any]) -> str | None:
    compression = policy.get("context_compression")
    if not isinstance(compression, Mapping):
        return None
    profile = compression.get("profile")
    return str(profile) if profile is not None else None


def _lane_budgets(policy: Mapping[str, Any]) -> Mapping[str, int]:
    compression = policy.get("context_compression")
    if not isinstance(compression, Mapping):
        return {}
    lanes = compression.get("lanes")
    if not isinstance(lanes, Mapping):
        return {}
    return {
        str(key): value
        for key, value in lanes.items()
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
    }


def _selection_policy(policy: Mapping[str, Any]) -> Mapping[str, Any]:
    compression = policy.get("context_compression")
    if not isinstance(compression, Mapping):
        return {}
    selection = compression.get("selection")
    if not isinstance(selection, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key in ("strategy", "max_selected_turns", "chronological_reassembly"):
        if key in selection:
            result[key] = selection[key]
    return result


def _lifecycle_stage_status(policy: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    auto = _context_compaction_auto_policy(policy)
    stages = auto.get("lifecycle_stages")
    if not isinstance(stages, Sequence) or isinstance(stages, (str, bytes, bytearray)):
        return ()
    return tuple(
        {"stage": str(stage), "status": "complete"}
        for stage in stages
        if isinstance(stage, str)
    )


def _context_metrics(policy: Mapping[str, Any]) -> tuple[str, ...]:
    auto = _context_compaction_auto_policy(policy)
    metrics = auto.get("metrics")
    if not isinstance(metrics, Sequence) or isinstance(
        metrics, (str, bytes, bytearray)
    ):
        return ()
    return tuple(str(metric) for metric in metrics if isinstance(metric, str))


def _file_context_messages(
    plan: ExecutionPlan,
    policy: Mapping[str, Any],
    *,
    model: str,
) -> tuple[tuple[tuple[str, OpenAIMessage], ...], PreparedInputMetadata]:
    file_context = policy.get("file_context")
    if not isinstance(file_context, Mapping) or not file_context.get("enabled"):
        return (), PreparedInputMetadata()

    package_root_value = getattr(plan.workflow, "package_root", None)
    if not package_root_value:
        raise WorkflowExecutionError(
            "prepare_model_input.file_context requires a package-root-backed workflow"
        )

    package_root = Path(package_root_value).resolve()
    roots = tuple(
        str(item) for item in file_context.get("roots", ()) if isinstance(item, str)
    )
    max_depth = _optional_positive_int(file_context.get("max_depth")) or 1
    max_files = _optional_positive_int(file_context.get("max_files")) or 20
    max_bytes = _optional_positive_int(file_context.get("max_bytes")) or 8192
    max_tokens = _optional_positive_int(file_context.get("max_tokens"))
    role = str(file_context.get("prompt_role") or "developer")
    header = str(file_context.get("header") or "Project file context:")

    files = _collect_file_context_paths(
        package_root,
        roots,
        max_depth=max_depth,
        max_files=max_files,
    )
    parts: list[tuple[str, OpenAIMessage]] = []
    source_paths: list[str] = []
    bytes_used = 0
    tokens_used = 0
    for index, relative_path in enumerate(files, start=1):
        path = package_root / relative_path
        content = path.read_text(encoding="utf-8")
        candidate = f"{header}\nSource: {relative_path}\n```text\n{content}\n```"
        candidate_bytes = len(candidate.encode("utf-8"))
        candidate_tokens = estimate_messages_tokens(
            ({"role": role, "content": candidate},),
            model=model,
        ).token_count
        if parts and (
            bytes_used + candidate_bytes > max_bytes
            or (max_tokens is not None and tokens_used + candidate_tokens > max_tokens)
        ):
            break
        if not parts and (
            candidate_bytes > max_bytes
            or (max_tokens is not None and candidate_tokens > max_tokens)
        ):
            content = _truncate_file_context_content(content, max_bytes=max_bytes)
            candidate = f"{header}\nSource: {relative_path}\n```text\n{content}\n```"
            candidate_bytes = len(candidate.encode("utf-8"))
            candidate_tokens = estimate_messages_tokens(
                ({"role": role, "content": candidate},),
                model=model,
            ).token_count
        if candidate_bytes > max_bytes:
            continue
        if max_tokens is not None and candidate_tokens > max_tokens:
            continue
        part_name = f"file_context_{index}"
        parts.append((part_name, OpenAIMessage(role=role, content=candidate)))
        source_paths.append(relative_path.as_posix())
        bytes_used += candidate_bytes
        tokens_used += candidate_tokens

    return tuple(parts), PreparedInputMetadata(
        file_context_applied=bool(parts),
        file_context_sources=tuple(source_paths),
        file_context_files_included=len(parts),
        file_context_bytes=bytes_used,
        file_context_estimated_tokens=tokens_used,
    )


def _collect_file_context_paths(
    package_root: Path,
    roots: Sequence[str],
    *,
    max_depth: int,
    max_files: int,
) -> tuple[Path, ...]:
    results: list[Path] = []
    for root in sorted(roots):
        candidate = (package_root / root).resolve()
        if not _is_relative_to(candidate, package_root):
            raise WorkflowExecutionError(
                f"prepare_model_input.file_context root {root!r} escapes package root"
            )
        if candidate.is_file():
            results.append(candidate.relative_to(package_root))
        elif candidate.is_dir():
            _collect_directory_file_context_paths(
                candidate,
                package_root,
                max_depth=max_depth,
                max_files=max_files,
                results=results,
            )
        if len(results) >= max_files:
            break
    deduped = sorted(dict.fromkeys(results))
    return tuple(deduped[:max_files])


def _collect_directory_file_context_paths(
    current: Path,
    package_root: Path,
    *,
    max_depth: int,
    max_files: int,
    results: list[Path],
    depth: int = 0,
) -> None:
    if len(results) >= max_files or depth > max_depth:
        return
    for child in sorted(current.iterdir(), key=lambda item: item.name):
        if len(results) >= max_files:
            return
        if child.is_dir():
            if depth < max_depth:
                _collect_directory_file_context_paths(
                    child,
                    package_root,
                    max_depth=max_depth,
                    max_files=max_files,
                    results=results,
                    depth=depth + 1,
                )
            continue
        if child.is_file():
            results.append(child.relative_to(package_root))


def _truncate_file_context_content(value: str, *, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    truncated = encoded[:max_bytes]
    return truncated.decode("utf-8", errors="ignore")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _hierarchy_messages(policy: Mapping[str, Any], role: str) -> tuple[str, ...]:
    hierarchy = policy.get("prompt_hierarchy")
    if not isinstance(hierarchy, Mapping):
        return ()
    value = hierarchy.get(role)
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(str(item) for item in value if item is not None)
    return (str(value),)


def _pruned_session_messages(
    session_messages: Sequence[OpenAIMessage],
    policy: Mapping[str, Any],
) -> tuple[tuple[OpenAIMessage, ...], tuple[OpenAIMessage, ...]]:
    pruning = policy.get("session_pruning")
    if not isinstance(pruning, Mapping):
        return tuple(session_messages), ()
    max_messages = pruning.get("max_messages")
    try:
        limit = int(max_messages)
    except (TypeError, ValueError):
        return tuple(session_messages), ()
    if limit < 0 or len(session_messages) <= limit:
        return tuple(session_messages), ()
    if limit == 0:
        return (), tuple(session_messages)
    return tuple(session_messages[-limit:]), tuple(session_messages[:-limit])


def _compacted_session_message(
    pruned_session: Sequence[OpenAIMessage],
    policy: Mapping[str, Any],
) -> OpenAIMessage | None:
    compaction = policy.get("context_compaction")
    if not isinstance(compaction, Mapping):
        return None
    strategy = str(compaction.get("strategy") or "summary_message")
    if strategy != "summary_message":
        return None
    role = str(compaction.get("summary_role") or "developer")
    max_chars = _optional_positive_int(compaction.get("max_chars_per_message")) or 120
    prefix = str(
        compaction.get("summary_prefix") or "Compacted earlier session context:"
    )
    lines = [prefix]
    for message in pruned_session:
        lines.append(f"- {message.role}: {_truncate_text(message.content, max_chars)}")
    return OpenAIMessage(role=role, content="\n".join(lines))


def _optional_positive_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _truncate_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    if max_chars <= 1:
        return value[:max_chars]
    return value[: max_chars - 1] + "…"


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


def _optional_model_name(node: PreparedNode) -> str | None:
    return node.model


def _normalize_model_adapters(
    value: ModelAdapter | Sequence[ModelAdapter] | None,
) -> tuple[ModelAdapter, ...]:
    if value is None:
        return ()
    if isinstance(value, (OpenAIClientAdapter, AsyncOpenAIClientAdapter)):
        return (value,)
    return tuple(value)


def _normalize_model_adapter_coverage(value: str | None) -> str:
    if value is None:
        return "augmented"
    if value in {"augmented", "strict"}:
        return value
    raise WorkflowExecutionError(
        f"model_adapter_coverage must be 'augmented' or 'strict'; got {value!r}"
    )


def _execution_policy_model_map(
    execution_policy: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = execution_policy.get("model_map")
    return value if isinstance(value, Mapping) else {}


def _select_model_and_adapter(
    node: PreparedNode,
    adapters: Sequence[ModelAdapter],
    model_map: Mapping[str, Any],
    *,
    model_adapter_coverage: str = "augmented",
) -> tuple[str, ModelAdapter]:
    requested_model = _optional_model_name(node)
    normalized_adapters = tuple(adapters)
    required_features = _required_model_features(node)
    coverage = _normalize_model_adapter_coverage(model_adapter_coverage)

    if requested_model is None:
        return _select_default_model_and_adapter_for_missing_model(
            node,
            normalized_adapters,
            required_features=required_features,
            coverage=coverage,
        )

    if not normalized_adapters and coverage == "augmented" and not required_features:
        return requested_model, AsyncOpenAIClientAdapter(models=(requested_model,))

    matches, preferred_matches = _matching_model_adapters(
        normalized_adapters,
        requested_model=requested_model,
        required_features=required_features,
        model_map=model_map,
    )

    if preferred_matches:
        return preferred_matches[0]
    if matches:
        return matches[0]

    if coverage == "strict":
        raise _strict_model_adapter_coverage_error(
            node,
            requested_model=requested_model,
            required_features=required_features,
        )

    if not required_features:
        wildcard_adapter = _first_wildcard_model_adapter(normalized_adapters)
        if wildcard_adapter is not None:
            return requested_model, wildcard_adapter
        return requested_model, AsyncOpenAIClientAdapter(models=(requested_model,))

    fallback_model = _fallback_model_name(requested_model, required_features, model_map)
    if _default_openai_adapter_allowed(fallback_model, model_map):
        return fallback_model, AsyncOpenAIClientAdapter(models=(fallback_model,))

    if fallback_model != requested_model:
        return _raise_missing_capability_adapter_error(
            node,
            model_label="fallback model",
            model_name=fallback_model,
            required_features=required_features,
        )
    return _raise_missing_capability_adapter_error(
        node,
        model_label="requested model",
        model_name=requested_model,
        required_features=required_features,
    )


def _select_default_model_and_adapter_for_missing_model(
    node: PreparedNode,
    adapters: Sequence[ModelAdapter],
    *,
    required_features: frozenset[str],
    coverage: str,
) -> tuple[str, ModelAdapter]:
    if required_features:
        raise WorkflowExecutionError(
            f"llm_step node {node.id!r} is missing model and requires "
            f"capabilities {sorted(required_features)!r}"
        )
    for adapter in adapters:
        configured_models = tuple(getattr(adapter, "models", ()))
        if configured_models:
            return configured_models[0], adapter
        if isinstance(adapter, OpenAIClientAdapter):
            try:
                return adapter.default_model(), adapter
            except ModelExecutionError as exc:
                raise WorkflowExecutionError(str(exc)) from exc
    if coverage == "strict":
        raise WorkflowExecutionError(
            f"llm_step node {node.id!r} is missing model and "
            "model_adapter_coverage 'strict' requires a provided model adapter"
        )
    adapter = OpenAIClientAdapter()
    try:
        model = adapter.default_model()
    except ModelExecutionError as exc:
        raise WorkflowExecutionError(str(exc)) from exc
    return model, AsyncOpenAIClientAdapter(models=(model,))


def _first_wildcard_model_adapter(
    adapters: Sequence[ModelAdapter],
) -> ModelAdapter | None:
    return next(
        (adapter for adapter in adapters if not getattr(adapter, "models", ())), None
    )


def _strict_model_adapter_coverage_error(
    node: PreparedNode,
    *,
    requested_model: str,
    required_features: frozenset[str],
) -> WorkflowExecutionError:
    feature_text = (
        f" and capabilities {sorted(required_features)!r}" if required_features else ""
    )
    return WorkflowExecutionError(
        "model_adapter_coverage 'strict' requires a provided model adapter that "
        f"advertises support for llm_step node {node.id!r} model "
        f"{requested_model!r}{feature_text}"
    )


def _raise_missing_capability_adapter_error(
    node: PreparedNode,
    *,
    model_label: str,
    model_name: str,
    required_features: frozenset[str],
) -> tuple[str, ModelAdapter]:
    raise WorkflowExecutionError(
        f"llm_step node {node.id!r} requires capabilities {sorted(required_features)!r} "
        f"but no provided model adapter advertises support for {model_label} "
        f"{model_name!r}"
    )


def _default_openai_adapter_allowed(
    model_name: str,
    model_map: Mapping[str, Any],
) -> bool:
    if model_name not in model_map:
        return True
    return bool(_registry_model_features_for_name(model_name))


def _matching_model_adapters(
    adapters: Sequence[ModelAdapter],
    *,
    requested_model: str,
    required_features: frozenset[str],
    model_map: Mapping[str, Any],
) -> tuple[list[tuple[str, ModelAdapter]], list[tuple[str, ModelAdapter]]]:
    matches: list[tuple[str, ModelAdapter]] = []
    preferred_matches: list[tuple[str, ModelAdapter]] = []
    for adapter in adapters:
        for model_name in getattr(adapter, "models", ()):
            features = _model_features_for_name(model_name, model_map)
            if not required_features and model_name != requested_model:
                continue
            if required_features and not required_features.issubset(features):
                continue
            candidate = (model_name, adapter)
            matches.append(candidate)
            if model_name == requested_model:
                preferred_matches.append(candidate)
    return matches, preferred_matches


def _required_model_features(node: PreparedNode) -> frozenset[str]:
    requirements = _mapping_or_none(node.model_requirements) or {}
    features: set[str] = set()
    required_capabilities = requirements.get("required_capabilities")
    if isinstance(required_capabilities, Sequence) and not isinstance(
        required_capabilities, (str, bytes, bytearray)
    ):
        features.update(str(item) for item in required_capabilities)
    for field_name in ("features", "required_features"):
        raw_value = node.raw.get(field_name)
        if isinstance(raw_value, Sequence) and not isinstance(
            raw_value, (str, bytes, bytearray)
        ):
            features.update(str(item) for item in raw_value)
    return frozenset(features)


def _model_features_for_name(
    model_name: str,
    model_map: Mapping[str, Any],
) -> frozenset[str]:
    registry_features = _registry_model_features_for_name(model_name)
    value = model_map.get(model_name)
    if isinstance(value, Mapping):
        if isinstance(value.get("features"), Sequence) and not isinstance(
            value.get("features"), (str, bytes, bytearray)
        ):
            return registry_features | frozenset(
                str(item) for item in value.get("features", ())
            )
        if isinstance(value.get("required_capabilities"), Sequence) and not isinstance(
            value.get("required_capabilities"), (str, bytes, bytearray)
        ):
            return registry_features | frozenset(
                str(item) for item in value.get("required_capabilities", ())
            )
        return registry_features | frozenset(
            str(key)
            for key, enabled in value.items()
            if isinstance(enabled, bool) and enabled
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return registry_features | frozenset(str(item) for item in value)
    return registry_features


def _registry_model_features_for_name(model_name: str) -> frozenset[str]:
    capabilities = _get_openai_model_capabilities(model_name)
    if capabilities is None:
        return frozenset()
    features: set[str] = set()
    if getattr(capabilities, "supports_structured", False):
        features.update({"structured_output", "json_mode"})
    if getattr(capabilities, "supports_functions", False):
        features.add("tool_calling")
    if getattr(capabilities, "supports_vision", False):
        features.add("multimodal_input")
    if getattr(capabilities, "supports_web_search", False):
        features.add("citation_generation")
    if (
        getattr(capabilities, "context_window", 0)
        and capabilities.context_window >= 128000
    ):
        features.add("long_context")
    input_modalities = set(getattr(capabilities, "input_modalities", ()) or ())
    if {"image", "audio"} & input_modalities:
        features.add("multimodal_input")
    return frozenset(features)


def _get_openai_model_capabilities(model_name: str) -> Any | None:
    try:
        registry = ModelRegistry.get_default()
        return registry.get_capabilities(model_name)
    except (ModelNotSupportedError, AttributeError, ImportError, OSError, ValueError):
        return None


def _fallback_model_name(
    requested_model: str,
    required_features: frozenset[str],
    model_map: Mapping[str, Any],
) -> str:
    if not required_features:
        return requested_model
    requested_features = _model_features_for_name(requested_model, model_map)
    if not requested_features or required_features.issubset(requested_features):
        return requested_model
    for model_name in sorted(str(name) for name in model_map):
        if required_features.issubset(_model_features_for_name(model_name, model_map)):
            return model_name
    return requested_model


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
