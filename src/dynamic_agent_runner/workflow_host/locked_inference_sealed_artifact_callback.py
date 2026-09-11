"""Bind locked inference roles to the generic sealed-artifact callback seam."""

from __future__ import annotations

from collections.abc import Mapping

from dynamic_agent_runner.workflow_host.locked_inference import (
    InferenceRoles,
    LockedInferenceError,
)
from dynamic_agent_runner.workflow_host.locked_inference_execution import (
    LockedInferenceExecutionService,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactCallback,
    SealedArtifactCallbackProvider,
    SealedArtifactRunnerDescriptor,
)


class LockedInferenceSealedArtifactCallbackError(ValueError):
    """Raised without exposing policy, asset, or provider details."""


class LockedInferenceSealedArtifactCallbackResolver:
    """Resolve only descriptor callbacks authorized by exact inference roles."""

    def __init__(self, *, execution: LockedInferenceExecutionService) -> None:
        if not callable(getattr(execution, "generate", None)):
            raise LockedInferenceSealedArtifactCallbackError(
                "locked inference callback is unavailable"
            )
        self._execution = execution

    def resolve(
        self,
        descriptor: SealedArtifactRunnerDescriptor,
        policy: object,
        revision: object,
    ) -> SealedArtifactCallbackProvider:
        del revision
        roles = getattr(policy, "inference_roles", None)
        if not isinstance(roles, InferenceRoles):
            raise LockedInferenceSealedArtifactCallbackError(
                "locked inference callback is unavailable"
            )
        callbacks = {callback.name: callback for callback in descriptor.callbacks}
        try:
            for callback in callbacks.values():
                role = roles.for_role(callback.name)
                if (
                    callback.requirement != role.capability_id
                    or descriptor.asset_digest not in role.authorized_asset_digests
                ):
                    raise LockedInferenceError("inference role is unavailable")
        except LockedInferenceError as error:
            raise LockedInferenceSealedArtifactCallbackError(
                "locked inference callback is unavailable"
            ) from error
        return _LockedInferenceCallbackProvider(self._execution, callbacks)


class _LockedInferenceCallbackProvider:
    def __init__(
        self,
        execution: LockedInferenceExecutionService,
        callbacks: Mapping[str, SealedArtifactCallback],
    ) -> None:
        self._execution = execution
        self._callbacks = dict(callbacks)

    def revalidate(self, callback: SealedArtifactCallback) -> None:
        if self._callbacks.get(callback.name) != callback:
            raise LockedInferenceSealedArtifactCallbackError(
                "locked inference callback is unavailable"
            )

    def invoke(self, name: str, request: bytes) -> bytes:
        if name not in self._callbacks or not isinstance(request, bytes):
            raise LockedInferenceSealedArtifactCallbackError(
                "locked inference callback is unavailable"
            )
        try:
            return self._execution.generate(name, request)
        except Exception as error:  # Provider failures remain private to the asset.
            raise LockedInferenceSealedArtifactCallbackError(
                "locked inference callback is unavailable"
            ) from error
