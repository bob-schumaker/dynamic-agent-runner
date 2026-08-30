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


class GuardrailExecutionError(DynamicAgentRunnerError):
    """Raised when guardrail execution blocks or fails a workflow."""


class AgentSessionError(DynamicAgentRunnerError):
    """Raised when persistent agent session state is invalid or unavailable."""


class HuggingFaceModelSearchError(DynamicAgentRunnerError):
    """Raised when Hugging Face model discovery fails."""


class LocalModelError(ModelExecutionError):
    """Base exception for local-model preparation and identity failures."""


class LocalModelResolutionError(LocalModelError):
    """Raised when a local model asset cannot be resolved."""


class LocalModelOfflinePolicyError(LocalModelResolutionError):
    """Raised when local-model resolution is blocked by offline policy."""


class LocalModelIdentityMismatchError(LocalModelError):
    """Raised when the resolved or observed model identity does not match."""


class EmbeddingError(LocalModelError):
    """Base exception for standalone local embedding failures."""


class EmbeddingInputError(EmbeddingError):
    """Raised when a caller-supplied embedding batch is invalid."""


class EmbeddingResultError(EmbeddingError):
    """Raised when an embedding backend returns an invalid batch."""


class EmbeddingExecutionError(EmbeddingError):
    """Raised when standalone embedding execution cannot complete."""


class LlamaCppMemoryFitProfileError(LocalModelError):
    """Raised when strict llama.cpp memory-fit profiling cannot continue."""


class LocalModelEndpointError(LocalModelError):
    """Base exception for local endpoint execution failures."""


class LocalModelEndpointConnectivityError(LocalModelEndpointError):
    """Raised when a local endpoint cannot be reached or is not ready."""


class LocalModelEndpointProtocolError(LocalModelEndpointError):
    """Raised when a local endpoint responds in an unsupported way."""


class WorkflowExecutionError(DynamicAgentRunnerError):
    """Raised when workflow execution cannot complete successfully."""
