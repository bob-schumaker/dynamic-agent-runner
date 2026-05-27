"""Public API for loading and running dynamic-agent workflow artifacts."""

from __future__ import annotations

from typing import Any

from dynamic_agent_runner.artifacts import load_agent_workflow_artifacts
from dynamic_agent_runner.executor import execute_workflow
from dynamic_agent_runner.models import LoadedAgentWorkflow
from dynamic_agent_runner.validation import validate_agent_workflow


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


def run_agent_workflow(
    *,
    prompt: str,
    runtime_manifest: Any | None = None,
    definition_yaml: Any | None = None,
    mermaid_graph: str | None = None,
    mermaid_diagram: str | None = None,
    agent_design: str | None = None,
    tool_index: Any | None = None,
    runtime_overrides: Any | None = None,
    tool_registry: Any | None = None,
    model_adapter: Any | None = None,
    max_steps: int | None = None,
    trace_sink: Any | None = None,
    prompt_cache: bool | None = None,
) -> Any:
    """Run an agent workflow from generated artifacts and a user prompt.

    This API returns the final workflow result. Detailed execution state is
    available from `dynamic_agent_runner.executor.execute_workflow`.
    """

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
    result = execute_workflow(
        workflow,
        prompt=prompt,
        tool_registry=tool_registry,
        model_adapter=model_adapter,
        max_steps=max_steps,
        trace_sink=trace_sink,
        prompt_cache=prompt_cache,
    )
    return result.final_result
