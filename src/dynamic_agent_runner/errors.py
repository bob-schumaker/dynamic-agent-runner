"""Project-specific exceptions for dynamic-agent-runner."""


class DynamicAgentRunnerError(Exception):
    """Base exception for all dynamic-agent-runner failures."""


class ArtifactLoadError(DynamicAgentRunnerError):
    """Raised when workflow artifacts cannot be loaded or parsed."""


class WorkflowValidationError(DynamicAgentRunnerError):
    """Raised when workflow artifacts are inconsistent or unsupported."""


class ToolRegistryError(DynamicAgentRunnerError):
    """Raised when tool lookup, validation, or invocation fails."""


class ModelExecutionError(DynamicAgentRunnerError):
    """Raised when model execution fails."""


class WorkflowExecutionError(DynamicAgentRunnerError):
    """Raised when workflow execution cannot complete successfully."""
