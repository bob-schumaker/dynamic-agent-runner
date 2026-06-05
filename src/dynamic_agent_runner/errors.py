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


class LocalModelError(ModelExecutionError):
    """Base exception for local-model preparation and identity failures."""


class LocalModelResolutionError(LocalModelError):
    """Raised when a local model asset cannot be resolved."""


class LocalModelOfflinePolicyError(LocalModelResolutionError):
    """Raised when local-model resolution is blocked by offline policy."""


class LocalModelIdentityMismatchError(LocalModelError):
    """Raised when the resolved or observed model identity does not match."""


class WorkflowExecutionError(DynamicAgentRunnerError):
    """Raised when workflow execution cannot complete successfully."""
