"""Locked-inference binding through the generic sealed-artifact callback seam."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from dynamic_agent_runner.workflow_host.locked_inference import (
    InferenceLimits,
    InferenceRole,
    InferenceRoles,
    SealedAsset,
)
from dynamic_agent_runner.workflow_host.locked_inference_sealed_artifact_callback import (
    LockedInferenceSealedArtifactCallbackError,
    LockedInferenceSealedArtifactCallbackResolver,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactCallback,
    SealedArtifactLimits,
    SealedArtifactRunnerDescriptor,
)


ASSET_DIGEST = "a" * 64


@dataclass
class _Execution:
    calls: list[tuple[str, bytes]] = field(default_factory=list)

    def generate(self, role: str, request: bytes) -> bytes:
        self.calls.append((role, request))
        return b'{"result":"ok"}'


def _roles(*, authorized_asset_digest: str = ASSET_DIGEST) -> InferenceRoles:
    asset = SealedAsset("assets/instruction.txt", "b" * 64)
    schema = SealedAsset("schemas/request.json", "c" * 64)
    return InferenceRoles(
        (
            InferenceRole(
                role="generate",
                material_role="model",
                capability_id="model.generate.v1",
                instruction_asset=asset,
                request_schema_asset=schema,
                response_schema_asset=SealedAsset("schemas/response.json", "d" * 64),
                authorized_asset_digests=(authorized_asset_digest,),
                limits=InferenceLimits(1, 100, 100, 100, 1),
            ),
        )
    )


def _callback(
    *, name: str = "generate", requirement: str = "model.generate.v1"
) -> SealedArtifactCallback:
    return SealedArtifactCallback(
        name=name,
        requirement=requirement,
        child_contract_digest="e" * 64,
        max_calls=1,
        max_concurrency=1,
        max_request_bytes=100,
        max_response_bytes=100,
        max_total_request_bytes=100,
        max_total_response_bytes=100,
        timeout_milliseconds=100,
    )


def _descriptor(callback: SealedArtifactCallback) -> SealedArtifactRunnerDescriptor:
    return SealedArtifactRunnerDescriptor(
        digest="f" * 64,
        asset_path="assets/runner.py",
        asset_digest=ASSET_DIGEST,
        capability_requirements_digest="0" * 64,
        profile_digest="1" * 64,
        inputs=(),
        outputs=(),
        limits=SealedArtifactLimits(1, 1, 1000, 1, 100),
        schema_assets=(),
        child_contract_digests=(callback.child_contract_digest,),
        callbacks=(callback,),
        output_roles=(),
    )


@pytest.mark.parametrize(
    ("callback", "roles"),
    (
        (_callback(name="other"), _roles()),
        (_callback(requirement="embedding.execute.v1"), _roles()),
        (_callback(), _roles(authorized_asset_digest="9" * 64)),
    ),
)
def test_resolver_rejects_unbound_role_requirement_or_asset(
    callback: SealedArtifactCallback, roles: InferenceRoles
) -> None:
    execution = _Execution()
    resolver = LockedInferenceSealedArtifactCallbackResolver(execution=execution)

    with pytest.raises(
        LockedInferenceSealedArtifactCallbackError,
        match="locked inference callback is unavailable",
    ):
        resolver.resolve(_descriptor(callback), SimpleNamespace(inference_roles=roles))

    assert execution.calls == []


def test_resolver_revalidates_and_delegates_only_the_bound_role() -> None:
    execution = _Execution()
    callback = _callback()
    provider = LockedInferenceSealedArtifactCallbackResolver(
        execution=execution
    ).resolve(_descriptor(callback), SimpleNamespace(inference_roles=_roles()))

    provider.revalidate(callback)

    assert provider.invoke("generate", b'{"request":"value"}') == b'{"result":"ok"}'
    assert execution.calls == [("generate", b'{"request":"value"}')]

    with pytest.raises(
        LockedInferenceSealedArtifactCallbackError,
        match="locked inference callback is unavailable",
    ):
        provider.revalidate(_callback(name="other"))
    with pytest.raises(
        LockedInferenceSealedArtifactCallbackError,
        match="locked inference callback is unavailable",
    ):
        provider.invoke("other", b"ignored")

    assert execution.calls == [("generate", b'{"request":"value"}')]
