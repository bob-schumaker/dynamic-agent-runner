"""Narrow host-owned invocation surface for one sealed callback asset."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from dynamic_agent_runner.workflow_host.locked_inference_asset_abi import (
    LockedInferenceAssetAbi,
)
from dynamic_agent_runner.workflow_host.sandbox_result_location import (
    ResultLocation,
    SealedResultArtifact,
)


class LockedInferenceAssetRuntimeError(ValueError):
    """Raised without exposing sealed asset, input, or provider contents."""


class LockedInferenceAssetRuntime:
    def __init__(
        self,
        *,
        abi: LockedInferenceAssetAbi,
        asset_digest: str,
        generate: Callable[[str, bytes], bytes],
    ) -> None:
        self._abi = abi
        self.asset_digest = asset_digest
        self._generate = generate

    def run(
        self,
        *,
        role: str,
        sealed_inputs: Mapping[str, bytes],
        asset: Callable[
            [Callable[[str, bytes], bytes], Mapping[str, bytes], ResultLocation], None
        ],
    ) -> tuple[SealedResultArtifact, ...]:
        if (
            self.asset_digest != self._abi.asset_digest
            or role not in self._abi.authorized_roles
            or set(sealed_inputs) != set(self._abi.sealed_inputs)
            or any(not isinstance(value, bytes) for value in sealed_inputs.values())
        ):
            raise LockedInferenceAssetRuntimeError(
                "locked inference asset is unavailable"
            )

        def callback(requested_role: str, value: bytes) -> bytes:
            if requested_role != role:
                raise LockedInferenceAssetRuntimeError(
                    "locked inference role is unavailable"
                )
            return self._generate(requested_role, value)

        location = self._abi.create_result_location()
        try:
            asset(callback, dict(sealed_inputs), location)
            return location.seal()
        except LockedInferenceAssetRuntimeError:
            raise
        except Exception as error:
            raise LockedInferenceAssetRuntimeError(
                "locked inference asset failed"
            ) from error
