"""Tests for generic sealed workflow model-material admission."""

from __future__ import annotations

from hashlib import sha256

import pytest

from dynamic_agent_runner.workflow_host.capabilities import (
    CapabilityRequirement,
    CapabilityRequirements,
)
from dynamic_agent_runner.workflow_host.model_material_admission import (
    HostMaterialPolicy,
    ModelMaterialAdmission,
    ModelMaterialAdmissionError,
    ModelPreparationProvider,
)
from dynamic_agent_runner.workflow_host.model_materials import (
    MaterialContract,
    parse_model_dependency_lock,
    transformation_digest,
)


SOURCE = b"locked source model"
OUTPUT = b"prepared output model"
PREPARATION_ID = "model.prepare.test.v1"
PREPARATION_CONTRACT = MaterialContract(PREPARATION_ID, "1")


class _Cache:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str, str | None], bytes] = {}
        self.lookups = 0
        self.promotions = 0

    def load(
        self, *, lock_digest: str, role: str, transformation_digest: str | None
    ) -> bytes | None:
        self.lookups += 1
        return self.values.get((lock_digest, role, transformation_digest))

    def promote(
        self,
        *,
        lock_digest: str,
        role: str,
        transformation_digest: str | None,
        content: bytes,
    ) -> None:
        self.promotions += 1
        self.values[(lock_digest, role, transformation_digest)] = content


class _Transport:
    def __init__(self, content: bytes = SOURCE) -> None:
        self.content = content
        self.calls: list[object] = []

    def fetch(self, source: object) -> bytes:
        self.calls.append(source)
        return self.content


def _lock(*, output: bytes = OUTPUT):
    operation = {
        "capability_id": PREPARATION_ID,
        "contract_version": "1",
        "contract_digest": "c" * 64,
        "inputs": ["base_f16"],
        "output": {
            "role": "base_model",
            "group": "base",
            "filename": "model.gguf",
            "sha256": sha256(output).hexdigest(),
        },
    }
    operation["transformation_digest"] = transformation_digest(operation)
    return parse_model_dependency_lock(
        {
            "format_version": 1,
            "logical_model_id": "example-model",
            "runner_contract": {"id": "llama-cpp-v1", "version": "1"},
            "loader_profile_contract": {"id": "llama-cpp-text-v1", "version": "1"},
            "sources": [
                {
                    "role": "base_f16",
                    "group": "base",
                    "source_type": "huggingface_file",
                    "repository": "example-org/example-model",
                    "revision": "a" * 40,
                    "filename": "model-f16.gguf",
                    "sha256": sha256(SOURCE).hexdigest(),
                }
            ],
            "preparation": [operation],
        }
    )


def _requirements() -> CapabilityRequirements:
    return CapabilityRequirements(
        (
            CapabilityRequirement("model.execution.test.v1", "1", "d" * 64, ()),
            CapabilityRequirement(PREPARATION_ID, "1", "c" * 64, ()),
        ),
        {"runner": "model.execution.test.v1"},
    )


def _provider(*, output: bytes = OUTPUT) -> ModelPreparationProvider:
    return ModelPreparationProvider(
        provider_id="private-preparer",
        contract=PREPARATION_CONTRACT,
        contract_digest="c" * 64,
        prepare=lambda _operation, inputs: (
            output if inputs["base_f16"] == SOURCE else b""
        ),
    )


def test_admission_reuses_a_verified_complete_cache_without_transport_or_prepare() -> (
    None
):
    lock = _lock()
    cache = _Cache()
    cache.promote(
        lock_digest=lock.digest,
        role="base_f16",
        transformation_digest=None,
        content=SOURCE,
    )
    cache.promote(
        lock_digest=lock.digest,
        role="base_model",
        transformation_digest=lock.preparation[0].transformation_digest,
        content=OUTPUT,
    )
    transport = _Transport()

    materials = ModelMaterialAdmission(
        cache=cache,
        transport=transport,
        providers=(_provider(),),
        selected_provider_ids=("private-preparer",),
        revalidate_selected=lambda _ids: True,
        policy=HostMaterialPolicy(allow_download=True, allow_preparation=True),
    ).materialize(lock=lock, requirements=_requirements())

    assert materials.artifacts == {"base_f16": SOURCE, "base_model": OUTPUT}
    assert transport.calls == []


def test_admission_downloads_exact_sources_then_promotes_verified_preparation() -> None:
    lock = _lock()
    cache = _Cache()
    transport = _Transport()
    calls: list[tuple[object, dict[str, bytes]]] = []
    provider = ModelPreparationProvider(
        provider_id="private-preparer",
        contract=PREPARATION_CONTRACT,
        contract_digest="c" * 64,
        prepare=lambda operation, inputs: calls.append((operation, inputs)) or OUTPUT,
    )

    materials = ModelMaterialAdmission(
        cache=cache,
        transport=transport,
        providers=(provider,),
        selected_provider_ids=("private-preparer",),
        revalidate_selected=lambda _ids: True,
        policy=HostMaterialPolicy(allow_download=True, allow_preparation=True),
    ).materialize(lock=lock, requirements=_requirements())

    assert materials.artifacts == {"base_f16": SOURCE, "base_model": OUTPUT}
    assert len(transport.calls) == 1
    assert calls == [(lock.preparation[0], {"base_f16": SOURCE})]
    assert cache.promotions == 2


def test_admission_rejects_unavailable_or_mismatched_provider_before_side_effects() -> (
    None
):
    lock = _lock()
    cache = _Cache()
    transport = _Transport()
    provider = _provider()

    with pytest.raises(ModelMaterialAdmissionError, match="material_unavailable"):
        ModelMaterialAdmission(
            cache=cache,
            transport=transport,
            providers=(provider,),
            selected_provider_ids=(),
            revalidate_selected=lambda _ids: True,
            policy=HostMaterialPolicy(allow_download=True, allow_preparation=True),
        ).materialize(lock=lock, requirements=_requirements())

    assert cache.lookups == 0
    assert transport.calls == []
    assert cache.promotions == 0


def test_admission_revalidates_before_download_or_preparation() -> None:
    lock = _lock()
    cache = _Cache()
    transport = _Transport()

    with pytest.raises(ModelMaterialAdmissionError, match="material_unavailable"):
        ModelMaterialAdmission(
            cache=cache,
            transport=transport,
            providers=(_provider(),),
            selected_provider_ids=("private-preparer",),
            revalidate_selected=lambda _ids: False,
            policy=HostMaterialPolicy(allow_download=True, allow_preparation=True),
        ).materialize(lock=lock, requirements=_requirements())

    assert cache.lookups == 0
    assert transport.calls == []
    assert cache.promotions == 0


def test_admission_rejects_bad_source_or_output_without_promoting_it() -> None:
    lock = _lock()
    source_cache = _Cache()
    bad_source_transport = _Transport(b"wrong source")

    with pytest.raises(ModelMaterialAdmissionError, match="material_integrity_failed"):
        ModelMaterialAdmission(
            cache=source_cache,
            transport=bad_source_transport,
            providers=(_provider(),),
            selected_provider_ids=("private-preparer",),
            revalidate_selected=lambda _ids: True,
            policy=HostMaterialPolicy(allow_download=True, allow_preparation=True),
        ).materialize(lock=lock, requirements=_requirements())

    output_cache = _Cache()
    with pytest.raises(ModelMaterialAdmissionError, match="material_integrity_failed"):
        ModelMaterialAdmission(
            cache=output_cache,
            transport=_Transport(),
            providers=(_provider(output=b"wrong output"),),
            selected_provider_ids=("private-preparer",),
            revalidate_selected=lambda _ids: True,
            policy=HostMaterialPolicy(allow_download=True, allow_preparation=True),
        ).materialize(lock=lock, requirements=_requirements())

    assert source_cache.promotions == 0
    assert output_cache.promotions == 1
