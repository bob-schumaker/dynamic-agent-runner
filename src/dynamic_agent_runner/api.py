"""Public API for loading and running dynamic-agent workflow artifacts."""

from __future__ import annotations

from typing import Any

from dynamic_agent_runner.artifacts import load_agent_workflow_artifacts
from dynamic_agent_runner.models import LoadedAgentWorkflow


def load_agent_workflow(
    *,
    runtime_manifest: Any | None = None,
    definition_yaml: Any | None = None,
    mermaid_graph: str | None = None,
    mermaid_diagram: str | None = None,
    agent_design: str | None = None,
    tool_index: Any | None = None,
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
    return load_agent_workflow_artifacts(
        runtime_manifest=runtime_input,
        mermaid_graph=graph_input,
        agent_design=agent_design,
        tool_index=tool_index,
    )


def run_agent_workflow(*args: Any, **kwargs: Any) -> Any:
    """Run an agent workflow from generated artifacts and a user prompt.

    The concrete implementation will be added after validation, registry, OpenAI
    adapter, and executor slices are implemented.
    """

    raise NotImplementedError("workflow execution is not implemented yet")
