"""Smoke tests for the initial package scaffold."""

import dynamic_agent_runner


def test_package_imports() -> None:
    """The package exposes the reserved public API names."""

    assert dynamic_agent_runner.load_agent_workflow is not None
    assert dynamic_agent_runner.run_agent_workflow is not None
    assert dynamic_agent_runner.DynamicAgentRunnerError is not None
