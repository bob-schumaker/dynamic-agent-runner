"""Initial public API placeholders for dynamic-agent-runner."""

from __future__ import annotations

from typing import Any


def load_agent_workflow(*args: Any, **kwargs: Any) -> Any:
    """Load and validate agent workflow artifacts.

    The concrete implementation will be added in the artifact loading and
    validation slices. This placeholder reserves the public API surface while
    keeping the package importable during the scaffold slice.
    """

    raise NotImplementedError("workflow loading is not implemented yet")


def run_agent_workflow(*args: Any, **kwargs: Any) -> Any:
    """Run an agent workflow from generated artifacts and a user prompt.

    The concrete implementation will be added after artifact loading,
    validation, registry, OpenAI adapter, and executor slices are implemented.
    """

    raise NotImplementedError("workflow execution is not implemented yet")
