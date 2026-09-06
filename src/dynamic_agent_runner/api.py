"""Public API for loading and running dynamic-agent workflow artifacts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from dynamic_agent_runner.artifacts import (
    compile_agent_package,
    compile_loaded_workflow,
    load_agent_package,
    load_agent_workflow_artifacts,
    load_runtime_behavior_overrides,
)
from dynamic_agent_runner.context import WorkflowExecutionContext
from dynamic_agent_runner.executor import (
    WorkflowInterruptedResult,
    _run_async_from_sync,
    execute_workflow_async,
)
from dynamic_agent_runner.errors import WorkflowExecutionError
from dynamic_agent_runner.hooks import WorkflowLifecycleHooks
from dynamic_agent_runner.guardrails import InMemoryGuardrailRegistry
from dynamic_agent_runner.models import CompiledAgentWorkflow, LoadedAgentWorkflow
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
    package_directory: str | None = None,
    runtime_manifest: Any | None = None,
    definition_yaml: Any | None = None,
    mermaid_graph: str | None = None,
    mermaid_diagram: str | None = None,
    agent_design: str | None = None,
    tool_index: Any | None = None,
    runtime_overrides: Any | None = None,
    tool_registry: Any | None = None,
) -> LoadedAgentWorkflow:
    """Load a workflow definition without executing the workflow.

    `package_directory` is the canonical public input and expects a directory
    containing the standard `agent-runtime.yaml`, `agent-design.md`, and
    `agent-graph.mmd` sibling artifacts. The file-by-file artifact inputs remain
    available as a lower-level compatibility seam.
    """

    if package_directory is not None:
        if any(
            value is not None
            for value in (
                runtime_manifest,
                definition_yaml,
                mermaid_graph,
                mermaid_diagram,
                agent_design,
                tool_index,
            )
        ):
            raise TypeError(
                "package_directory cannot be combined with individual artifact inputs"
            )

        workflow = load_agent_package(package_directory)
        if runtime_overrides is not None:
            workflow = LoadedAgentWorkflow(
                runtime_manifest=workflow.runtime_manifest,
                package_root=workflow.package_root,
                skill_bundle_root=workflow.skill_bundle_root,
                mermaid_graph=workflow.mermaid_graph,
                agent_design=workflow.agent_design,
                tool_index=workflow.tool_index,
                runtime_overrides=load_runtime_behavior_overrides(runtime_overrides),
            )
        validate_agent_workflow(workflow, tool_registry=tool_registry)
        return workflow

    runtime_input = (
        runtime_manifest if runtime_manifest is not None else definition_yaml
    )
    if runtime_input is None:
        raise TypeError(
            "load_agent_workflow requires package_directory or runtime_manifest"
        )

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


def compile_agent_workflow(
    workflow: LoadedAgentWorkflow,
    *,
    runtime_overrides: Any | None = None,
    tool_registry: Any | None = None,
) -> CompiledAgentWorkflow:
    """Compile a loaded workflow into a final execution-ready workflow."""

    compiled = compile_loaded_workflow(
        workflow,
        runtime_overrides=runtime_overrides,
    )
    validate_agent_workflow(compiled, tool_registry=tool_registry)
    return compiled


def load_agent_package_workflow(
    package_directory: str,
    *,
    runtime_overrides: Any | None = None,
    tool_registry: Any | None = None,
) -> CompiledAgentWorkflow:
    """Load and compile a package-directory-first workflow bundle."""

    compiled = compile_agent_package(
        package_directory,
        runtime_overrides=runtime_overrides,
    )
    validate_agent_workflow(compiled, tool_registry=tool_registry)
    return compiled


def run_agent_workflow(
    *,
    prompt: str,
    execution_context: WorkflowExecutionContext | None = None,
    package_directory: str | None = None,
    runtime_manifest: Any | None = None,
    definition_yaml: Any | None = None,
    mermaid_graph: str | None = None,
    mermaid_diagram: str | None = None,
    agent_design: str | None = None,
    tool_index: Any | None = None,
    runtime_overrides: Any | None = None,
    tool_registry: Any | None = None,
    guardrail_registry: InMemoryGuardrailRegistry | None = None,
    model_adapter: ModelAdapterValue | None = None,
    max_steps: int | None = None,
    trace_sink: Any | None = None,
    prompt_cache: bool | None = None,
    lifecycle_hooks: WorkflowLifecycleHooks | None = None,
    model_adapter_coverage: str | None = None,
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
            package_directory=package_directory,
            runtime_manifest=runtime_manifest,
            definition_yaml=definition_yaml,
            mermaid_graph=mermaid_graph,
            mermaid_diagram=mermaid_diagram,
            agent_design=agent_design,
            tool_index=tool_index,
            runtime_overrides=runtime_overrides,
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


async def run_agent_workflow_async(
    *,
    prompt: str,
    execution_context: WorkflowExecutionContext | None = None,
    package_directory: str | None = None,
    runtime_manifest: Any | None = None,
    definition_yaml: Any | None = None,
    mermaid_graph: str | None = None,
    mermaid_diagram: str | None = None,
    agent_design: str | None = None,
    tool_index: Any | None = None,
    runtime_overrides: Any | None = None,
    tool_registry: Any | None = None,
    guardrail_registry: InMemoryGuardrailRegistry | None = None,
    model_adapter: ModelAdapterValue | None = None,
    max_steps: int | None = None,
    trace_sink: Any | None = None,
    prompt_cache: bool | None = None,
    lifecycle_hooks: WorkflowLifecycleHooks | None = None,
    model_adapter_coverage: str | None = None,
    run_id: str | None = None,
) -> Any:
    """Run generated workflow artifacts asynchronously and return final output."""

    if execution_context is not None:
        if any(
            value is not None
            for value in (
                runtime_manifest,
                package_directory,
                definition_yaml,
                mermaid_graph,
                mermaid_diagram,
                agent_design,
                tool_index,
                runtime_overrides,
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
            raise TypeError(
                "execution_context cannot be combined with artifact or runtime "
                "keyword arguments"
            )
        result = await execute_workflow_async(
            execution_context, prompt=prompt, run_id=run_id
        )
        return _final_result_or_error(result)

    if package_directory is not None:
        workflow = load_agent_package_workflow(
            package_directory,
            runtime_overrides=runtime_overrides,
            tool_registry=tool_registry,
        )
    else:
        workflow = compile_agent_workflow(
            load_agent_workflow(
                runtime_manifest=runtime_manifest,
                definition_yaml=definition_yaml,
                mermaid_graph=mermaid_graph,
                mermaid_diagram=mermaid_diagram,
                agent_design=agent_design,
                tool_index=tool_index,
                tool_registry=tool_registry,
            ),
            runtime_overrides=runtime_overrides,
            tool_registry=tool_registry,
        )
    result = await execute_workflow_async(
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
    return _final_result_or_error(result)


def _final_result_or_error(result: Any) -> Any:
    if isinstance(result, WorkflowInterruptedResult):
        interruption = result.interruption
        raise WorkflowExecutionError(
            "workflow interrupted for approval at "
            f"node {interruption.node_id!r} tool {interruption.tool_id!r}; "
            "use execute_workflow to inspect the interruption"
        )
    return result.final_result
