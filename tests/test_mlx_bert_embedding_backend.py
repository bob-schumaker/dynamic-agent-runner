"""Fake-only contract for the generic MLX BERT embedding interpreter."""

from __future__ import annotations

import json
import math
import struct
import asyncio
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from dynamic_agent_runner.errors import EmbeddingExecutionError
from dynamic_agent_runner.local_models import EmbeddingBatchResult, EmbeddingInputItem
from dynamic_agent_runner.workflow_host.capabilities import (
    CapabilityCatalog,
    CapabilityContract,
    CapabilityProvider,
    CapabilityRequirement,
    CapabilityRequirements,
)
from dynamic_agent_runner.workflow_host.embedding_execution import (
    EmbeddingBatchLimits,
    EmbeddingExecutionService,
    EmbeddingProviderCatalog,
    EmbeddingTextItem,
    LocalEmbeddingAdapterProvider,
    derive_embedding_execution_binding,
)
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptorValidatorRegistry,
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.model_execution_binding import (
    ModelExecutionBinding,
)
from dynamic_agent_runner.workflow_host.mlx_embedding_abi import (
    BERT_ENCODER_MLX_V1_ABI,
    BertEncoderMlxV1EmbeddingBackend,
    BertEncoderMlxV1DescriptorValidator,
    _bert_tensor_shapes,
    bert_encoder_mlx_v1_embedding_batch_limits,
)
from dynamic_agent_runner.mlx_local_embedding import (
    MLXLocalEmbeddingConfig,
    MLXPreparedEmbeddingArtifacts,
    create_mlx_local_embedding_adapter,
    create_mlx_local_embedding_async_adapter,
)


def _materials(
    *, pooling: str = "cls", normalization: str = "none", **limit_overrides: int
) -> SimpleNamespace:
    limits = {
        "max_items": 1,
        "max_item_bytes": 1024,
        "max_aggregate_bytes": 1024,
        "max_tokens": 3,
        "max_vectors": 1,
        "max_memory_bytes": 8 * 1024**3,
        "max_tokenizer_bytes": 16 * 1024 * 1024,
        "max_weights_bytes": 8 * 1024**3,
        "max_safetensors_header_bytes": 16 * 1024 * 1024,
        "max_conformance_fixture_bytes": 16 * 1024 * 1024,
    }
    limits.update(limit_overrides)
    return SimpleNamespace(
        execution_descriptor=parse_execution_descriptor(
            {
                "format_version": 1,
                "architecture_abi": {
                    "id": "bert-encoder-mlx-v1",
                    "version": "1",
                    "contract_digest": "2179662461bf786c7f55d88d9e3454a3d4dc59f5e818a96e248847abc62e4420",
                },
                "material_roles": ["tokenizer", "weights"],
                "abi_fields": {
                    "tokenizer": {
                        "role": "tokenizer",
                        "format": "wordpiece-json-v1",
                        "normalization": "nfc",
                        "pre_tokenizer": "bert-basic-v1",
                        "special_token_ids": {
                            "cls": 101,
                            "sep": 102,
                            "pad": 0,
                            "unk": 100,
                        },
                        "truncation": "longest-first",
                    },
                    "encoder": {
                        "weights_role": "weights",
                        "tensor_layout": "bert-encoder-safetensors-v1",
                        "dtype": "float32",
                        "vocab_size": 200,
                        "hidden_size": 2,
                        "layers": 1,
                        "attention_heads": 1,
                        "intermediate_size": 2,
                        "max_positions": 4,
                        "type_vocab_size": 1,
                    },
                    "pooling": pooling,
                    "normalization": normalization,
                    "limits": limits,
                    "conformance": {
                        "fixture_filename": "conformance-fixture.json",
                        "fixture_sha256": "a" * 64,
                        "precision": "float32",
                        "metric": "max_abs",
                        "max_error": 0.0,
                    },
                },
            }
        )
    )


def test_bert_abi_projects_descriptor_limits_without_material_read() -> None:
    descriptor = _materials(max_items=2, max_vectors=4).execution_descriptor

    limits = bert_encoder_mlx_v1_embedding_batch_limits(descriptor)

    assert limits.max_items == 2
    assert limits.max_item_utf8_bytes == 1024
    assert limits.max_total_utf8_bytes == 1024
    assert limits.max_vector_dimension == 2
    assert limits.max_total_vectors == 4


TensorHeader = dict[str, dict[str, object]]
HeaderMutation = Callable[[TensorHeader], None]
TokenizerAsset = dict[str, object]
TokenizerMutation = Callable[[TokenizerAsset], None]


def _tokenizer_bytes(*, mutate: TokenizerMutation | None = None) -> bytes:
    vocab = {
        (
            "[PAD]"
            if index == 0
            else "[UNK]"
            if index == 100
            else "[CLS]"
            if index == 101
            else "[SEP]"
            if index == 102
            else f"token-{index}"
        ): index
        for index in range(200)
    }
    asset: TokenizerAsset = {
        "model": {"type": "WordPiece", "unk_token": "[UNK]", "vocab": vocab},
        "normalizer": {"type": "BertNormalizer", "lowercase": False},
        "pre_tokenizer": {"type": "BertPreTokenizer"},
    }
    if mutate is not None:
        mutate(asset)
    return json.dumps(asset).encode()


def _weights_header(*, mutate: HeaderMutation | None = None) -> bytes:
    descriptor = _materials().execution_descriptor
    cursor = 0
    header = {
        name: {
            "data_offsets": [
                cursor,
                cursor := cursor + 4 * math.prod(shape),
            ],
            "dtype": "F32",
            "shape": list(shape),
        }
        for name, shape in _bert_tensor_shapes(descriptor).items()
    }
    if mutate is not None:
        mutate(header)
    return json.dumps(header).encode()


def _weights_blob(
    *,
    mutate: HeaderMutation | None = None,
    values: dict[str, list[float]] | None = None,
) -> bytes:
    header = _weights_header(mutate=mutate)
    descriptor = _materials().execution_descriptor
    payload_size = sum(
        4 * math.prod(shape) for shape in _bert_tensor_shapes(descriptor).values()
    )
    payload = bytearray(payload_size)
    if values is not None:
        metadata = json.loads(header)
        for name, tensor_values in values.items():
            start, end = metadata[name]["data_offsets"]
            assert end - start == 4 * len(tensor_values)
            struct.pack_into(f"<{len(tensor_values)}f", payload, start, *tensor_values)
    return len(header).to_bytes(8, "little") + header + payload


def _prepared_materials() -> MLXPreparedEmbeddingArtifacts:
    descriptor = _materials().execution_descriptor
    return MLXPreparedEmbeddingArtifacts(
        execution_abi_id=BERT_ENCODER_MLX_V1_ABI.abi_id,
        execution_abi_version=BERT_ENCODER_MLX_V1_ABI.version,
        execution_abi_contract_digest=BERT_ENCODER_MLX_V1_ABI.contract_digest,
        execution_descriptor_digest=descriptor.digest,
        material_lock_digest="c" * 64,
        execution_descriptor=descriptor,
    )


class _NumpyMlx:
    int32 = np.int32

    @staticmethod
    def array(value: object, dtype: object | None = None) -> np.ndarray:
        return np.array(value, dtype=dtype)

    @staticmethod
    def arange(size: int) -> np.ndarray:
        return np.arange(size)

    @staticmethod
    def zeros(shape: tuple[int, ...], dtype: object | None = None) -> np.ndarray:
        return np.zeros(shape, dtype=dtype)

    @staticmethod
    def mean(value: np.ndarray, *, axis: int, keepdims: bool) -> np.ndarray:
        return np.mean(value, axis=axis, keepdims=keepdims)

    @staticmethod
    def sqrt(value: np.ndarray) -> np.ndarray:
        return np.sqrt(value)

    @staticmethod
    def sum(value: np.ndarray, *, axis: int, keepdims: bool = False) -> np.ndarray:
        return np.sum(value, axis=axis, keepdims=keepdims)

    @staticmethod
    def softmax(value: np.ndarray, *, axis: int) -> np.ndarray:
        shifted = value - np.max(value, axis=axis, keepdims=True)
        exponentials = np.exp(shifted)
        return exponentials / np.sum(exponentials, axis=axis, keepdims=True)

    @staticmethod
    def erf(value: np.ndarray) -> np.ndarray:
        return np.vectorize(math.erf)(value)

    @staticmethod
    def eval(*_values: object) -> None:
        return None

    @staticmethod
    def load(source: str | BytesIO) -> dict[str, np.ndarray]:
        payload = (
            Path(source).read_bytes() if isinstance(source, str) else source.read()
        )
        header_size = int.from_bytes(payload[:8], "little")
        header = json.loads(payload[8 : 8 + header_size])
        data = payload[8 + header_size :]
        dtypes = {"F16": np.float16, "BF16": np.float32, "F32": np.float32}
        return {
            name: np.frombuffer(
                data,
                dtype=dtypes[metadata["dtype"]],
                count=math.prod(metadata["shape"]),
                offset=metadata["data_offsets"][0],
            ).reshape(metadata["shape"])
            for name, metadata in header.items()
        }


class _RecordingNumpyMlx(_NumpyMlx):
    def __init__(self) -> None:
        self.arrays: list[np.ndarray] = []

    def array(self, value: object, dtype: object | None = None) -> np.ndarray:
        array = np.array(value, dtype=dtype)
        self.arrays.append(array)
        return array


class _PathOnlyNumpyMlx(_NumpyMlx):
    @staticmethod
    def load(source: str) -> dict[str, np.ndarray]:
        assert isinstance(source, str)
        path = Path(source)
        assert path.name == "weights.safetensors"
        return _NumpyMlx.load(BytesIO(path.read_bytes()))


def test_backend_rejects_malformed_artifacts_before_tokenizer_or_model_work() -> None:
    calls: list[str] = []
    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=lambda _role: calls.append("artifact") or b"malformed",
    )

    with pytest.raises(EmbeddingExecutionError, match="material"):
        backend.embed((EmbeddingInputItem("entry", "text"),), _materials())

    assert calls == ["artifact"]


def test_backend_rejects_malformed_weights_before_tokenizer_or_model_work() -> None:
    calls: list[str] = []

    def artifact_reader(role: str) -> bytes:
        calls.append(role)
        return _tokenizer_bytes() if role == "tokenizer" else b"malformed"

    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=artifact_reader,
    )

    with pytest.raises(EmbeddingExecutionError, match="material"):
        backend.embed((EmbeddingInputItem("entry", "text"),), _materials())

    assert calls == ["tokenizer", "weights"]


def test_backend_rejects_unknown_tensor_before_tokenizer_or_model_work() -> None:
    calls: list[str] = []
    header = json.dumps({"unexpected": {}}).encode()

    def artifact_reader(role: str) -> bytes:
        calls.append(role)
        return (
            _tokenizer_bytes()
            if role == "tokenizer"
            else len(header).to_bytes(8, "little") + header
        )

    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=artifact_reader,
    )

    with pytest.raises(EmbeddingExecutionError, match="material"):
        backend.embed((EmbeddingInputItem("entry", "text"),), _materials())

    assert calls == ["tokenizer", "weights"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda header: header["embeddings.word_embeddings.weight"].update(
            shape=[199, 2]
        ),
        lambda header: header["embeddings.word_embeddings.weight"].update(dtype="F16"),
    ],
)
def test_backend_rejects_wrong_tensor_metadata_before_tokenizer_or_model_work(
    mutate: HeaderMutation,
) -> None:
    calls: list[str] = []
    header = _weights_header(mutate=mutate)

    def artifact_reader(role: str) -> bytes:
        calls.append(role)
        return (
            _tokenizer_bytes()
            if role == "tokenizer"
            else len(header).to_bytes(8, "little") + header
        )

    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=artifact_reader,
    )

    with pytest.raises(EmbeddingExecutionError, match="material"):
        backend.embed((EmbeddingInputItem("entry", "text"),), _materials())

    assert calls == ["tokenizer", "weights"]


def test_backend_rejects_invalid_tensor_offsets_before_tokenizer_or_model_work() -> (
    None
):
    calls: list[str] = []
    weights = _weights_blob(
        mutate=lambda header: header["embeddings.word_embeddings.weight"].update(
            data_offsets=[0, 1]
        )
    )

    def artifact_reader(role: str) -> bytes:
        calls.append(role)
        return _tokenizer_bytes() if role == "tokenizer" else weights

    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=artifact_reader,
    )

    with pytest.raises(EmbeddingExecutionError, match="material"):
        backend.embed((EmbeddingInputItem("entry", "text"),), _materials())

    assert calls == ["tokenizer", "weights"]


def test_backend_admits_exact_tensor_offsets_before_execution() -> None:
    calls: list[str] = []
    weights = _weights_blob()

    def artifact_reader(role: str) -> bytes:
        calls.append(role)
        return _tokenizer_bytes() if role == "tokenizer" else weights

    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=artifact_reader,
        mlx_loader=object,
    )

    with pytest.raises(EmbeddingExecutionError, match="execution"):
        backend.embed((EmbeddingInputItem("entry", "text"),), _materials())

    assert calls == ["tokenizer", "weights"]


def test_backend_loads_mlx_only_after_sealed_material_admission() -> None:
    calls: list[str] = []
    weights = _weights_blob()
    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=lambda role: (
            calls.append(role)
            or (_tokenizer_bytes() if role == "tokenizer" else weights)
        ),
        mlx_loader=lambda: calls.append("mlx") or object(),
    )

    with pytest.raises(EmbeddingExecutionError, match="execution"):
        backend.embed((EmbeddingInputItem("entry", "text"),), _materials())

    assert calls == ["tokenizer", "weights", "mlx"]


def test_backend_executes_sealed_bert_encoder_with_fake_mlx() -> None:
    weights = _weights_blob()
    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=lambda role: (
            _tokenizer_bytes() if role == "tokenizer" else weights
        ),
        mlx_loader=_NumpyMlx,
    )

    result = backend.embed((EmbeddingInputItem("entry", "text"),), _materials())

    assert isinstance(result, EmbeddingBatchResult)
    assert result.model == _materials().execution_descriptor.digest
    assert [(item.id, item.vector) for item in result.items] == [("entry", (0.0, 0.0))]


def test_backend_truncation_retains_required_sep_token() -> None:
    weights = _weights_blob()
    mlx = _RecordingNumpyMlx()
    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=lambda role: (
            _tokenizer_bytes() if role == "tokenizer" else weights
        ),
        mlx_loader=lambda: mlx,
    )

    backend.embed((EmbeddingInputItem("entry", "one two"),), _materials())

    assert mlx.arrays[0].tolist() == [[101, 100, 102]]


def test_backend_pads_token_batches_and_preserves_input_order() -> None:
    weights = _weights_blob()
    mlx = _RecordingNumpyMlx()
    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=lambda role: (
            _tokenizer_bytes() if role == "tokenizer" else weights
        ),
        mlx_loader=lambda: mlx,
    )
    items = (EmbeddingInputItem("first", ""), EmbeddingInputItem("second", "text"))

    result = backend.embed(
        items,
        _materials(max_items=2, max_vectors=2),
    )

    assert mlx.arrays[0].tolist() == [[101, 102, 0], [101, 100, 102]]
    assert mlx.arrays[1].tolist() == [[1, 1, 0], [1, 1, 1]]
    assert [item.id for item in result.items] == ["first", "second"]


def test_backend_rejects_nonfinite_materialized_vectors() -> None:
    word_embeddings = [0.0] * 400
    word_embeddings[202:204] = [math.nan, 1.0]
    weights = _weights_blob(
        values={
            "embeddings.word_embeddings.weight": word_embeddings,
            "embeddings.LayerNorm.weight": [1.0, 1.0],
            "encoder.layer.0.attention.output.LayerNorm.weight": [1.0, 1.0],
            "encoder.layer.0.output.LayerNorm.weight": [1.0, 1.0],
        }
    )
    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=lambda role: (
            _tokenizer_bytes() if role == "tokenizer" else weights
        ),
        mlx_loader=_NumpyMlx,
    )

    with pytest.raises(EmbeddingExecutionError, match="execution"):
        backend.embed((EmbeddingInputItem("entry", "text"),), _materials())


def test_backend_execution_failure_redacts_input_content() -> None:
    secret = "private-floorplan-or-vault-content"
    word_embeddings = [0.0] * 400
    word_embeddings[202:204] = [math.nan, 1.0]
    weights = _weights_blob(
        values={
            "embeddings.word_embeddings.weight": word_embeddings,
            "embeddings.LayerNorm.weight": [1.0, 1.0],
            "encoder.layer.0.attention.output.LayerNorm.weight": [1.0, 1.0],
            "encoder.layer.0.output.LayerNorm.weight": [1.0, 1.0],
        }
    )
    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=lambda role: (
            _tokenizer_bytes() if role == "tokenizer" else weights
        ),
        mlx_loader=_NumpyMlx,
    )

    with pytest.raises(EmbeddingExecutionError) as raised:
        backend.embed((EmbeddingInputItem("entry", secret),), _materials())

    assert str(raised.value) == "MLX embedding execution failed"
    assert secret not in str(raised.value)


@pytest.mark.parametrize(
    ("pooling", "normalization", "expected"),
    [
        ("cls", "none", (1.0, -1.0)),
        ("cls", "l2", (math.sqrt(0.5), -math.sqrt(0.5))),
        ("masked_mean", "none", (0.0, 0.0)),
    ],
)
def test_backend_applies_declared_pooling(
    pooling: str, normalization: str, expected: tuple[float, float]
) -> None:
    layer_norm_weights = {
        "embeddings.LayerNorm.weight": [1.0, 1.0],
        "encoder.layer.0.attention.output.LayerNorm.weight": [1.0, 1.0],
        "encoder.layer.0.output.LayerNorm.weight": [1.0, 1.0],
    }
    word_embeddings = [0.0] * 400
    word_embeddings[200:204] = [0.0, 0.0, 1.0, -1.0]
    word_embeddings[204:206] = [-1.0, 1.0]
    weights = _weights_blob(
        values={
            "embeddings.word_embeddings.weight": word_embeddings,
            **layer_norm_weights,
        }
    )
    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=lambda role: (
            _tokenizer_bytes() if role == "tokenizer" else weights
        ),
        mlx_loader=_NumpyMlx,
    )

    result = backend.embed(
        (EmbeddingInputItem("entry", "text"),),
        _materials(pooling=pooling, normalization=normalization),
    )

    assert result.items[0].vector == pytest.approx(expected)


def test_backend_has_sync_async_adapter_parity_without_mlx_import() -> None:
    weights = _weights_blob()
    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=lambda role: (
            _tokenizer_bytes() if role == "tokenizer" else weights
        ),
        mlx_loader=_NumpyMlx,
    )
    config = MLXLocalEmbeddingConfig(
        material_resolver=_prepared_materials,
        descriptor_validators=ExecutionDescriptorValidatorRegistry(
            (BertEncoderMlxV1DescriptorValidator(),)
        ),
    )
    kwargs = {
        "backend": backend,
        "dependency_loader": lambda: "0.32.2",
        "platform_system": lambda: "Darwin",
        "macos_version": lambda: (14, 0),
        "machine": lambda: "arm64",
    }
    items = (EmbeddingInputItem("entry", "text"),)

    sync = create_mlx_local_embedding_adapter(config, **kwargs).embed(items)
    asynchronous = asyncio.run(
        create_mlx_local_embedding_async_adapter(config, **kwargs).embed(items)
    )

    assert asynchronous == sync


def test_generic_mlx_adapter_registers_only_through_exact_embedding_capability() -> (
    None
):
    descriptor = _materials().execution_descriptor
    contract = CapabilityContract(
        "embedding.execute.v1", "1", "d" * 64, ("deterministic",)
    )
    requirements = CapabilityRequirements(
        (
            CapabilityRequirement(
                contract.capability_id,
                contract.contract_version,
                contract.contract_digest,
                contract.features,
            ),
        ),
        {},
    )
    model_binding = ModelExecutionBinding(
        logical_model_id="workflow-locked-model",
        runner_contract_id="mlx-embedding-v1",
        runner_contract_version="1",
        loader_profile_contract_id="sealed-embedding-v1",
        loader_profile_contract_version="1",
        material_lock_digest="c" * 64,
        capability_requirements_digest="e" * 64,
        runner_capability_id="embedding.execute.v1",
        runner_capability_version="1",
        runner_capability_digest="f" * 64,
    )
    weights = _weights_blob()
    adapter = create_mlx_local_embedding_adapter(
        MLXLocalEmbeddingConfig(
            material_resolver=_prepared_materials,
            descriptor_validators=ExecutionDescriptorValidatorRegistry(
                (BertEncoderMlxV1DescriptorValidator(),)
            ),
        ),
        backend=BertEncoderMlxV1EmbeddingBackend(
            artifact_reader=lambda role: (
                _tokenizer_bytes() if role == "tokenizer" else weights
            ),
            mlx_loader=_NumpyMlx,
        ),
        dependency_loader=lambda: "0.32.2",
        platform_system=lambda: "Darwin",
        macos_version=lambda: (14, 0),
        machine=lambda: "arm64",
    )
    provider = LocalEmbeddingAdapterProvider(
        "receiver-mlx-bert", contract, adapter, model_binding
    )
    selected = CapabilityCatalog(
        (contract,),
        (
            CapabilityProvider(
                provider.provider_id,
                contract,
                conformance_passed=True,
                conformance_vector_ids=frozenset({descriptor.digest}),
            ),
        ),
    ).resolve(requirements)

    result = EmbeddingExecutionService(
        providers=EmbeddingProviderCatalog((provider,)),
        host_limits=EmbeddingBatchLimits(1, 1024, 1024, 2, 1),
    ).execute(
        binding=derive_embedding_execution_binding(
            model_binding=model_binding, requirements=requirements
        ),
        selected_provider_ids=selected.selected_provider_ids,
        package_limits=EmbeddingBatchLimits(1, 1024, 1024, 2, 1),
        items=(EmbeddingTextItem("entry", "text"),),
    )

    assert [(item.item_id, item.values) for item in result] == [("entry", (0.0, 0.0))]


def test_backend_supplies_admitted_weights_as_a_scoped_named_safetensors_file() -> None:
    weights = _weights_blob()
    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=lambda role: (
            _tokenizer_bytes() if role == "tokenizer" else weights
        ),
        mlx_loader=_PathOnlyNumpyMlx,
    )

    result = backend.embed((EmbeddingInputItem("entry", "text"),), _materials())

    assert result.items[0].id == "entry"


def test_backend_rejects_invalid_wordpiece_tokenizer_before_weights_read() -> None:
    calls: list[str] = []
    tokenizer = _tokenizer_bytes(
        mutate=lambda asset: asset["model"]["vocab"].pop("token-199")  # type: ignore[index]
    )
    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=lambda _role: calls.append("artifact") or tokenizer,
    )

    with pytest.raises(EmbeddingExecutionError, match="material"):
        backend.embed((EmbeddingInputItem("entry", "text"),), _materials())

    assert calls == ["artifact"]


@pytest.mark.parametrize(
    ("items", "limits"),
    [
        ((), {}),
        (
            (EmbeddingInputItem("entry", "text"), EmbeddingInputItem("other", "text")),
            {"max_items": 1},
        ),
        ((EmbeddingInputItem("entry", "text"),), {"max_item_bytes": 3}),
        (
            (EmbeddingInputItem("entry", "x"), EmbeddingInputItem("entry", "x")),
            {"max_items": 2, "max_vectors": 2},
        ),
        (
            (EmbeddingInputItem("entry", "xx"), EmbeddingInputItem("other", "xx")),
            {"max_items": 2, "max_vectors": 2, "max_aggregate_bytes": 3},
        ),
    ],
)
def test_backend_rejects_invalid_inputs_before_artifact_reads(
    items: tuple[EmbeddingInputItem, ...], limits: dict[str, int]
) -> None:
    calls: list[str] = []
    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=lambda _role: calls.append("artifact") or b"{}",
    )

    with pytest.raises(EmbeddingExecutionError, match="input"):
        backend.embed(items, _materials(**limits))

    assert calls == []


def test_backend_rejects_declared_memory_overage_before_artifact_reads() -> None:
    calls: list[str] = []
    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=lambda _role: calls.append("artifact") or b"{}",
    )

    with pytest.raises(EmbeddingExecutionError, match="material"):
        backend.embed(
            (EmbeddingInputItem("entry", "text"),),
            _materials(max_memory_bytes=1),
        )

    assert calls == []


@pytest.mark.parametrize(
    ("limits", "expected_calls"),
    [
        ({"max_tokenizer_bytes": 1}, ["tokenizer"]),
        ({"max_weights_bytes": 1}, ["tokenizer", "weights"]),
        ({"max_safetensors_header_bytes": 1}, ["tokenizer", "weights"]),
    ],
)
def test_backend_enforces_descriptor_artifact_byte_limits_before_execution(
    limits: dict[str, int], expected_calls: list[str]
) -> None:
    calls: list[str] = []
    header = _weights_header()

    def artifact_reader(role: str) -> bytes:
        calls.append(role)
        return (
            (b"{}" if "max_tokenizer_bytes" in limits else _tokenizer_bytes())
            if role == "tokenizer"
            else len(header).to_bytes(8, "little") + header
        )

    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=artifact_reader,
    )

    with pytest.raises(EmbeddingExecutionError, match="material"):
        backend.embed((EmbeddingInputItem("entry", "text"),), _materials(**limits))

    assert calls == expected_calls
