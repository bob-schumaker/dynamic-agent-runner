"""Tests for host-owned embedding capability execution."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import pytest

from dynamic_agent_runner.workflow_host.capabilities import (
    CapabilityContract,
    CapabilityRequirement,
    CapabilityRequirements,
)
from dynamic_agent_runner.workflow_host.embedding_execution import (
    EmbeddingBatchLimits,
    EmbeddingExecutionBindingError,
    EmbeddingExecutionService,
    EmbeddingProviderCatalog,
    EmbeddingTextItem,
    EmbeddingVector,
    LocalEmbeddingAdapterProvider,
    derive_embedding_execution_binding,
)
from dynamic_agent_runner.workflow_host.model_execution_binding import (
    ModelExecutionBinding,
)


_EMBEDDING_CAPABILITY_ID = "embedding.execute.v1"


def _contract() -> CapabilityContract:
    return CapabilityContract(
        _EMBEDDING_CAPABILITY_ID,
        "1",
        "a" * 64,
        ("deterministic",),
    )


def _requirements(*, include_embedding: bool = True) -> CapabilityRequirements:
    requirements = ()
    if include_embedding:
        requirements = (
            CapabilityRequirement(
                _EMBEDDING_CAPABILITY_ID,
                "1",
                "a" * 64,
                ("deterministic",),
            ),
        )
    return CapabilityRequirements(requirements, {})


def _model_binding() -> ModelExecutionBinding:
    return ModelExecutionBinding(
        logical_model_id="locked-embedding-model",
        runner_contract_id="llama-cpp-v1",
        runner_contract_version="1",
        loader_profile_contract_id="llama-cpp-embedding-v1",
        loader_profile_contract_version="1",
        material_lock_digest="b" * 64,
        capability_requirements_digest="c" * 64,
        runner_capability_id="model.execution.llama-cpp.v1",
        runner_capability_version="1",
        runner_capability_digest="d" * 64,
    )


def _limits() -> EmbeddingBatchLimits:
    return EmbeddingBatchLimits(
        max_items=2,
        max_item_utf8_bytes=16,
        max_total_utf8_bytes=24,
        max_vector_dimension=3,
        max_total_vectors=4,
    )


@dataclass
class _FakeProvider:
    contract: CapabilityContract
    response: tuple[EmbeddingVector, ...]
    provider_id: str = "receiver-private-provider"
    deterministic: bool = True
    calls: list[tuple[EmbeddingTextItem, ...]] = field(default_factory=list)

    @property
    def model_binding(self) -> ModelExecutionBinding:
        return _model_binding()

    def embed(
        self,
        *,
        binding: object,
        items: tuple[EmbeddingTextItem, ...],
    ) -> tuple[EmbeddingVector, ...]:
        self.calls.append(items)
        return self.response


def _binding():
    return derive_embedding_execution_binding(
        model_binding=_model_binding(), requirements=_requirements()
    )


def _service(provider: _FakeProvider) -> EmbeddingExecutionService:
    return EmbeddingExecutionService(
        providers=EmbeddingProviderCatalog((provider,)), host_limits=_limits()
    )


def test_embedding_binding_requires_the_exact_deterministic_contract() -> None:
    binding = _binding()

    assert binding.material_lock_digest == "b" * 64
    assert binding.capability_contract_digest == "a" * 64
    with pytest.raises(EmbeddingExecutionBindingError, match="unavailable"):
        derive_embedding_execution_binding(
            model_binding=_model_binding(),
            requirements=_requirements(include_embedding=False),
        )


def test_embedding_executes_only_against_selected_exact_provider() -> None:
    provider = _FakeProvider(
        _contract(),
        (
            EmbeddingVector("chunk-1", (0.25, 0.75)),
            EmbeddingVector("chunk-2", (0.5, 0.5)),
        ),
    )

    vectors = _service(provider).execute(
        binding=_binding(),
        selected_provider_ids=(provider.provider_id,),
        package_limits=_limits(),
        items=(
            EmbeddingTextItem("chunk-1", "alpha"),
            EmbeddingTextItem("chunk-2", "beta"),
        ),
    )

    assert vectors == provider.response
    assert provider.calls == [
        (EmbeddingTextItem("chunk-1", "alpha"), EmbeddingTextItem("chunk-2", "beta"))
    ]


@pytest.mark.parametrize(
    "changes",
    (
        {"material_lock_digest": "e" * 64},
        {"runner_contract_id": "other-runner-v1"},
    ),
)
def test_embedding_rejects_provider_with_wrong_model_binding_before_entry(
    changes: dict[str, str],
) -> None:
    @dataclass
    class IncompatibleProvider(_FakeProvider):
        @property
        def model_binding(self) -> ModelExecutionBinding:
            return replace(_model_binding(), **changes)

    provider = IncompatibleProvider(
        _contract(), (EmbeddingVector("chunk-1", (0.25, 0.75)),)
    )

    with pytest.raises(EmbeddingExecutionBindingError, match="unavailable"):
        _service(provider).execute(
            binding=_binding(),
            selected_provider_ids=(provider.provider_id,),
            package_limits=_limits(),
            items=(EmbeddingTextItem("chunk-1", "alpha"),),
        )
    assert provider.calls == []


def test_embedding_catalog_rejects_provider_without_exact_model_binding() -> None:
    class MalformedProvider:
        provider_id = "receiver-private-provider"
        contract = _contract()
        deterministic = True

        def embed(self, **_: object) -> tuple[EmbeddingVector, ...]:
            raise AssertionError("malformed provider must not be called")

    with pytest.raises(EmbeddingExecutionBindingError, match="unavailable"):
        EmbeddingProviderCatalog((MalformedProvider(),))


def test_local_adapter_is_only_a_receiver_owned_provider_bridge() -> None:
    from dynamic_agent_runner.local_models import (
        EmbeddingBatchResult,
        EmbeddingVectorItem,
    )

    class Adapter:
        def __init__(self) -> None:
            self.calls: list[object] = []

        def embed(self, items: object) -> object:
            self.calls.append(items)
            return EmbeddingBatchResult(
                model="receiver-owned-model",
                items=(EmbeddingVectorItem(id="chunk-1", vector=(0.25, 0.75)),),
            )

    adapter = Adapter()
    provider = LocalEmbeddingAdapterProvider(
        "receiver-private-provider", _contract(), adapter, _model_binding()
    )

    result = _service(provider).execute(
        binding=_binding(),
        selected_provider_ids=(provider.provider_id,),
        package_limits=_limits(),
        items=(EmbeddingTextItem("chunk-1", "alpha"),),
    )

    assert result == (EmbeddingVector("chunk-1", (0.25, 0.75)),)
    assert adapter.calls[0][0].id == "chunk-1"
    assert adapter.calls[0][0].text == "alpha"


@pytest.mark.parametrize(
    "provider,selected_provider_ids",
    [
        (
            _FakeProvider(_contract(), (), deterministic=False),
            ("receiver-private-provider",),
        ),
        (_FakeProvider(_contract(), ()), ("changed-provider",)),
        (
            _FakeProvider(
                CapabilityContract(
                    _EMBEDDING_CAPABILITY_ID, "1", "e" * 64, ("deterministic",)
                ),
                (),
            ),
            ("receiver-private-provider",),
        ),
    ],
)
def test_embedding_rejects_unavailable_changed_or_nondeterministic_provider(
    provider: _FakeProvider, selected_provider_ids: tuple[str, ...]
) -> None:
    with pytest.raises(EmbeddingExecutionBindingError, match="unavailable"):
        _service(provider).execute(
            binding=_binding(),
            selected_provider_ids=selected_provider_ids,
            package_limits=_limits(),
            items=(EmbeddingTextItem("chunk-1", "alpha"),),
        )
    assert provider.calls == []


@pytest.mark.parametrize(
    "items,package_limits",
    [
        ((), _limits()),
        ((EmbeddingTextItem("chunk-1", "x" * 17),), _limits()),
        (
            (
                EmbeddingTextItem("chunk-1", "alpha"),
                EmbeddingTextItem("chunk-2", "beta"),
            ),
            EmbeddingBatchLimits(1, 16, 24, 3, 4),
        ),
        (
            (
                EmbeddingTextItem("chunk-1", "alpha"),
                EmbeddingTextItem("chunk-2", "beta"),
            ),
            EmbeddingBatchLimits(2, 16, 8, 3, 4),
        ),
        (
            (EmbeddingTextItem("chunk-1", "alpha"),),
            EmbeddingBatchLimits(3, 16, 24, 3, 4),
        ),
        (
            (
                EmbeddingTextItem("chunk-1", "alpha"),
                EmbeddingTextItem("chunk-1", "beta"),
            ),
            _limits(),
        ),
    ],
)
def test_embedding_rejects_invalid_or_over_limit_batches_before_provider_execution(
    items: tuple[EmbeddingTextItem, ...], package_limits: EmbeddingBatchLimits
) -> None:
    provider = _FakeProvider(_contract(), ())

    with pytest.raises(EmbeddingExecutionBindingError, match="batch"):
        _service(provider).execute(
            binding=_binding(),
            selected_provider_ids=(provider.provider_id,),
            package_limits=package_limits,
            items=items,
        )
    assert provider.calls == []


@pytest.mark.parametrize(
    "response",
    [
        (EmbeddingVector("chunk-2", (0.25, 0.75)),),
        (
            EmbeddingVector("chunk-1", (0.25, 0.75)),
            EmbeddingVector("chunk-1", (0.5, 0.5)),
        ),
        (EmbeddingVector("chunk-1", (float("nan"), 0.75)),),
        (EmbeddingVector("chunk-1", (0.25, 0.75, 0.5, 0.125)),),
        (EmbeddingVector("chunk-1", (0.25,)), EmbeddingVector("chunk-2", (0.5, 0.5))),
    ],
)
def test_embedding_rejects_malformed_vectors_after_one_provider_call(
    response: tuple[EmbeddingVector, ...],
) -> None:
    provider = _FakeProvider(_contract(), response)

    with pytest.raises(EmbeddingExecutionBindingError, match="result"):
        _service(provider).execute(
            binding=_binding(),
            selected_provider_ids=(provider.provider_id,),
            package_limits=_limits(),
            items=(
                EmbeddingTextItem("chunk-1", "alpha"),
                EmbeddingTextItem("chunk-2", "beta"),
            ),
        )
    assert len(provider.calls) == 1
