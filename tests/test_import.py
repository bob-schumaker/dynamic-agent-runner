"""Smoke tests for the initial package scaffold."""

import dynamic_agent_runner


def test_package_imports() -> None:
    """The package exposes the reserved public API names."""

    assert dynamic_agent_runner.load_agent_workflow is not None
    assert dynamic_agent_runner.load_agent_package_workflow is not None
    assert dynamic_agent_runner.run_agent_workflow is not None
    assert dynamic_agent_runner.run_agent_workflow_async is not None
    assert dynamic_agent_runner.execute_workflow_async is not None
    assert dynamic_agent_runner.WorkflowExecutionContext is not None
    assert (
        dynamic_agent_runner.RunContext is dynamic_agent_runner.WorkflowExecutionContext
    )
    assert dynamic_agent_runner.ModelCapabilities is not None
    assert dynamic_agent_runner.ToolExposure is not None
    assert dynamic_agent_runner.ToolPolicy is not None
    assert dynamic_agent_runner.ToolType is not None
    assert dynamic_agent_runner.RegisteredLifecycleHook is not None
    assert dynamic_agent_runner.invoke_lifecycle_hook_async is not None
    assert dynamic_agent_runner.DynamicAgentRunnerError is not None
    assert dynamic_agent_runner.OpenAIProviderConfig is not None
    assert dynamic_agent_runner.create_default_openai_provider is not None
    assert dynamic_agent_runner.create_default_async_openai_provider is not None
    assert dynamic_agent_runner.LocalOpenAIEndpointConfig is not None
    assert dynamic_agent_runner.create_local_openai_adapter is not None
    assert dynamic_agent_runner.create_local_async_openai_adapter is not None
    assert dynamic_agent_runner.search_hugging_face_models is not None
    assert dynamic_agent_runner.HuggingFaceModelSearchResult is not None
    assert dynamic_agent_runner.HuggingFaceModelSearchError is not None
