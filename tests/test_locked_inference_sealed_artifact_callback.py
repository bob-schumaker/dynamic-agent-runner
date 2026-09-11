"""Locked-inference binding through the generic sealed-artifact callback seam."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dynamic_agent_runner.workflow_host.locked_inference import (
    InferenceLimits,
    InferenceRole,
    InferenceRoles,
    LockedInferenceBinding,
    SealedAsset,
)
from dynamic_agent_runner.workflow_host.locked_inference_sealed_artifact_callback import (
    LockedInferenceExecutionFactory,
    LockedInferenceSealedArtifactCallbackError,
    LockedInferenceSealedArtifactCallbackResolver,
)
from dynamic_agent_runner.workflow_host.locked_inference_execution import (
    LockedInferenceExecutionError,
    LockedInferenceHostLimits,
)
from dynamic_agent_runner.workflow_host.locked_inference_provider_registry import (
    LockedInferenceProviderBinding,
    LockedInferenceProviderRegistry,
)
from dynamic_agent_runner.workflow_host.capabilities import (
    CapabilityCatalog,
    CapabilityContract,
    CapabilityProvider,
    CapabilityRequirement,
    CapabilityRequirements,
    ProviderAvailability,
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


@dataclass
class _Provider:
    calls: list[dict[str, object]] = field(default_factory=list)

    def generate(self, **kwargs: object) -> bytes:
        self.calls.append(kwargs)
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


def test_factory_rereads_revision_assets_and_creates_fresh_service(
    tmp_path: Path,
) -> None:
    instruction = b"sealed instruction"
    schema = json.dumps(
        {
            "type": "object",
            "properties": {"result": {"type": "string", "max_string_bytes": 64}},
            "required": ["result"],
            "max_depth": 2,
            "max_items": 1,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    (tmp_path / "assets").mkdir()
    (tmp_path / "schemas").mkdir()
    (tmp_path / "assets" / "instruction.txt").write_bytes(instruction)
    (tmp_path / "schemas" / "request.json").write_bytes(schema)
    (tmp_path / "schemas" / "response.json").write_bytes(schema)
    roles = InferenceRoles(
        (
            InferenceRole(
                role="generate",
                material_role="model",
                capability_id="model.generate.v1",
                instruction_asset=_asset("assets/instruction.txt", instruction),
                request_schema_asset=_asset("schemas/request.json", schema),
                response_schema_asset=_asset("schemas/response.json", schema),
                authorized_asset_digests=(ASSET_DIGEST,),
                limits=InferenceLimits(1, 100, 100, 100, 1),
            ),
        )
    )
    contract = CapabilityContract("model.generate.v1", "1", "2" * 64, ("structured",))
    provider = _Provider()
    available = True
    catalog = CapabilityCatalog(
        (contract,),
        (CapabilityProvider("generate-provider", contract, conformance_passed=True),),
        availability_provider=lambda _provider: (
            ProviderAvailability.AVAILABLE
            if available
            else ProviderAvailability.DISABLED
        ),
    )
    factory = LockedInferenceExecutionFactory(
        capability_catalog=catalog,
        provider_registry=LockedInferenceProviderRegistry(
            (LockedInferenceProviderBinding("generate-provider", contract, provider),)
        ),
        host_limits=LockedInferenceHostLimits(2, 200, 200, 200, 2),
    )
    policy = SimpleNamespace(
        inference_roles=roles,
        locked_inference_bindings=(
            LockedInferenceBinding(
                "generate",
                "model",
                object(),
                contract.contract_version,
                contract.contract_digest,
            ),
        ),
        capability_requirements=CapabilityRequirements(
            (
                CapabilityRequirement(
                    "model.generate.v1", "1", "2" * 64, ("structured",)
                ),
            )
        ),
        selected_capability_provider_ids=("generate-provider",),
    )
    revision = SimpleNamespace(package_root=tmp_path)

    first = factory.create(policy=policy, revision=revision)
    assert first.generate("generate", b'{"result":"value"}') == b'{"result":"ok"}'
    with pytest.raises(LockedInferenceExecutionError, match="quota"):
        first.generate("generate", b'{"result":"value"}')

    second = factory.create(policy=policy, revision=revision)
    assert second.generate("generate", b'{"result":"value"}') == b'{"result":"ok"}'
    assert [call["instruction_bytes"] for call in provider.calls] == [
        instruction,
        instruction,
    ]

    available = False
    with pytest.raises(LockedInferenceExecutionError, match="provider is unavailable"):
        second.generate("generate", b'{"result":"value"}')
    assert len(provider.calls) == 2


def test_factory_rejects_a_requirement_that_no_longer_matches_the_binding(
    tmp_path: Path,
) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "schemas").mkdir()
    instruction = b"instruction"
    (tmp_path / "assets" / "instruction.txt").write_bytes(instruction)
    schema = b'{"max_depth":1,"max_items":1,"max_string_bytes":1,"type":"null"}'
    (tmp_path / "schemas" / "request.json").write_bytes(schema)
    (tmp_path / "schemas" / "response.json").write_bytes(schema)
    roles = InferenceRoles(
        (
            InferenceRole(
                role="generate",
                material_role="model",
                capability_id="model.generate.v1",
                instruction_asset=_asset("assets/instruction.txt", instruction),
                request_schema_asset=_asset("schemas/request.json", schema),
                response_schema_asset=_asset("schemas/response.json", schema),
                authorized_asset_digests=(ASSET_DIGEST,),
                limits=InferenceLimits(1, 100, 100, 100, 1),
            ),
        )
    )
    contract = CapabilityContract("model.generate.v1", "1", "2" * 64, ("structured",))
    factory = LockedInferenceExecutionFactory(
        capability_catalog=CapabilityCatalog(
            (contract,),
            (
                CapabilityProvider(
                    "generate-provider", contract, conformance_passed=True
                ),
            ),
        ),
        provider_registry=LockedInferenceProviderRegistry(
            (
                LockedInferenceProviderBinding(
                    "generate-provider", contract, _Provider()
                ),
            )
        ),
        host_limits=LockedInferenceHostLimits(1, 100, 100, 100, 1),
    )
    policy = SimpleNamespace(
        inference_roles=roles,
        locked_inference_bindings=(
            LockedInferenceBinding("generate", "model", object(), "1", "2" * 64),
        ),
        capability_requirements=CapabilityRequirements(
            (
                CapabilityRequirement(
                    "model.generate.v1", "1", "3" * 64, ("structured",)
                ),
            )
        ),
        selected_capability_provider_ids=("generate-provider",),
    )

    with pytest.raises(
        LockedInferenceSealedArtifactCallbackError,
        match="locked inference callback is unavailable",
    ):
        factory.create(policy=policy, revision=SimpleNamespace(package_root=tmp_path))


def _asset(path: str, value: bytes) -> SealedAsset:
    return SealedAsset(path, hashlib.sha256(value).hexdigest())
