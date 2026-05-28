"""Execution context objects for dynamic-agent workflow runs."""

from __future__ import annotations

from dataclasses import dataclass

from dynamic_agent_runner.models import LoadedAgentWorkflow
from dynamic_agent_runner.openai_client import OpenAIClientAdapter
from dynamic_agent_runner.registry import ToolRegistry
from dynamic_agent_runner.tracing import TraceSink


@dataclass(frozen=True)
class WorkflowExecutionContext:
    """Stable execution envelope for a loaded workflow.

    The context groups runtime collaborators and caller policy overrides that
    were historically passed as separate ``execute_workflow(...)`` keyword
    arguments. It intentionally does not include the user prompt because prompts
    are per-run inputs while the context can be reused across runs.
    """

    workflow: LoadedAgentWorkflow
    tool_registry: ToolRegistry | None = None
    model_adapter: OpenAIClientAdapter | None = None
    max_steps: int | None = None
    trace_sink: TraceSink | None = None
    prompt_cache: bool | None = None


RunContext = WorkflowExecutionContext


__all__ = ["RunContext", "WorkflowExecutionContext"]
