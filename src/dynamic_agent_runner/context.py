"""Execution context objects for dynamic-agent workflow runs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from dynamic_agent_runner.context_compaction import ProviderContextCompactor
from dynamic_agent_runner.context_selection import ContextSelector
from dynamic_agent_runner.models import CompiledAgentWorkflow, LoadedAgentWorkflow
from dynamic_agent_runner.openai_client import (
    AsyncOpenAIClientAdapter,
    OpenAIClientAdapter,
)
from dynamic_agent_runner.registry import ToolRegistry
from dynamic_agent_runner.tracing import TraceSink
from dynamic_agent_runner.hooks import WorkflowLifecycleHooks
from dynamic_agent_runner.guardrails import InMemoryGuardrailRegistry


@dataclass(frozen=True)
class WorkflowExecutionContext:
    """Stable execution envelope for a loaded workflow.

    The context groups runtime collaborators and caller policy overrides that
    were historically passed as separate ``execute_workflow(...)`` keyword
    arguments. It intentionally does not include the user prompt because prompts
    are per-run inputs while the context can be reused across runs.
    """

    workflow: LoadedAgentWorkflow | CompiledAgentWorkflow
    tool_registry: ToolRegistry | None = None
    guardrail_registry: InMemoryGuardrailRegistry | None = None
    model_adapter: (
        OpenAIClientAdapter
        | AsyncOpenAIClientAdapter
        | Sequence[OpenAIClientAdapter | AsyncOpenAIClientAdapter]
        | None
    ) = None
    max_steps: int | None = None
    trace_sink: TraceSink | None = None
    prompt_cache: bool | None = None
    lifecycle_hooks: WorkflowLifecycleHooks | None = None
    model_adapter_coverage: str = "augmented"
    context_selector: ContextSelector | None = None
    provider_context_compactor: ProviderContextCompactor | None = None
    embedding_profile_id: str | None = None
    embedding_producer: object | None = None
    embedding_producer_mode: str | None = None


RunContext = WorkflowExecutionContext


__all__ = ["RunContext", "WorkflowExecutionContext"]
