"""Public API for loading and running dynamic-agent workflow artifacts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from dynamic_agent_runner.artifacts import (
    load_agent_package,
    load_agent_workflow_artifacts,
)
from dynamic_agent_runner.context import WorkflowExecutionContext
from dynamic_agent_runner.executor import (
    _run_async_from_sync,
    execute_workflow_async,
)
from dynamic_agent_runner.hooks import WorkflowLifecycleHooks
from dynamic_agent_runner.models import LoadedAgentWorkflow
from dynamic_agent_runner.openai_client import (
    AsyncOpenAIClientAdapter,
    OpenAIClientAdapter,
)
from dynamic_agent_runner.validation import validate_agent_workflow


ModelAdapterValue = (
    OpenAIClientAdapter
    | AsyncOpenAIClientAdapter
    | Sequence[OpenAIClientAdapter | AsyncOpenAIClientAdapter]
)


def load_agent_workflow(
    *,
    runtime_manifest: Any | None = None,
    definition_yaml: Any | None = None,
    mermaid_graph: str | None = None,
    mermaid_diagram: str | None = None,
    agent_design: str | None = None,
    tool_index: Any | None = None,
    runtime_overrides: Any | None = None,
    tool_registry: Any | None = None,
) -> LoadedAgentWorkflow:
    """Load generated workflow artifacts without executing the workflow.

    `runtime_manifest` is the preferred name for the generated
    `agent-runtime.yaml` input. `definition_yaml` is accepted as a compatibility
    alias for the earlier README sketch.
    """

    runtime_input = (
        runtime_manifest if runtime_manifest is not None else definition_yaml
    )
    if runtime_input is None:
        raise TypeError("load_agent_workflow requires runtime_manifest")

    graph_input = mermaid_graph if mermaid_graph is not None else mermaid_diagram
    workflow = load_agent_workflow_artifacts(
        runtime_manifest=runtime_input,
        mermaid_graph=graph_input,
        agent_design=agent_design,
        tool_index=tool_index,
        runtime_overrides=runtime_overrides,
    )
    validate_agent_workflow(workflow, tool_registry=tool_registry)
    return workflow


def load_agent_package_workflow(
    package_directory: str,
    *,
    tool_registry: Any | None = None,
) -> LoadedAgentWorkflow:
    """Load a package-directory-first workflow bundle without executing it."""

    workflow = load_agent_package(package_directory)
    validate_agent_workflow(workflow, tool_registry=tool_registry)
    return workflow


def run_agent_workflow(
    *,
    prompt: str,
    execution_context: WorkflowExecutionContext | None = None,
    runtime_manifest: Any | None = None,
    definition_yaml: Any | None = None,
    mermaid_graph: str | None = None,
    mermaid_diagram: str | None = None,
    agent_design: str | None = None,
    tool_index: Any | None = None,
    runtime_overrides: Any | None = None,
    tool_registry: Any | None = None,
    model_adapter: ModelAdapterValue | None = None,
    max_steps: int | None = None,
    trace_sink: Any | None = None,
    prompt_cache: bool | None = None,
    lifecycle_hooks: WorkflowLifecycleHooks | None = None,
    run_id: str | None = None,
) -> Any:
    """Run an agent workflow from generated artifacts and a user prompt.

    This API returns the final workflow result. Detailed execution state is
    available from `dynamic_agent_runner.executor.execute_workflow`.
    """

    return _run_async_from_sync(
        lambda: run_agent_workflow_async(
            prompt=prompt,
            execution_context=execution_context,
            runtime_manifest=runtime_manifest,
            definition_yaml=definition_yaml,
            mermaid_graph=mermaid_graph,
            mermaid_diagram=mermaid_diagram,
            agent_design=agent_design,
            tool_index=tool_index,
            runtime_overrides=runtime_overrides,
            tool_registry=tool_registry,
            model_adapter=model_adapter,
            max_steps=max_steps,
            trace_sink=trace_sink,
            prompt_cache=prompt_cache,
            lifecycle_hooks=lifecycle_hooks,
            run_id=run_id,
        )
    )


async def run_agent_workflow_async(
    *,
    prompt: str,
    execution_context: WorkflowExecutionContext | None = None,
    runtime_manifest: Any | None = None,
    definition_yaml: Any | None = None,
    mermaid_graph: str | None = None,
    mermaid_diagram: str | None = None,
    agent_design: str | None = None,
    tool_index: Any | None = None,
    runtime_overrides: Any | None = None,
    tool_registry: Any | None = None,
    model_adapter: ModelAdapterValue | None = None,
    max_steps: int | None = None,
    trace_sink: Any | None = None,
    prompt_cache: bool | None = None,
    lifecycle_hooks: WorkflowLifecycleHooks | None = None,
    run_id: str | None = None,
) -> Any:
    """Run generated workflow artifacts asynchronously and return final output."""

    if execution_context is not None:
        if any(
            value is not None
            for value in (
                runtime_manifest,
                definition_yaml,
                mermaid_graph,
                mermaid_diagram,
                agent_design,
                tool_index,
                runtime_overrides,
                tool_registry,
                model_adapter,
                max_steps,
                trace_sink,
                prompt_cache,
                lifecycle_hooks,
            )
        ):
            raise TypeError(
                "execution_context cannot be combined with artifact or runtime "
                "keyword arguments"
            )
        result = await execute_workflow_async(
            execution_context, prompt=prompt, run_id=run_id
        )
        return result.final_result

    workflow = load_agent_workflow(
        runtime_manifest=runtime_manifest,
        definition_yaml=definition_yaml,
        mermaid_graph=mermaid_graph,
        mermaid_diagram=mermaid_diagram,
        agent_design=agent_design,
        tool_index=tool_index,
        runtime_overrides=runtime_overrides,
        tool_registry=tool_registry,
    )
    result = await execute_workflow_async(
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
    return result.final_result
