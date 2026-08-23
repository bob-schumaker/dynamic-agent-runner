"""Workflow executor for validated dynamic-agent runtime artifacts."""

from __future__ import annotations

import asyncio
import json
import re
from copy import deepcopy
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
from dynamic_agent_runner.context_selection import (
    ContextSelection,
    ContextSelectionCandidate,
    ContextSelector,
)
from dynamic_agent_runner.errors import (
    GuardrailExecutionError,
    ModelExecutionError,
    ToolRegistryError,
    WorkflowExecutionError,
)
from dynamic_agent_runner.guardrails import (
    GuardrailDecision,
    GuardrailResult,
    InMemoryGuardrailRegistry,
)
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
    GuardrailDeclaration,
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
    is_context_overflow_error,
)
from dynamic_agent_runner.prompt_cache import (
    build_prompt_cache_observation,
    prompt_cache_policy_from_value,
)
from dynamic_agent_runner.registry import (
    PreparedToolInvocation,
    RegisteredTool,
    ToolRegistry,
    ToolResult,
    ToolSelector,
    tool_descriptor_budget_policy_from_values,
)
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
ContextCompactor = Callable[
    [tuple[OpenAIMessage, ...], Mapping[str, Any]],
    tuple[OpenAIMessage, ...],
]
ContextSummarizer = Callable[
    [tuple[OpenAIMessage, ...], Mapping[str, Any]],
    str | OpenAIMessage,
]


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
    compaction: Mapping[str, Any] = field(default_factory=dict)
    pre_turn_compaction: Mapping[str, Any] = field(default_factory=dict)
    context_reset: Mapping[str, Any] = field(default_factory=dict)
    file_context_applied: bool = False
    file_context_sources: tuple[str, ...] = ()
    file_context_files_included: int = 0
    file_context_bytes: int = 0
    file_context_estimated_tokens: int = 0
    retrieved_context: tuple[Mapping[str, Any], ...] = ()
    retrieved_context_omitted: tuple[Mapping[str, Any], ...] = ()
    mutation_applied: bool = False
    mutation_id: str | None = None
    mutation_output_slots: tuple[str, ...] = ()
    mutation_attachment: Mapping[str, Any] = field(default_factory=dict)
    mutation_context: Mapping[str, Any] = field(default_factory=dict)
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
    context_lanes: tuple[Mapping[str, Any], ...] = ()
    selection_policy: Mapping[str, Any] = field(default_factory=dict)
    selected_turns: tuple[Mapping[str, Any], ...] = ()
    omitted_turns: tuple[Mapping[str, Any], ...] = ()
    rejected_turns: tuple[Mapping[str, Any], ...] = ()
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
class _SemanticTurnCandidate:
    turn_index: int
    candidate: ContextSelectionCandidate
    messages: tuple[OpenAIMessage, ...]


@dataclass(frozen=True)
class _RankedSemanticTurn:
    exact_match_count: int
    score: float
    turn_index: int
    turn_id: str
    reason: str
    messages: tuple[OpenAIMessage, ...]


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
    tool_choice_policy: Any = None
    response_format: Mapping[str, Any] | None = None
    context_compactor: ContextCompactor | None = None

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
    context_compactor: ContextCompactor | None = None,
    context_summarizer: ContextSummarizer | None = None,
    context_selector: ContextSelector | None = None,
    session_messages: Sequence[OpenAIMessage] = (),
    initial_node_outputs: Mapping[str, Any] | None = None,
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
        context_selector=context_selector,
    )
    plan = prepare_execution_plan(context.workflow)
    nodes = plan.nodes_by_id
    if not plan.entrypoint_id or plan.entrypoint_id not in nodes:
        raise WorkflowExecutionError("workflow entrypoint does not reference a node")
    adapters = _normalize_model_adapters(context.model_adapter)
    state = WorkflowExecutionState(
        prompt=prompt,
        run_id=run_id or _new_run_id(),
        session_messages=tuple(session_messages),
        node_outputs=dict(initial_node_outputs or {}),
    )
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
                    context.guardrail_registry,
                    adapters,
                    tracer,
                    context.prompt_cache,
                    hooks,
                    context.model_adapter_coverage,
                    context_compactor,
                    context_summarizer,
                    context.context_selector,
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
    context_compactor: ContextCompactor | None = None,
    context_summarizer: ContextSummarizer | None = None,
    context_selector: ContextSelector | None = None,
    session_messages: Sequence[OpenAIMessage] = (),
    initial_node_outputs: Mapping[str, Any] | None = None,
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
            context_compactor=context_compactor,
            context_summarizer=context_summarizer,
            context_selector=context_selector,
            session_messages=session_messages,
            initial_node_outputs=initial_node_outputs,
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
    context_compactor: ContextCompactor | None = None,
    context_summarizer: ContextSummarizer | None = None,
    context_selector: ContextSelector | None = None,
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
        node, plan, state
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
        context_compactor=context_compactor,
        context_summarizer=context_summarizer,
        context_selector=context_selector,
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
                "compaction": preparation.compaction,
                "pre_turn_compaction": preparation.pre_turn_compaction,
                "context_reset": preparation.context_reset,
                "file_context_applied": preparation.file_context_applied,
                "file_context_sources": preparation.file_context_sources,
                "file_context_files_included": preparation.file_context_files_included,
                "file_context_bytes": preparation.file_context_bytes,
                "file_context_estimated_tokens": preparation.file_context_estimated_tokens,
                "retrieved_context": preparation.retrieved_context,
                "retrieved_context_omitted": preparation.retrieved_context_omitted,
                "mutation_applied": preparation.mutation_applied,
                "mutation_id": preparation.mutation_id,
                "mutation_output_slots": preparation.mutation_output_slots,
                "mutation_attachment": preparation.mutation_attachment,
                "mutation_context": preparation.mutation_context,
                "skill_sources_loaded": preparation.skill_sources_loaded,
                "skill_sources_omitted": preparation.skill_sources_omitted,
                "skill_sources_rejected": preparation.skill_sources_rejected,
                "turn_count": preparation.turn_count,
                "segment_count": preparation.segment_count,
                "context_threshold": preparation.context_threshold,
                "compression_profile": preparation.compression_profile,
                "lane_budgets": preparation.lane_budgets,
                "context_lanes": preparation.context_lanes,
                "selection_policy": preparation.selection_policy,
                "selected_turns": preparation.selected_turns,
                "omitted_turns": preparation.omitted_turns,
                "rejected_turns": preparation.rejected_turns,
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
        tool_choice_policy=node.tool_choice_policy,
        response_format=node.response_format,
        context_compactor=context_compactor,
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
    context_selector: ContextSelector | None,
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
                context_selector,
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
        context_selector=context_selector,
    )


async def _execute_node_async(
    node: PreparedNode,
    plan: ExecutionPlan,
    state: WorkflowExecutionState,
    registry: ToolRegistry | None,
    guardrail_registry: InMemoryGuardrailRegistry | None,
    model_adapters: Sequence[ModelAdapter],
    tracer: WorkflowTracer,
    prompt_cache: bool | None,
    lifecycle_hooks: WorkflowLifecycleHooks | None,
    model_adapter_coverage: str,
    context_compactor: ContextCompactor | None,
    context_summarizer: ContextSummarizer | None,
    context_selector: ContextSelector | None,
) -> Any:
    if node.kind == "llm_step":
        return await _execute_llm_step_async(
            node,
            plan,
            state,
            registry,
            guardrail_registry,
            model_adapters,
            tracer,
            prompt_cache,
            lifecycle_hooks,
            model_adapter_coverage,
            context_compactor,
            context_summarizer,
            context_selector,
        )
    if node.kind == "tool_use_step":
        return await _execute_tool_step_async(
            node, plan, state, registry, guardrail_registry, tracer, lifecycle_hooks
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


def _tool_input_guardrail_runner(
    plan: ExecutionPlan,
    guardrail_registry: InMemoryGuardrailRegistry | None,
    tracer: WorkflowTracer,
    node: PreparedNode,
    tool_call_id: str | None = None,
) -> Callable[[PreparedToolInvocation], None] | None:
    declarations = _tool_input_guardrail_declarations(plan)
    if not declarations:
        return None

    def run(prepared: PreparedToolInvocation) -> None:
        for declaration in declarations:
            _run_tool_input_guardrail(
                declaration,
                prepared,
                guardrail_registry,
                tracer,
                node,
                tool_call_id,
            )

    return run


def _tool_input_guardrail_declarations(
    plan: ExecutionPlan,
) -> tuple[GuardrailDeclaration, ...]:
    return tuple(
        declaration
        for declaration in plan.workflow.runtime_manifest.guardrails
        if declaration.phase == "tool_input"
    )


def _run_tool_input_guardrail(
    declaration: GuardrailDeclaration,
    prepared: PreparedToolInvocation,
    guardrail_registry: InMemoryGuardrailRegistry | None,
    tracer: WorkflowTracer,
    node: PreparedNode,
    tool_call_id: str | None,
) -> None:
    guardrail_id = str(declaration.id)
    payload = _tool_input_guardrail_payload(guardrail_id, prepared, node, tool_call_id)
    tracer.emit("guardrail_started", node_id=str(node.id), payload=payload)
    if guardrail_registry is None or not guardrail_registry.has_guardrail(guardrail_id):
        _raise_tool_input_guardrail_error(
            tracer, node, payload, "missing_adapter", guardrail_id
        )
    result = _run_tool_input_guardrail_handler(
        guardrail_registry, guardrail_id, prepared, node, tool_call_id, tracer, payload
    )
    _record_tool_input_guardrail_result(result, guardrail_id, tracer, node, payload)


def _tool_input_guardrail_payload(
    guardrail_id: str,
    prepared: PreparedToolInvocation,
    node: PreparedNode,
    tool_call_id: str | None,
) -> dict[str, Any]:
    payload = {
        "guardrail_id": guardrail_id,
        "phase": "tool_input",
        "tool_id": prepared.tool.id,
        "node_id": str(node.id),
    }
    if tool_call_id is not None:
        payload["tool_call_id"] = tool_call_id
    return payload


def _run_tool_input_guardrail_handler(
    guardrail_registry: InMemoryGuardrailRegistry,
    guardrail_id: str,
    prepared: PreparedToolInvocation,
    node: PreparedNode,
    tool_call_id: str | None,
    tracer: WorkflowTracer,
    payload: Mapping[str, Any],
) -> GuardrailResult:
    subject: dict[str, Any] = {
        "phase": "tool_input",
        "tool_id": prepared.tool.id,
        "node_id": str(node.id),
        "arguments": deepcopy(dict(prepared.arguments)),
    }
    if tool_call_id is not None:
        subject["tool_call_id"] = tool_call_id
    try:
        result = guardrail_registry.run(guardrail_id, subject)
    except Exception:  # noqa: BLE001 - adapters are caller-owned.
        _raise_tool_input_guardrail_error(
            tracer, node, payload, "handler_error", guardrail_id
        )
    if not isinstance(result, GuardrailResult):
        _raise_tool_input_guardrail_error(
            tracer, node, payload, "malformed_result", guardrail_id
        )
    return result


def _record_tool_input_guardrail_result(
    result: GuardrailResult,
    guardrail_id: str,
    tracer: WorkflowTracer,
    node: PreparedNode,
    payload: Mapping[str, Any],
) -> None:
    if result.guardrail_id != guardrail_id:
        _raise_tool_input_guardrail_error(
            tracer, node, payload, "result_identity_mismatch", guardrail_id
        )
    if result.phase != "tool_input":
        _raise_tool_input_guardrail_error(
            tracer, node, payload, "result_phase_mismatch", guardrail_id
        )
    if result.decision is GuardrailDecision.PASS:
        tracer.emit("guardrail_passed", node_id=str(node.id), payload=payload)
        return
    if result.decision is GuardrailDecision.ABORT:
        tracer.emit(
            "guardrail_aborted",
            node_id=str(node.id),
            payload={**payload, "reason_code": result.reason_code},
        )
        error = f"tool-input guardrail {guardrail_id!r} aborted tool invocation"
        if result.reason_code:
            error = f"{error}: {result.reason_code}"
        tracer.emit("workflow_error", node_id=str(node.id), payload={"error": error})
        raise GuardrailExecutionError(error)
    _raise_tool_input_guardrail_error(
        tracer, node, payload, "unsupported_decision", guardrail_id
    )


def _raise_tool_input_guardrail_error(
    tracer: WorkflowTracer,
    node: PreparedNode,
    payload: Mapping[str, Any],
    reason: str,
    guardrail_id: str,
) -> None:
    tracer.emit(
        "guardrail_errored",
        node_id=str(node.id),
        payload={**payload, "reason": reason},
    )
    error = f"tool-input guardrail {guardrail_id!r} failed: {reason}"
    tracer.emit("workflow_error", node_id=str(node.id), payload={"error": error})
    raise GuardrailExecutionError(error)


async def _execute_llm_step_async(
    node: PreparedNode,
    plan: ExecutionPlan,
    state: WorkflowExecutionState,
    registry: ToolRegistry | None,
    guardrail_registry: InMemoryGuardrailRegistry | None,
    model_adapters: Sequence[ModelAdapter],
    tracer: WorkflowTracer,
    prompt_cache: bool | None,
    lifecycle_hooks: WorkflowLifecycleHooks | None,
    model_adapter_coverage: str,
    context_compactor: ContextCompactor | None,
    context_summarizer: ContextSummarizer | None,
    context_selector: ContextSelector | None,
) -> ModelResponse:
    prepared_input = prepare_model_input(
        node,
        plan,
        state,
        model_adapters=model_adapters,
        tracer=tracer,
        prompt_cache=prompt_cache,
        model_adapter_coverage=model_adapter_coverage,
        context_compactor=context_compactor,
        context_summarizer=context_summarizer,
        context_selector=context_selector,
    )
    tools, exposed_tools, tool_descriptor_budget_payload = _llm_step_tools(
        node,
        plan,
        prepared_input,
        registry,
    )
    request = build_openai_request(
        model=prepared_input.model,
        messages=prepared_input.messages,
        tools=tools,
        tool_choice=_tool_choice_for_phase(
            plan,
            prepared_input,
            phase="initial",
        ),
        response_format=prepared_input.response_format,
        **prepared_input.model_parameters,
    )
    model_request_payload = {
        "model": prepared_input.model,
        "message_count": len(prepared_input.messages),
        "tool_count": len(tools),
        "tool_sources": _tool_sources_payload(exposed_tools),
        "request": request.to_kwargs(),
    }
    if tool_descriptor_budget_payload is not None:
        model_request_payload["tool_descriptor_budget"] = tool_descriptor_budget_payload
    state.node_inputs[str(node.id)] = request.to_kwargs()
    tracer.emit(
        "model_request",
        node_id=str(node.id),
        payload=model_request_payload,
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
        retry_response = await _retry_model_after_context_overflow_async(
            exc,
            node,
            plan,
            state,
            prepared_input,
            tools,
            tracer,
        )
        if retry_response is not None:
            response = retry_response
            attempts = 2
        else:
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
    if "response" not in locals():
        raise WorkflowExecutionError(f"llm_step node {node.id!r} did not return output")
    if attempts == 2:
        _record_retry(
            state, node, "model", attempts=attempts, outcome="success", tracer=tracer
        )
    else:
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
    if _iterative_loop_enabled(plan):
        loop_output = await _execute_model_tool_loop_async(
            node,
            plan,
            state,
            registry,
            guardrail_registry,
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


def _llm_step_tools(
    node: PreparedNode,
    plan: ExecutionPlan,
    prepared_input: PreparedModelInput,
    registry: ToolRegistry | None,
) -> tuple[list[dict[str, Any]], tuple[RegisteredTool, ...], dict[str, Any] | None]:
    if not node.available_tools:
        return [], (), None
    if registry is None:
        raise WorkflowExecutionError(
            f"llm_step node {node.id!r} exposes tools but no registry was provided"
        )
    exposed_tools = registry.list_tools_for_node(node.source_node)
    budget_policy = tool_descriptor_budget_policy_from_values(
        plan.execution_policy.get("tool_descriptor_budget"),
        node.source_node.raw.get("tool_descriptor_budget"),
    )
    if not budget_policy.enabled:
        return (
            registry.to_openai_tools(tool.id for tool in exposed_tools),
            exposed_tools,
            None,
        )
    try:
        selection = ToolSelector().select(
            messages=prepared_input.messages,
            tools=exposed_tools,
            policy=budget_policy,
            model=prepared_input.model,
        )
    except ToolRegistryError as exc:
        raise WorkflowExecutionError(str(exc)) from exc
    return selection.tools, exposed_tools, selection.diagnostics.to_trace_payload()


async def _retry_model_after_context_overflow_async(
    exc: ModelExecutionError,
    node: PreparedNode,
    plan: ExecutionPlan,
    state: WorkflowExecutionState,
    prepared_input: PreparedModelInput,
    tools: Sequence[Mapping[str, Any]],
    tracer: WorkflowTracer,
) -> ModelResponse | None:
    auto = _context_compaction_auto_policy(
        _prepare_model_input_policy(plan.execution_policy)
    )
    if (
        not is_context_overflow_error(exc)
        or auto.get("retry_on_overflow") is not True
        or prepared_input.context_compactor is None
    ):
        return None
    metadata = {
        "phase": "overflow_retry",
        "trigger": "provider_context_overflow",
        "implementation": str(auto.get("implementation") or "injected"),
        "status": "retrying",
        "reason": "context_overflow",
    }
    replacement_messages = tuple(
        prepared_input.context_compactor(prepared_input.messages, metadata)
    )
    retry_request = build_openai_request(
        model=prepared_input.model,
        messages=replacement_messages,
        tools=tools,
        tool_choice=_tool_choice_for_phase(
            plan,
            prepared_input,
            phase="initial",
        ),
        response_format=prepared_input.response_format,
        **prepared_input.model_parameters,
    )
    state.node_inputs[str(node.id)] = retry_request.to_kwargs()
    tracer.emit(
        "context_overflow_retry",
        node_id=str(node.id),
        payload={
            **metadata,
            "message_count": len(replacement_messages),
        },
    )
    return await _create_model_response_async(prepared_input.adapter, retry_request)


def _iterative_loop_enabled(plan: ExecutionPlan) -> bool:
    policy = plan.tool_use_completion_policy
    return bool(policy is not None and policy.run_again == "required")


def _tool_choice_for_phase(
    plan: ExecutionPlan,
    prepared_input: PreparedModelInput,
    *,
    phase: str,
) -> Any:
    for policy in (prepared_input.tool_choice_policy, plan.tool_choice_policy):
        if policy is None:
            continue
        value = getattr(policy, phase, None)
        if value == "auto":
            return None
        if value == "required":
            return "required"
    return prepared_input.tool_choice


async def _execute_model_tool_loop_async(
    node: PreparedNode,
    plan: ExecutionPlan,
    state: WorkflowExecutionState,
    registry: ToolRegistry | None,
    guardrail_registry: InMemoryGuardrailRegistry | None,
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
                    guardrail_registry,
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
    messages, mid_turn_compaction = _apply_mid_turn_compaction(
        (*prepared_input.messages, *transcript),
        plan,
        prepared_input,
    )
    if mid_turn_compaction:
        tracer.emit(
            "mid_turn_compaction",
            node_id=str(node.id),
            payload=mid_turn_compaction,
        )
    if mid_turn_compaction.get("status") == "missing_collaborator":
        raise WorkflowExecutionError(
            f"llm_step node {node.id!r} requires mid-turn context compaction"
        )
    request = build_openai_request(
        model=prepared_input.model,
        messages=messages,
        tools=tools,
        tool_choice=_tool_choice_for_phase(
            plan,
            prepared_input,
            phase="after_tool_result",
        ),
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


def _apply_mid_turn_compaction(
    messages: Sequence[OpenAIMessage | Mapping[str, Any]],
    plan: ExecutionPlan,
    prepared_input: PreparedModelInput,
) -> tuple[tuple[OpenAIMessage | Mapping[str, Any], ...], Mapping[str, Any]]:
    normalized_messages = tuple(
        _message_from_model_input(message) for message in messages
    )
    compacted_parts, metadata = _apply_pre_turn_compaction(
        tuple(
            (f"mid_turn_message_{index}", message)
            for index, message in enumerate(normalized_messages, start=1)
        ),
        _prepare_model_input_policy(plan.execution_policy),
        prepared_input.adapter,
        model=prepared_input.model,
        context_compactor=prepared_input.context_compactor,
    )
    if not metadata:
        return tuple(messages), {}
    metadata = {**metadata, "phase": "mid_turn"}
    if metadata.get("status") != "complete":
        return tuple(messages), metadata
    return tuple(message for _part_name, message in compacted_parts), metadata


def _message_from_model_input(
    message: OpenAIMessage | Mapping[str, Any],
) -> OpenAIMessage:
    if isinstance(message, OpenAIMessage):
        return message
    return OpenAIMessage(
        role=str(message.get("role") or "user"),
        content=str(message.get("content") or ""),
    )


async def _coordinate_tool_invocation_async(
    *,
    node: PreparedNode,
    plan: ExecutionPlan,
    state: WorkflowExecutionState,
    tracer: WorkflowTracer,
    lifecycle_hooks: WorkflowLifecycleHooks | None,
    registry: ToolRegistry,
    tool: RegisteredTool,
    arguments: Mapping[str, Any],
    result_key: str,
    invoke: Callable[[PreparedToolInvocation | None], Awaitable[ToolResult]],
    approval_reason: str,
    action_id: str | None = None,
    emit_tool_invocation: bool = False,
    guardrail_runner: Callable[[PreparedToolInvocation], None] | None = None,
) -> ToolResult | WorkflowInterruptedResult:
    """Apply DAR's shared approval, lifecycle, and observation boundary."""

    prepared: PreparedToolInvocation | None = None
    if guardrail_runner is not None:
        prepared = registry.prepare_tool_invocation(tool.id, arguments)
        guardrail_runner(prepared)
    active_arguments = prepared.arguments if prepared is not None else arguments
    event_payload = {"tool_id": tool.id, "arguments": active_arguments}
    if action_id is not None:
        event_payload["tool_call_id"] = action_id
    if _approval_required(tool):
        prepared = prepared or registry.prepare_tool_invocation(tool.id, arguments)
        interruption = ApprovalInterruption(
            interruption_id=_new_approval_id(),
            run_id=str(state.run_id),
            workflow_id=str(plan.workflow.runtime_manifest.package_id),
            node_id=str(node.id),
            tool_id=tool.id,
            action_id=action_id,
            arguments=prepared.arguments,
            policy=_tool_policy_payload(tool),
            reason=approval_reason,
        )
        approval_payload = {
            "interruption_id": interruption.interruption_id,
            "tool_id": tool.id,
            "arguments": prepared.arguments,
            "policy": interruption.policy,
            "reason": interruption.reason,
        }
        if action_id is not None:
            approval_payload["tool_call_id"] = action_id
        tracer.emit(
            "approval_requested",
            node_id=str(node.id),
            payload=approval_payload,
            sensitive_fields=("arguments",),
        )
        paused_payload = {
            "interruption_id": interruption.interruption_id,
            "tool_id": tool.id,
            "state": interruption.state.value,
        }
        if action_id is not None:
            paused_payload["tool_call_id"] = action_id
        tracer.emit("approval_paused", node_id=str(node.id), payload=paused_payload)
        return WorkflowInterruptedResult(
            final_result=None,
            state=state,
            interruption=interruption,
        )
    tracer.emit(
        "tool_started",
        node_id=str(node.id),
        payload=event_payload,
        sensitive_fields=("arguments",),
    )
    if emit_tool_invocation:
        tracer.emit(
            "tool_invocation",
            node_id=str(node.id),
            payload=event_payload,
            sensitive_fields=("arguments",),
        )
    await invoke_lifecycle_hook_async(
        lifecycle_hooks.registered_hook("before_tool") if lifecycle_hooks else None,
        ToolHookContext(
            node_id=str(node.id),
            tool_id=tool.id,
            arguments=active_arguments,
            run_id=state.run_id,
        ),
    )
    result = await invoke(prepared)
    state.tool_results[result_key] = result
    trace_payload = result.trace_payload()
    if action_id is not None:
        trace_payload = {"tool_call_id": action_id, **trace_payload}
    tracer.emit(
        "tool_result",
        node_id=str(node.id),
        payload=trace_payload,
        sensitive_fields=tuple(dict.fromkeys(("output", *result.sensitive_fields))),
    )
    finished_payload = {
        "tool_id": tool.id,
        "success": result.success,
        "error": result.error,
    }
    if action_id is not None:
        finished_payload["tool_call_id"] = action_id
    tracer.emit("tool_finished", node_id=str(node.id), payload=finished_payload)
    await invoke_lifecycle_hook_async(
        lifecycle_hooks.registered_hook("after_tool") if lifecycle_hooks else None,
        ToolHookContext(
            node_id=str(node.id),
            tool_id=tool.id,
            arguments=active_arguments,
            result=result,
            error=result.error,
            run_id=state.run_id,
        ),
    )
    return result


async def _invoke_model_tool_call_async(
    node: PreparedNode,
    plan: ExecutionPlan,
    tool_call: ModelToolCall,
    tool_call_id: str,
    iteration: int,
    registry: ToolRegistry,
    guardrail_registry: InMemoryGuardrailRegistry | None,
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
    coordinated = await _coordinate_tool_invocation_async(
        node=node,
        plan=plan,
        state=state,
        tracer=tracer,
        lifecycle_hooks=lifecycle_hooks,
        registry=registry,
        tool=tool,
        arguments=arguments,
        result_key=f"{node.id}.{tool_call_id}",
        action_id=tool_call_id,
        invoke=lambda prepared: (
            registry.invoke_prepared_tool_async(prepared)
            if prepared is not None
            else registry.invoke_tool_async(tool.id, arguments)
        ),
        approval_reason=f"model tool {tool.id!r} requires approval",
        guardrail_runner=_tool_input_guardrail_runner(
            plan,
            guardrail_registry,
            tracer,
            node,
            tool_call_id,
        ),
    )
    if isinstance(coordinated, WorkflowInterruptedResult):
        return coordinated
    result = coordinated
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
    model_output = json.dumps(result.model_facing_output)
    arguments = (
        tool_call.arguments
        if isinstance(tool_call.arguments, str)
        else json.dumps(tool_call.arguments)
    )
    return (
        {
            "role": "assistant",
            "content": f"Tool call {tool_call_id}: {tool_call.name}",
            "_dar_transcript_type": "model_tool_call",
            "call_id": tool_call_id,
            "name": tool_call.name,
            "arguments": arguments,
        },
        {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_call.name,
            "content": model_output,
            "_dar_transcript_type": "model_tool_result",
            "call_id": tool_call_id,
            "output": model_output,
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
    guardrail_registry: InMemoryGuardrailRegistry | None,
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
    coordinated = await _coordinate_tool_invocation_async(
        node=node,
        plan=plan,
        state=state,
        tracer=tracer,
        lifecycle_hooks=lifecycle_hooks,
        registry=registry,
        tool=tool,
        arguments=arguments,
        result_key=str(node.id),
        invoke=lambda prepared: _invoke_tool_with_retry_async(
            node, registry, prepared or arguments, state, tracer
        ),
        approval_reason=f"tool {node.tool_id!r} requires approval",
        emit_tool_invocation=True,
        guardrail_runner=_tool_input_guardrail_runner(
            plan, guardrail_registry, tracer, node
        ),
    )
    if isinstance(coordinated, WorkflowInterruptedResult):
        return coordinated
    result = coordinated
    if not result.success and _failure_behavior(node) == "error":
        error = result.error or f"tool {node.tool_id!r} failed"
        state.errors.append(error)
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
    arguments: Mapping[str, Any] | PreparedToolInvocation,
    state: WorkflowExecutionState,
    tracer: WorkflowTracer,
) -> ToolResult:
    policy = _tool_retry_policy(node, registry)
    retry_failures = _retries_failures(policy)
    max_attempts = policy.max_attempts if retry_failures else 1
    last_result: ToolResult | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = (
                await registry.invoke_prepared_tool_async(arguments)
                if isinstance(arguments, PreparedToolInvocation)
                else await registry.invoke_tool_async(str(node.tool_id), arguments)
            )
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
    plan: ExecutionPlan,
    state: WorkflowExecutionState,
) -> tuple[dict[str, Any], PreparedInputMetadata]:
    context = _format_context(state)
    mutation_session_messages, mutation_context_metadata = (
        _mutation_context_session_messages(plan, state)
    )
    mutation_context = _mutation_render_context(
        node,
        state,
        session_messages=mutation_session_messages,
    )
    context.update(mutation_context)
    return context, _mutation_preparation_metadata(
        node,
        mutation_context,
        mutation_context_metadata,
    )


def _mutation_render_context(
    node: PreparedNode,
    state: WorkflowExecutionState,
    *,
    session_messages: Sequence[OpenAIMessage],
) -> dict[str, Any]:
    spec = node.mutation_spec
    if spec is None or spec.kind != "context_pruning":
        return {}
    return ContextPruningMutation(spec).render_context(
        prompt=state.prompt,
        session_messages=session_messages,
        resolve_source=lambda binding: _resolve_mutation_render_source(binding, state),
    )


def _mutation_context_session_messages(
    plan: ExecutionPlan,
    state: WorkflowExecutionState,
) -> tuple[tuple[OpenAIMessage, ...], Mapping[str, Any]]:
    policy = _prepare_model_input_policy(plan.execution_policy)
    if not policy:
        return state.session_messages, {}
    kept_session, pruned_session = _pruned_session_messages(
        state.session_messages,
        policy,
    )
    compaction = policy.get("context_compaction")
    if (
        isinstance(compaction, Mapping)
        and compaction.get("strategy") == "model_summary"
    ):
        summary_message = None
    else:
        summary_message = (
            _compacted_session_message(
                pruned_session,
                policy,
                state,
                context_summarizer=None,
            )
            if pruned_session
            else None
        )
    return kept_session, {
        "session_messages_included": len(kept_session),
        "session_messages_pruned": len(pruned_session),
        "context_compaction_applied": summary_message is not None,
    }


def _mutation_preparation_metadata(
    node: PreparedNode,
    mutation_context: Mapping[str, Any],
    mutation_context_metadata: Mapping[str, Any],
) -> PreparedInputMetadata:
    spec = node.mutation_spec
    if spec is None or spec.kind != "context_pruning" or not mutation_context:
        return PreparedInputMetadata()
    return PreparedInputMetadata(
        mutation_applied=True,
        mutation_id=spec.mutation_id,
        mutation_output_slots=tuple(mutation_context.keys()),
        mutation_attachment=_mutation_attachment_metadata(spec),
        mutation_context=dict(mutation_context_metadata),
    )


def _mutation_attachment_metadata(spec: Any) -> Mapping[str, Any]:
    config = spec.config if isinstance(spec.config, Mapping) else {}
    attachment = config.get("attachment")
    if isinstance(attachment, Mapping):
        return dict(attachment)
    return {
        "type": "llm_step_interaction",
        "target_node_id": spec.target_node_id,
    }


def _merge_prepared_input_metadata(
    base: PreparedInputMetadata,
    overlay: PreparedInputMetadata,
) -> PreparedInputMetadata:
    return PreparedInputMetadata(
        hierarchy_applied=base.hierarchy_applied,
        session_messages_included=base.session_messages_included,
        session_messages_pruned=base.session_messages_pruned,
        context_compaction_applied=base.context_compaction_applied,
        compaction=base.compaction,
        pre_turn_compaction=base.pre_turn_compaction,
        context_reset=base.context_reset,
        file_context_applied=base.file_context_applied,
        file_context_sources=base.file_context_sources,
        file_context_files_included=base.file_context_files_included,
        file_context_bytes=base.file_context_bytes,
        file_context_estimated_tokens=base.file_context_estimated_tokens,
        retrieved_context=base.retrieved_context,
        retrieved_context_omitted=base.retrieved_context_omitted,
        mutation_applied=overlay.mutation_applied,
        mutation_id=overlay.mutation_id,
        mutation_output_slots=overlay.mutation_output_slots,
        mutation_attachment=overlay.mutation_attachment,
        mutation_context=overlay.mutation_context,
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
        context_lanes=base.context_lanes,
        selection_policy=base.selection_policy,
        selected_turns=base.selected_turns,
        omitted_turns=base.omitted_turns,
        rejected_turns=base.rejected_turns,
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
        compaction=base.compaction,
        pre_turn_compaction=base.pre_turn_compaction,
        context_reset=base.context_reset,
        file_context_applied=base.file_context_applied,
        file_context_sources=base.file_context_sources,
        file_context_files_included=base.file_context_files_included,
        file_context_bytes=base.file_context_bytes,
        file_context_estimated_tokens=base.file_context_estimated_tokens,
        retrieved_context=base.retrieved_context,
        retrieved_context_omitted=base.retrieved_context_omitted,
        mutation_applied=base.mutation_applied,
        mutation_id=base.mutation_id,
        mutation_output_slots=base.mutation_output_slots,
        mutation_attachment=base.mutation_attachment,
        mutation_context=base.mutation_context,
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
        context_lanes=base.context_lanes,
        selection_policy=base.selection_policy,
        selected_turns=base.selected_turns,
        omitted_turns=base.omitted_turns,
        rejected_turns=base.rejected_turns,
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
    context_compactor: ContextCompactor | None,
    context_summarizer: ContextSummarizer | None,
    context_selector: ContextSelector | None,
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
    compression_profile = _compression_profile(policy)
    lane_budgets = _lane_budgets(policy)
    turn_metadata, segment_metadata = _session_turn_diagnostics(state.session_messages)
    context_threshold = _context_threshold_metadata(policy, adapter, model)
    selection_policy = _selection_policy(policy)
    selection_policy = _selection_policy_with_selector_status(
        selection_policy,
        context_selector,
    )
    lifecycle_stages = _lifecycle_stage_status(policy)
    metrics = _context_metrics(policy)
    (
        retrieved_context_parts,
        retrieved_context,
        retrieved_context_omitted,
    ) = _retrieved_context_messages(
        state,
        policy,
        lane_budgets,
        model=model,
    )
    result_parts.extend(retrieved_context_parts)
    kept_session, lane_trimmed_session = _apply_recent_turn_lane_budget(
        kept_session,
        lane_budgets,
        model=model,
    )
    (
        selected_turn_parts,
        selected_turns,
        omitted_turns,
        rejected_turns,
    ) = _selected_older_turn_parts(
        pruned_session,
        state.prompt,
        selection_policy,
        context_selector=context_selector,
        model=model,
    )
    context_compaction_applied = False
    compaction_metadata: Mapping[str, Any] = {}
    context_reset = _context_reset_metadata(pruned_session, policy)
    if pruned_session:
        summary_message = _compacted_session_message(
            pruned_session,
            policy,
            state,
            context_summarizer=context_summarizer,
        )
        if summary_message is not None:
            result_parts.append(("session_summary", summary_message))
            context_compaction_applied = True
            compaction_metadata = _compaction_metadata(
                pruned_session,
                summary_message,
                policy,
                model=model,
            )

    result_parts.extend(selected_turn_parts)

    for index, message in enumerate(kept_session, start=1):
        result_parts.append((f"session_message_{index}", message))

    if user_part is not None:
        result_parts.append(user_part)

    result_parts, pre_turn_compaction = _apply_pre_turn_compaction(
        result_parts,
        policy,
        adapter,
        model=model,
        context_compactor=context_compactor,
    )

    context_lanes = _context_lane_metadata(
        result_parts,
        lane_budgets,
        recent_trimmed_count=len(lane_trimmed_session),
        retrieved_omitted_count=len(retrieved_context_omitted),
    )

    return tuple(result_parts), PreparedInputMetadata(
        hierarchy_applied=hierarchy_applied,
        session_messages_included=len(kept_session),
        session_messages_pruned=len(pruned_session),
        context_compaction_applied=context_compaction_applied,
        compaction=compaction_metadata,
        pre_turn_compaction=pre_turn_compaction,
        context_reset=context_reset,
        file_context_applied=file_context_metadata.file_context_applied,
        file_context_sources=file_context_metadata.file_context_sources,
        file_context_files_included=file_context_metadata.file_context_files_included,
        file_context_bytes=file_context_metadata.file_context_bytes,
        file_context_estimated_tokens=file_context_metadata.file_context_estimated_tokens,
        retrieved_context=retrieved_context,
        retrieved_context_omitted=retrieved_context_omitted,
        turn_count=len(turn_metadata),
        segment_count=len(segment_metadata),
        turns=turn_metadata,
        segments=segment_metadata,
        context_threshold=context_threshold,
        compression_profile=compression_profile,
        lane_budgets=lane_budgets,
        context_lanes=context_lanes,
        selection_policy=selection_policy,
        selected_turns=selected_turns,
        omitted_turns=omitted_turns,
        rejected_turns=rejected_turns,
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


def _apply_recent_turn_lane_budget(
    messages: Sequence[OpenAIMessage],
    lane_budgets: Mapping[str, int],
    *,
    model: str,
) -> tuple[tuple[OpenAIMessage, ...], tuple[OpenAIMessage, ...]]:
    budget = lane_budgets.get("recent_turn_tokens")
    if budget is None:
        return tuple(messages), ()
    included: list[OpenAIMessage] = []
    omitted: list[OpenAIMessage] = []
    used_tokens = 0
    for message in messages:
        token_count = estimate_messages_tokens(
            ({"role": message.role, "content": message.content},),
            model=model,
        ).token_count
        if used_tokens + token_count > budget:
            omitted.append(message)
            continue
        included.append(message)
        used_tokens += token_count
    return tuple(included), tuple(omitted)


def _retrieved_context_messages(
    state: WorkflowExecutionState,
    policy: Mapping[str, Any],
    lane_budgets: Mapping[str, int],
    *,
    model: str,
) -> tuple[
    tuple[tuple[str, OpenAIMessage], ...],
    tuple[Mapping[str, Any], ...],
    tuple[Mapping[str, Any], ...],
]:
    retrieved_context = policy.get("retrieved_context")
    if (
        not isinstance(retrieved_context, Mapping)
        or retrieved_context.get("enabled") is not True
    ):
        return (), (), ()

    slot = str(retrieved_context.get("source_slot") or "retrieved_context")
    evidence_items = _retrieved_context_items(state.node_outputs.get(slot))
    if not evidence_items:
        return (), (), ()

    role = str(retrieved_context.get("prompt_role") or "developer")
    header = str(retrieved_context.get("header") or "Retrieved context:")
    budget = lane_budgets.get("retrieved_context_tokens")
    used_optional_tokens = 0
    parts: list[tuple[str, OpenAIMessage]] = []
    included: list[Mapping[str, Any]] = []
    omitted: list[Mapping[str, Any]] = []

    for item in evidence_items:
        metadata = _retrieved_context_metadata(item)
        token_count = _retrieved_context_token_estimate(item, model=model)
        required = metadata["required"] is True
        if (
            not required
            and budget is not None
            and used_optional_tokens + token_count > budget
        ):
            omitted.append(
                {
                    **metadata,
                    "selection_status": "omitted",
                    "selection_reason": "retrieved_context_lane_budget_exceeded",
                }
            )
            continue
        part_index = len(parts) + 1
        parts.append(
            (
                f"retrieved_context_{part_index}",
                OpenAIMessage(
                    role=role,
                    content=_render_retrieved_context_item(header, item),
                ),
            )
        )
        included.append({**metadata, "selection_status": "included"})
        if not required:
            used_optional_tokens += token_count

    return tuple(parts), tuple(included), tuple(omitted)


def _retrieved_context_items(value: Any) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, Mapping):
        evidence = value.get("evidence")
        if evidence is None:
            return (value,)
        value = evidence
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _retrieved_context_metadata(item: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata: dict[str, Any] = {
        "source_id": str(item.get("source_id") or ""),
        "chunk_id": str(item.get("chunk_id") or ""),
        "citation_handle": str(item.get("citation_handle") or ""),
        "required": _retrieved_context_required(item),
    }
    token_estimate = item.get("token_estimate")
    if isinstance(token_estimate, int) and not isinstance(token_estimate, bool):
        metadata["token_estimate"] = token_estimate
    score = item.get("score")
    if isinstance(score, int | float) and not isinstance(score, bool):
        metadata["score"] = score
    freshness = item.get("freshness")
    if isinstance(freshness, Mapping):
        metadata["freshness"] = dict(freshness)
    packing_hint = item.get("packing_hint")
    if isinstance(packing_hint, Mapping):
        metadata["packing_hint"] = dict(packing_hint)
    return {key: value for key, value in metadata.items() if value != ""}


def _retrieved_context_required(item: Mapping[str, Any]) -> bool:
    if item.get("required") is True or item.get("required_context") is True:
        return True
    lane_hint = item.get("lane_hint")
    return isinstance(lane_hint, str) and lane_hint.lower() == "required"


def _retrieved_context_token_estimate(
    item: Mapping[str, Any],
    *,
    model: str,
) -> int:
    token_estimate = item.get("token_estimate")
    if isinstance(token_estimate, int) and not isinstance(token_estimate, bool):
        return max(token_estimate, 0)
    content = str(item.get("content") or "")
    return estimate_messages_tokens(
        ({"role": "developer", "content": content},),
        model=model,
    ).token_count


def _render_retrieved_context_item(header: str, item: Mapping[str, Any]) -> str:
    lines = [header]
    for label, key in (
        ("Source ID", "source_id"),
        ("Chunk ID", "chunk_id"),
        ("Citation", "citation_handle"),
    ):
        value = item.get(key)
        if value is not None:
            lines.append(f"{label}: {value}")
    lines.append(str(item.get("content") or ""))
    return "\n".join(lines)


def _selected_older_turn_parts(
    pruned_session: Sequence[OpenAIMessage],
    prompt: str,
    selection_policy: Mapping[str, Any],
    *,
    context_selector: ContextSelector | None = None,
    model: str | None = None,
) -> tuple[
    tuple[tuple[str, OpenAIMessage], ...],
    tuple[Mapping[str, Any], ...],
    tuple[Mapping[str, Any], ...],
    tuple[Mapping[str, Any], ...],
]:
    strategy = str(selection_policy.get("strategy") or "")
    if strategy == "injected_semantic":
        if context_selector is None:
            fallback_policy = {
                key: value
                for key, value in selection_policy.items()
                if key
                in {
                    "max_selected_turns",
                    "chronological_reassembly",
                }
            }
            return _selected_older_turn_parts(
                pruned_session,
                prompt,
                {**fallback_policy, "strategy": "deterministic_overlap"},
                model=model,
            )
        return _injected_semantic_older_turn_parts(
            pruned_session,
            prompt,
            selection_policy,
            context_selector=context_selector,
            model=model,
        )
    if strategy not in {"deterministic_overlap", "hybrid_exact_semantic", "exact"}:
        return (), (), (), ()
    max_selected_turns = selection_policy.get("max_selected_turns")
    if (
        not isinstance(max_selected_turns, int)
        or isinstance(max_selected_turns, bool)
        or max_selected_turns <= 0
    ):
        return (), (), (), ()

    use_exact_tokens = strategy in {"hybrid_exact_semantic", "exact"}
    prompt_tokens = _selection_tokens(prompt, exact=use_exact_tokens)
    if not prompt_tokens:
        return (), (), (), ()

    scored_turns: list[tuple[int, int, str, tuple[OpenAIMessage, ...]]] = []
    rejected_turns: list[Mapping[str, Any]] = []
    for turn_index, messages in enumerate(_session_turns(pruned_session), start=1):
        turn_text = "\n".join(message.content for message in messages)
        score = len(
            prompt_tokens & _selection_tokens(turn_text, exact=use_exact_tokens)
        )
        if score > 0:
            scored_turns.append((score, turn_index, f"turn_{turn_index}", messages))
        else:
            rejected_turns.append(
                {
                    "turn_id": f"turn_{turn_index}",
                    "selection_status": "rejected",
                    "selection_reason": f"no_{strategy}_overlap",
                    "relevance_score": 0,
                }
            )

    ranked_candidates = sorted(scored_turns, key=lambda item: (-item[0], item[1]))
    selected_candidates = ranked_candidates[:max_selected_turns]
    omitted_candidates = ranked_candidates[max_selected_turns:]
    if selection_policy.get("chronological_reassembly") is not False:
        selected_candidates = sorted(selected_candidates, key=lambda item: item[1])

    parts: list[tuple[str, OpenAIMessage]] = []
    metadata: list[Mapping[str, Any]] = []
    for selected_index, (score, _turn_index, turn_id, messages) in enumerate(
        selected_candidates,
        start=1,
    ):
        lines = [f"Selected older turn {turn_id}:"]
        lines.extend(f"- {message.role}: {message.content}" for message in messages)
        parts.append(
            (
                f"selected_turn_{selected_index}",
                OpenAIMessage(role="developer", content="\n".join(lines)),
            )
        )
        metadata.append(
            {
                "turn_id": turn_id,
                "selection_status": "selected",
                "selection_reason": strategy,
                "relevance_score": score,
            }
        )
    omitted_turns = tuple(
        {
            "turn_id": turn_id,
            "selection_status": "omitted",
            "selection_reason": "max_selected_turns_exceeded",
            "relevance_score": score,
        }
        for score, _turn_index, turn_id, _messages in omitted_candidates
    )
    return tuple(parts), tuple(metadata), omitted_turns, tuple(rejected_turns)


def _injected_semantic_older_turn_parts(
    pruned_session: Sequence[OpenAIMessage],
    prompt: str,
    selection_policy: Mapping[str, Any],
    *,
    context_selector: ContextSelector,
    model: str | None,
) -> tuple[
    tuple[tuple[str, OpenAIMessage], ...],
    tuple[Mapping[str, Any], ...],
    tuple[Mapping[str, Any], ...],
    tuple[Mapping[str, Any], ...],
]:
    max_selected_turns = selection_policy.get("max_selected_turns")
    if not _valid_positive_int(max_selected_turns):
        return (), (), (), ()

    candidate_by_id = _semantic_turn_candidates(pruned_session, prompt, model=model)
    if not candidate_by_id:
        return (), (), (), ()

    rejected_turns: list[Mapping[str, Any]] = []
    selector_scores, selector_rejections = _semantic_selector_scores(
        context_selector,
        prompt,
        candidate_by_id,
        selection_policy,
    )
    rejected_turns.extend(selector_rejections)
    ranked_candidates = _rank_semantic_turns(
        candidate_by_id,
        selector_scores,
        rejected_turns,
    )
    selected_candidates = ranked_candidates[:max_selected_turns]
    omitted_candidates = ranked_candidates[max_selected_turns:]
    if selection_policy.get("chronological_reassembly") is not False:
        selected_candidates = sorted(
            selected_candidates,
            key=lambda item: item.turn_index,
        )
    parts, metadata = _semantic_selected_turn_parts(selected_candidates)
    omitted_turns = _semantic_omitted_turn_metadata(omitted_candidates)
    return tuple(parts), tuple(metadata), omitted_turns, tuple(rejected_turns)


def _valid_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _semantic_turn_candidates(
    pruned_session: Sequence[OpenAIMessage],
    prompt: str,
    *,
    model: str | None,
) -> dict[str, _SemanticTurnCandidate]:
    prompt_exact_tokens = _selection_tokens(prompt, exact=True)
    candidates: dict[str, _SemanticTurnCandidate] = {}
    for turn_index, messages in enumerate(_session_turns(pruned_session), start=1):
        turn_id = f"turn_{turn_index}"
        text = "\n".join(message.content for message in messages)
        exact_match_count = len(
            prompt_exact_tokens & _selection_tokens(text, exact=True)
        )
        candidate = ContextSelectionCandidate(
            turn_id=turn_id,
            text=text,
            roles=tuple(message.role for message in messages),
            exact_match_count=exact_match_count,
            token_estimate=_semantic_turn_token_estimate(messages, model=model),
        )
        candidates[turn_id] = _SemanticTurnCandidate(
            turn_index=turn_index,
            candidate=candidate,
            messages=messages,
        )
    return candidates


def _semantic_turn_token_estimate(
    messages: Sequence[OpenAIMessage],
    *,
    model: str | None,
) -> int | None:
    if model is None:
        return None
    return estimate_messages_tokens(
        tuple(
            {"role": message.role, "content": message.content} for message in messages
        ),
        model=model,
    ).token_count


def _semantic_selector_scores(
    context_selector: ContextSelector,
    prompt: str,
    candidate_by_id: Mapping[str, _SemanticTurnCandidate],
    selection_policy: Mapping[str, Any],
) -> tuple[dict[str, tuple[float, str]], tuple[Mapping[str, Any], ...]]:
    candidates = tuple(record.candidate for record in candidate_by_id.values())
    try:
        raw_selections = tuple(
            context_selector(
                prompt,
                candidates,
                _semantic_selector_metadata(selection_policy),
            )
        )
    except Exception as exc:
        return {}, (
            {
                "selection_status": "rejected",
                "selection_reason": "selector_error",
                "error_type": type(exc).__name__,
                "selector": "injected_semantic",
            },
        )

    selector_scores: dict[str, tuple[float, str]] = {}
    rejected_turns: list[Mapping[str, Any]] = []
    for selection in raw_selections:
        normalized = _normalize_semantic_selection(selection, candidate_by_id)
        if normalized[0] is None:
            rejected_turns.append(normalized[1])
            continue
        turn_id, score, reason = normalized[0]
        selector_scores[turn_id] = (score, reason)
    return selector_scores, tuple(rejected_turns)


def _semantic_selector_metadata(
    selection_policy: Mapping[str, Any],
) -> Mapping[str, Any]:
    return {
        key: value
        for key, value in selection_policy.items()
        if key
        in {
            "profile",
            "strategy",
            "max_selected_turns",
            "chronological_reassembly",
        }
    }


def _normalize_semantic_selection(
    selection: object,
    candidate_by_id: Mapping[str, _SemanticTurnCandidate],
) -> tuple[tuple[str, float, str] | None, Mapping[str, Any]]:
    if not isinstance(selection, ContextSelection):
        return None, {
            "selection_status": "rejected",
            "selection_reason": "invalid_selector_result",
            "selector": "injected_semantic",
        }
    if selection.turn_id not in candidate_by_id:
        return None, {
            "turn_id": selection.turn_id,
            "selection_status": "rejected",
            "selection_reason": "unknown_selector_turn",
            "relevance_score": selection.score,
            "selector": "injected_semantic",
        }
    if isinstance(selection.score, bool) or not isinstance(
        selection.score, int | float
    ):
        return None, {
            "turn_id": selection.turn_id,
            "selection_status": "rejected",
            "selection_reason": "invalid_selector_score",
            "selector": "injected_semantic",
        }
    return (
        (
            selection.turn_id,
            float(selection.score),
            selection.reason or "injected_semantic",
        ),
        {},
    )


def _rank_semantic_turns(
    candidate_by_id: Mapping[str, _SemanticTurnCandidate],
    selector_scores: Mapping[str, tuple[float, str]],
    rejected_turns: list[Mapping[str, Any]],
) -> list[_RankedSemanticTurn]:
    ranked_candidates: list[_RankedSemanticTurn] = []
    for turn_id, record in candidate_by_id.items():
        exact_count = record.candidate.exact_match_count
        if exact_count > 0:
            ranked_candidates.append(
                _RankedSemanticTurn(
                    exact_match_count=exact_count,
                    score=float(exact_count),
                    turn_index=record.turn_index,
                    turn_id=turn_id,
                    reason="exact_identifier_match",
                    messages=record.messages,
                )
            )
            continue
        selector_score = selector_scores.get(turn_id)
        if selector_score is None:
            rejected_turns.append(_semantic_missing_score_metadata(turn_id))
            continue
        score, reason = selector_score
        ranked_candidates.append(
            _RankedSemanticTurn(
                exact_match_count=0,
                score=score,
                turn_index=record.turn_index,
                turn_id=turn_id,
                reason=reason,
                messages=record.messages,
            )
        )
    return sorted(
        ranked_candidates,
        key=lambda item: (-item.exact_match_count, -item.score, item.turn_index),
    )


def _semantic_missing_score_metadata(turn_id: str) -> Mapping[str, Any]:
    return {
        "turn_id": turn_id,
        "selection_status": "rejected",
        "selection_reason": "no_injected_semantic_score",
        "relevance_score": 0,
        "selector": "injected_semantic",
    }


def _semantic_selected_turn_parts(
    selected_candidates: Sequence[_RankedSemanticTurn],
) -> tuple[list[tuple[str, OpenAIMessage]], list[Mapping[str, Any]]]:
    parts: list[tuple[str, OpenAIMessage]] = []
    metadata: list[Mapping[str, Any]] = []
    for selected_index, selected in enumerate(
        selected_candidates,
        start=1,
    ):
        lines = [f"Selected older turn {selected.turn_id}:"]
        lines.extend(
            f"- {message.role}: {message.content}" for message in selected.messages
        )
        parts.append(
            (
                f"selected_turn_{selected_index}",
                OpenAIMessage(role="developer", content="\n".join(lines)),
            )
        )
        metadata.append(
            {
                "turn_id": selected.turn_id,
                "selection_status": "selected",
                "selection_reason": selected.reason,
                "relevance_score": _semantic_score_value(selected.score),
                "selector": "injected_semantic",
            }
        )
    return parts, metadata


def _semantic_omitted_turn_metadata(
    omitted_candidates: Sequence[_RankedSemanticTurn],
) -> tuple[Mapping[str, Any], ...]:
    return tuple(
        {
            "turn_id": candidate.turn_id,
            "selection_status": "omitted",
            "selection_reason": "max_selected_turns_exceeded",
            "relevance_score": _semantic_score_value(candidate.score),
            "selector": "injected_semantic",
        }
        for candidate in omitted_candidates
    )


def _semantic_score_value(score: float) -> int | float:
    return int(score) if score.is_integer() else score


def _session_turns(
    session_messages: Sequence[OpenAIMessage],
) -> tuple[tuple[OpenAIMessage, ...], ...]:
    turns: list[list[OpenAIMessage]] = []
    current: list[OpenAIMessage] = []
    for message in session_messages:
        if message.role == "user" and current:
            turns.append(current)
            current = []
        current.append(message)
    if current:
        turns.append(current)
    return tuple(tuple(turn) for turn in turns)


def _selection_tokens(value: str, *, exact: bool = False) -> set[str]:
    pattern = r"[A-Za-z0-9][A-Za-z0-9_.:/-]*" if exact else r"[A-Za-z]+"
    return {token for token in re.findall(pattern, value.lower()) if len(token) >= 4}


def _context_lane_metadata(
    parts: Sequence[tuple[str, OpenAIMessage]],
    lane_budgets: Mapping[str, int],
    *,
    recent_trimmed_count: int,
    retrieved_omitted_count: int,
) -> tuple[Mapping[str, Any], ...]:
    lane_order = (
        "pinned",
        "file_tool",
        "retrieved_context",
        "rolling_summary",
        "selected_older_turns",
        "recent_turns",
        "current_turn",
    )
    lane_parts: dict[str, list[str]] = {lane_id: [] for lane_id in lane_order}
    for part_name, _message in parts:
        lane_parts[_part_lane_id(part_name)].append(part_name)
    lanes: list[Mapping[str, Any]] = []
    for lane_id in lane_order:
        part_names = tuple(lane_parts[lane_id])
        if (
            not part_names
            and not (lane_id == "recent_turns" and recent_trimmed_count)
            and not (lane_id == "retrieved_context" and retrieved_omitted_count)
        ):
            continue
        budget = lane_budgets.get(_lane_budget_key(lane_id))
        omitted_count = (
            retrieved_omitted_count
            if lane_id == "retrieved_context"
            else recent_trimmed_count
            if lane_id == "recent_turns"
            else 0
        )
        lane: dict[str, Any] = {
            "lane_id": lane_id,
            "part_count": len(part_names),
            "part_names": part_names,
            "trimmed_count": recent_trimmed_count if lane_id == "recent_turns" else 0,
            "omitted_count": omitted_count,
        }
        if budget is not None:
            lane["budget_tokens"] = budget
        lanes.append(lane)
    return tuple(lanes)


def _part_lane_id(part_name: str) -> str:
    if part_name.startswith("hierarchy_") or part_name in {
        "system",
        "developer",
        "skill_instructions",
    }:
        return "pinned"
    if part_name.startswith("file_context_"):
        return "file_tool"
    if part_name.startswith("retrieved_context_"):
        return "retrieved_context"
    if part_name == "session_summary":
        return "rolling_summary"
    if part_name.startswith("selected_turn_"):
        return "selected_older_turns"
    if part_name.startswith("session_message_"):
        return "recent_turns"
    if part_name == "user_prompt":
        return "current_turn"
    return "pinned"


def _lane_budget_key(lane_id: str) -> str:
    return {
        "pinned": "pinned_tokens",
        "file_tool": "file_context_tokens",
        "retrieved_context": "retrieved_context_tokens",
        "rolling_summary": "summary_tokens",
        "selected_older_turns": "selected_turn_tokens",
        "recent_turns": "recent_turn_tokens",
        "current_turn": "current_turn_tokens",
    }[lane_id]


def _selection_policy(policy: Mapping[str, Any]) -> Mapping[str, Any]:
    compression = policy.get("context_compression")
    if not isinstance(compression, Mapping):
        return {}
    profile = str(compression.get("profile") or "")
    selection = compression.get("selection")
    if not isinstance(selection, Mapping):
        return {}
    result: dict[str, Any] = {}
    if profile in {"exact", "semantic"}:
        result["profile"] = profile
    for key in ("strategy", "max_selected_turns", "chronological_reassembly"):
        if key in selection:
            result[key] = selection[key]
    return result


def _selection_policy_with_selector_status(
    selection_policy: Mapping[str, Any],
    context_selector: ContextSelector | None,
) -> Mapping[str, Any]:
    if selection_policy.get("strategy") != "injected_semantic":
        return selection_policy
    if context_selector is None:
        return {
            **selection_policy,
            "selector_status": "missing",
            "fallback_strategy": "deterministic_overlap",
        }
    return {**selection_policy, "selector_status": "available"}


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


def _apply_pre_turn_compaction(
    parts: Sequence[tuple[str, OpenAIMessage]],
    policy: Mapping[str, Any],
    adapter: ModelAdapter,
    *,
    model: str,
    context_compactor: ContextCompactor | None,
) -> tuple[list[tuple[str, OpenAIMessage]], Mapping[str, Any]]:
    auto = _context_compaction_auto_policy(policy)
    if auto.get("enabled") is not True:
        return list(parts), {}
    implementation = str(auto.get("implementation") or "metadata_only")
    if implementation != "injected":
        return list(parts), {}
    messages = tuple(message for _part_name, message in parts)
    tokens_before = estimate_messages_tokens(
        tuple(
            {"role": message.role, "content": message.content} for message in messages
        ),
        model=model,
    ).token_count
    threshold = _pre_turn_compaction_threshold(auto, adapter, model)
    base_metadata: dict[str, Any] = {
        "phase": "pre_turn",
        "trigger": str(auto.get("trigger") or "token_threshold"),
        "implementation": implementation,
        "threshold_tokens": threshold,
        "tokens_before": tokens_before,
    }
    if threshold is None or tokens_before <= threshold:
        return list(parts), {
            **base_metadata,
            "status": "skipped",
            "reason": "under_threshold",
            "tokens_after": tokens_before,
        }
    if context_compactor is None:
        return list(parts), {
            **base_metadata,
            "status": "missing_collaborator",
            "reason": "context_compactor_unavailable",
            "tokens_after": tokens_before,
        }
    replacement_messages = tuple(context_compactor(messages, base_metadata))
    tokens_after = estimate_messages_tokens(
        tuple(
            {"role": message.role, "content": message.content}
            for message in replacement_messages
        ),
        model=model,
    ).token_count
    replacement_parts = [
        (f"pre_turn_compacted_{index}", message)
        for index, message in enumerate(replacement_messages, start=1)
    ]
    return replacement_parts, {
        **base_metadata,
        "status": "complete",
        "reason": "token_threshold_exceeded",
        "tokens_after": tokens_after,
    }


def _pre_turn_compaction_threshold(
    auto: Mapping[str, Any],
    adapter: ModelAdapter,
    model: str,
) -> int | None:
    threshold_tokens = auto.get("threshold_tokens")
    if isinstance(threshold_tokens, int) and not isinstance(threshold_tokens, bool):
        return threshold_tokens
    context_window = _adapter_context_window(adapter, model)
    if context_window is None:
        return None
    threshold_ratio = min(float(auto.get("threshold_ratio", 0.9)), 0.9)
    return int(context_window * threshold_ratio)


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
    turns = _session_turns(session_messages)
    kept_turns: list[tuple[OpenAIMessage, ...]] = []
    kept_count = 0
    for turn in reversed(turns):
        if kept_turns and kept_count + len(turn) > limit:
            break
        kept_turns.append(turn)
        kept_count += len(turn)
        if kept_count >= limit:
            break
    kept_turns.reverse()
    pruned_turn_count = len(turns) - len(kept_turns)
    return (
        tuple(message for turn in kept_turns for message in turn),
        tuple(message for turn in turns[:pruned_turn_count] for message in turn),
    )


def _compacted_session_message(
    pruned_session: Sequence[OpenAIMessage],
    policy: Mapping[str, Any],
    state: WorkflowExecutionState,
    *,
    context_summarizer: ContextSummarizer | None,
) -> OpenAIMessage | None:
    compaction = policy.get("context_compaction")
    if not isinstance(compaction, Mapping):
        return None
    if compaction.get("reset_behavior") == "new_window":
        return None
    strategy = str(compaction.get("strategy") or "summary_message")
    if strategy == "rolling_summary":
        return _rolling_summary_message(pruned_session, compaction, state)
    if strategy == "model_summary":
        return _model_summary_message(
            pruned_session,
            compaction,
            context_summarizer=context_summarizer,
        )
    if strategy not in {"summary_message", "basic"}:
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


def _model_summary_message(
    pruned_session: Sequence[OpenAIMessage],
    compaction: Mapping[str, Any],
    *,
    context_summarizer: ContextSummarizer | None,
) -> OpenAIMessage | None:
    config = compaction.get("model_summary")
    if not isinstance(config, Mapping) or config.get("enabled") is not True:
        return None
    if context_summarizer is None:
        raise WorkflowExecutionError(
            "context_compaction strategy 'model_summary' requires context_summarizer"
        )
    role = str(compaction.get("summary_role") or "developer")
    max_chars = _optional_positive_int(config.get("max_summary_chars")) or 4000
    metadata = {
        "strategy": "model_summary",
        "source_message_count": len(pruned_session),
        "max_summary_chars": max_chars,
    }
    raw_summary = context_summarizer(tuple(pruned_session), metadata)
    if isinstance(raw_summary, OpenAIMessage):
        content = raw_summary.content
        role = raw_summary.role
    else:
        content = str(raw_summary)
    content = content[:max_chars]
    return OpenAIMessage(role=role, content=content)


def _context_reset_metadata(
    pruned_session: Sequence[OpenAIMessage],
    policy: Mapping[str, Any],
) -> Mapping[str, Any]:
    compaction = policy.get("context_compaction")
    if (
        not pruned_session
        or not isinstance(compaction, Mapping)
        or compaction.get("reset_behavior") != "new_window"
    ):
        return {}
    return {
        "reset_behavior": "new_window",
        "reason": str(compaction.get("reset_reason") or "policy"),
        "session_messages_dropped": len(pruned_session),
        "compaction_success": False,
    }


def _rolling_summary_message(
    pruned_session: Sequence[OpenAIMessage],
    compaction: Mapping[str, Any],
    state: WorkflowExecutionState,
) -> OpenAIMessage | None:
    rolling_summary = compaction.get("rolling_summary")
    if (
        not isinstance(rolling_summary, Mapping)
        or rolling_summary.get("enabled") is not True
    ):
        return None
    role = str(compaction.get("summary_role") or "developer")
    prior_summary_slot = str(
        rolling_summary.get("prior_summary_slot") or "rolling_summary"
    )
    source_slot = str(
        rolling_summary.get("source_provenance_slot") or "source_provenance"
    )
    retained_turns = _retained_rolling_summary_turns(
        pruned_session,
        rolling_summary,
    )
    lines = [
        "Rolling context summary:",
        "## Prior Summary",
        str(state.node_outputs.get(prior_summary_slot) or "Not recorded."),
        "## Retained Turns",
    ]
    if retained_turns:
        for turn in retained_turns:
            lines.extend(f"- {message.role}: {message.content}" for message in turn)
    else:
        lines.append("Not recorded.")
    lines.extend(["## Source Provenance"])
    source_provenance = _rolling_summary_source_provenance(
        state.node_outputs.get(source_slot)
    )
    if source_provenance:
        lines.extend(f"- {source}" for source in source_provenance)
    else:
        lines.append("Not recorded.")
    lines.extend(["## Open Decisions", "Not recorded."])
    return OpenAIMessage(role=role, content="\n".join(lines))


def _retained_rolling_summary_turns(
    pruned_session: Sequence[OpenAIMessage],
    rolling_summary: Mapping[str, Any],
) -> tuple[tuple[OpenAIMessage, ...], ...]:
    max_retained_turns = (
        _optional_positive_int(rolling_summary.get("max_retained_turns")) or 1
    )
    return _session_turns(pruned_session)[-max_retained_turns:]


def _rolling_summary_source_provenance(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(str(item) for item in value if item is not None)
    return (str(value),)


def _compaction_metadata(
    pruned_session: Sequence[OpenAIMessage],
    summary_message: OpenAIMessage,
    policy: Mapping[str, Any],
    *,
    model: str,
) -> Mapping[str, Any]:
    compaction = policy.get("context_compaction")
    strategy = (
        str(compaction.get("strategy") or "summary_message")
        if isinstance(compaction, Mapping)
        else "summary_message"
    )
    before_tokens = estimate_messages_tokens(
        tuple(
            {"role": message.role, "content": message.content}
            for message in pruned_session
        ),
        model=model,
    ).token_count
    after_tokens = estimate_messages_tokens(
        ({"role": summary_message.role, "content": summary_message.content},),
        model=model,
    ).token_count
    return {
        "strategy": strategy,
        "messages_before": len(pruned_session),
        "messages_after": 1,
        "tokens_before": before_tokens,
        "tokens_after": after_tokens,
        "compression_ratio": after_tokens / before_tokens if before_tokens else 1,
        **_model_summary_metadata(summary_message, compaction),
        **_rolling_summary_metadata(pruned_session, compaction),
    }


def _model_summary_metadata(
    summary_message: OpenAIMessage,
    compaction: Any,
) -> Mapping[str, Any]:
    if not isinstance(compaction, Mapping):
        return {}
    if str(compaction.get("strategy") or "") != "model_summary":
        return {}
    return {"summary_chars": len(summary_message.content)}


def _rolling_summary_metadata(
    pruned_session: Sequence[OpenAIMessage],
    compaction: Any,
) -> Mapping[str, Any]:
    if not isinstance(compaction, Mapping):
        return {}
    if str(compaction.get("strategy") or "") != "rolling_summary":
        return {}
    rolling_summary = compaction.get("rolling_summary")
    if not isinstance(rolling_summary, Mapping):
        return {}
    retained_turn_count = len(
        _retained_rolling_summary_turns(pruned_session, rolling_summary)
    )
    total_turn_count = max(len(_session_turns(pruned_session)), 1)
    return {
        "retained_turn_count": retained_turn_count,
        "information_retention_proxy": retained_turn_count / total_turn_count,
    }


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
        "tool_results": {
            key: result.model_facing_output
            for key, result in state.tool_results.items()
        },
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
