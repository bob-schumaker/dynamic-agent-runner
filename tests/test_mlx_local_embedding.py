"""RED contract for the sealed, direct generic MLX embedding adapter."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import pytest

from dynamic_agent_runner.errors import EmbeddingExecutionError
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptorAbi,
    ExecutionDescriptorValidatorRegistry,
    parse_execution_descriptor,
)
from dynamic_agent_runner.local_models import (
    EmbeddingBatchResult,
    EmbeddingInputItem,
    EmbeddingVectorItem,
)
from dynamic_agent_runner.mlx_local_embedding import (
    MLXPreparedEmbeddingArtifacts,
    MLXLocalEmbeddingConfig,
    create_mlx_local_embedding_adapter,
    create_mlx_local_embedding_async_adapter,
)
import dynamic_agent_runner.mlx_local_embedding as mlx_local_embedding


@dataclass
class _Backend:
    calls: list[
        tuple[tuple[EmbeddingInputItem, ...], MLXPreparedEmbeddingArtifacts]
    ] = field(default_factory=list)

    def embed(
        self,
        items: tuple[EmbeddingInputItem, ...],
        materials: MLXPreparedEmbeddingArtifacts,
    ) -> EmbeddingBatchResult:
        self.calls.append((items, materials))
        return EmbeddingBatchResult(
            model="test-embedding-model",
            items=(EmbeddingVectorItem(id="chunk-1", vector=(0.25,)),),
        )


def _materials() -> MLXPreparedEmbeddingArtifacts:
    descriptor = parse_execution_descriptor(
        {
            "format_version": 1,
            "architecture_abi": {
                "id": "test-embedding-abi",
                "version": "1",
                "contract_digest": "a" * 64,
            },
            "material_roles": ["tokenizer"],
            "abi_fields": {},
        }
    )
    return MLXPreparedEmbeddingArtifacts(
        execution_abi_id="test-embedding-abi",
        execution_abi_version="1",
        execution_abi_contract_digest="a" * 64,
        execution_descriptor_digest=descriptor.digest,
        material_lock_digest="c" * 64,
        execution_descriptor=descriptor,
    )


def _descriptor_validators() -> ExecutionDescriptorValidatorRegistry:
    class _Validator:
        identity = ExecutionDescriptorAbi("test-embedding-abi", "1", "a" * 64)

        def validate(self, _descriptor) -> None:
            return None

    return ExecutionDescriptorValidatorRegistry((_Validator(),))


def test_mlx_embedding_factories_are_lazy() -> None:
    calls: list[str] = []
    config = MLXLocalEmbeddingConfig(
        material_resolver=lambda: calls.append("material") or _materials(),
        descriptor_validators=_descriptor_validators(),
    )

    sync_adapter = create_mlx_local_embedding_adapter(
        config,
        dependency_loader=lambda: calls.append("dependency") or "0.32.2",
    )
    async_adapter = create_mlx_local_embedding_async_adapter(
        config,
        dependency_loader=lambda: calls.append("dependency") or "0.32.2",
    )

    assert sync_adapter is not None
    assert async_adapter is not None
    assert calls == []


def test_mlx_dependency_probe_uses_core_version_when_top_level_lacks_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    top_level = object()
    core = type("Core", (), {"__version__": "0.32.2"})()

    monkeypatch.setattr(
        mlx_local_embedding,
        "import_module",
        lambda name: top_level if name == "mlx" else core,
    )

    assert mlx_local_embedding._load_mlx_version() == "0.32.2"


def _adapter(
    *,
    backend: _Backend | None = None,
    material_resolver=None,
    platform_system=lambda: "Darwin",
    macos_version=lambda: (14, 0),
    machine=lambda: "arm64",
    dependency_loader=lambda: "0.32.2",
    descriptor_validators=None,
):
    return create_mlx_local_embedding_adapter(
        MLXLocalEmbeddingConfig(
            material_resolver=material_resolver or _materials,
            descriptor_validators=descriptor_validators or _descriptor_validators(),
        ),
        backend=backend,
        platform_system=platform_system,
        macos_version=macos_version,
        machine=machine,
        dependency_loader=dependency_loader,
    )


@pytest.mark.parametrize(
    "platform_system,macos_version,machine",
    (
        (lambda: "Linux", lambda: (14, 0), lambda: "arm64"),
        (lambda: "Darwin", lambda: (13, 6), lambda: "arm64"),
        (lambda: "Darwin", lambda: (14, 0), lambda: "x86_64"),
    ),
)
def test_mlx_embedding_rejects_ineligible_hosts_before_any_other_admission(
    platform_system, macos_version, machine
) -> None:
    calls: list[str] = []
    adapter = _adapter(
        material_resolver=lambda: calls.append("material") or _materials(),
        platform_system=platform_system,
        macos_version=macos_version,
        machine=machine,
        dependency_loader=lambda: calls.append("dependency") or "0.32.2",
    )

    with pytest.raises(EmbeddingExecutionError, match="unavailable"):
        adapter.embed((EmbeddingInputItem("chunk-1", "alpha"),))
    assert calls == []


@pytest.mark.parametrize("loaded", (None, "0.31.3"))
def test_mlx_embedding_rejects_missing_or_wrong_dependency_before_materials(
    loaded: str | None,
) -> None:
    calls: list[str] = []
    adapter = _adapter(
        material_resolver=lambda: calls.append("material") or _materials(),
        dependency_loader=lambda: calls.append("dependency") or loaded,
    )

    with pytest.raises(EmbeddingExecutionError, match="dependency"):
        adapter.embed((EmbeddingInputItem("chunk-1", "alpha"),))
    assert calls == ["dependency"]


@pytest.mark.parametrize("failure", (ImportError("no mlx"), RuntimeError("bad ABI")))
def test_mlx_embedding_redacts_dependency_load_failures_before_materials(
    failure: Exception,
) -> None:
    calls: list[str] = []

    def dependency_loader() -> str:
        calls.append("dependency")
        raise failure

    adapter = _adapter(
        material_resolver=lambda: calls.append("material") or _materials(),
        dependency_loader=dependency_loader,
    )

    with pytest.raises(EmbeddingExecutionError, match="dependency"):
        adapter.embed((EmbeddingInputItem("chunk-1", "alpha"),))
    assert calls == ["dependency"]


def test_mlx_embedding_admits_materials_after_dependency_and_reaches_backend() -> None:
    calls: list[str] = []
    backend = _Backend()
    materials = _materials()
    adapter = _adapter(
        backend=backend,
        material_resolver=lambda: calls.append("material") or materials,
        dependency_loader=lambda: calls.append("dependency") or "0.32.2",
    )

    result = adapter.embed((EmbeddingInputItem("chunk-1", "alpha"),))

    assert calls == ["dependency", "material"]
    assert result.items[0].vector == (0.25,)
    assert backend.calls == [((EmbeddingInputItem("chunk-1", "alpha"),), materials)]


@pytest.mark.parametrize(
    "changed_materials",
    (
        lambda: replace(_materials(), execution_abi_id=""),
        lambda: replace(_materials(), execution_abi_version=""),
        lambda: replace(_materials(), execution_abi_contract_digest="bad"),
        lambda: replace(_materials(), execution_descriptor_digest="bad"),
        lambda: replace(_materials(), material_lock_digest="B" * 64),
    ),
)
def test_mlx_embedding_rejects_changed_materials_before_backend(
    changed_materials,
) -> None:
    backend = _Backend()
    adapter = _adapter(
        backend=backend,
        material_resolver=changed_materials,
    )

    with pytest.raises(EmbeddingExecutionError, match="material"):
        adapter.embed((EmbeddingInputItem("chunk-1", "alpha"),))
    assert backend.calls == []


def test_mlx_embedding_rejects_unsupported_descriptor_before_backend() -> None:
    backend = _Backend()
    adapter = _adapter(
        backend=backend,
        descriptor_validators=ExecutionDescriptorValidatorRegistry(()),
    )

    with pytest.raises(EmbeddingExecutionError, match="material"):
        adapter.embed((EmbeddingInputItem("chunk-1", "alpha"),))
    assert backend.calls == []


def test_mlx_embedding_static_and_receiver_resolved_capabilities_are_separate() -> None:
    calls: list[str] = []
    backend = _Backend()
    adapter = _adapter(
        backend=backend,
        material_resolver=lambda: calls.append("material") or _materials(),
        dependency_loader=lambda: calls.append("dependency") or "0.32.2",
    )

    assert adapter.capabilities["embeddings"] is False
    assert calls == []
    assert adapter.resolved_capabilities()["embeddings"] is True
    assert calls == ["dependency", "material"]
    assert backend.calls == []
