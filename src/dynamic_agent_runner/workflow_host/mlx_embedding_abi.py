"""Pure descriptor validation for the generic MLX BERT encoder ABI."""

from __future__ import annotations

import math
import json
import tempfile
from collections.abc import Mapping
from collections.abc import Callable, Sequence
from typing import Protocol
import unicodedata

from dynamic_agent_runner.errors import EmbeddingExecutionError
from dynamic_agent_runner.local_models import (
    EmbeddingBatchResult,
    EmbeddingInputItem,
    EmbeddingVectorItem,
)
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptor,
    ExecutionDescriptorAbi,
    ExecutionDescriptorError,
)
from dynamic_agent_runner.workflow_host.embedding_execution import EmbeddingBatchLimits


BERT_ENCODER_MLX_V1_ABI = ExecutionDescriptorAbi(
    "bert-encoder-mlx-v1",
    "1",
    "2179662461bf786c7f55d88d9e3454a3d4dc59f5e818a96e248847abc62e4420",
)


class BertEncoderMlxV1DescriptorValidator:
    """Validate the finite, model-neutral BERT encoder descriptor grammar."""

    identity = BERT_ENCODER_MLX_V1_ABI

    def validate(self, descriptor: ExecutionDescriptor) -> None:
        if descriptor.architecture_abi != self.identity:
            _invalid()
        if descriptor.material_roles != ("tokenizer", "weights"):
            _invalid()
        fields = _mapping(
            descriptor.abi_fields,
            {
                "tokenizer",
                "encoder",
                "pooling",
                "normalization",
                "limits",
                "conformance",
            },
        )
        tokenizer = _mapping(
            fields["tokenizer"],
            {
                "role",
                "format",
                "normalization",
                "pre_tokenizer",
                "special_token_ids",
                "truncation",
            },
        )
        encoder = _mapping(
            fields["encoder"],
            {
                "weights_role",
                "tensor_layout",
                "dtype",
                "vocab_size",
                "hidden_size",
                "layers",
                "attention_heads",
                "intermediate_size",
                "max_positions",
                "type_vocab_size",
            },
        )
        limits = _mapping(
            fields["limits"],
            {
                "max_items",
                "max_item_bytes",
                "max_aggregate_bytes",
                "max_tokens",
                "max_vectors",
                "max_memory_bytes",
                "max_tokenizer_bytes",
                "max_weights_bytes",
                "max_safetensors_header_bytes",
                "max_conformance_fixture_bytes",
            },
        )
        conformance = _mapping(
            fields["conformance"],
            {"fixture_filename", "fixture_sha256", "precision", "metric", "max_error"},
        )
        _one_of(tokenizer["role"], {"tokenizer"})
        _one_of(tokenizer["format"], {"wordpiece-json-v1"})
        _one_of(tokenizer["normalization"], {"nfc", "nfc-lowercase"})
        _one_of(tokenizer["pre_tokenizer"], {"bert-basic-v1"})
        _one_of(tokenizer["truncation"], {"longest-first"})
        token_ids = _mapping(
            tokenizer["special_token_ids"], {"cls", "sep", "pad", "unk"}
        )
        vocab_size = _bounded_int(encoder["vocab_size"], 500_000)
        ids = [
            _nonnegative_int(token_ids[name]) for name in ("cls", "sep", "pad", "unk")
        ]
        if len(set(ids)) != 4 or any(value >= vocab_size for value in ids):
            _invalid()
        _one_of(encoder["weights_role"], {"weights"})
        _one_of(encoder["tensor_layout"], {"bert-encoder-safetensors-v1"})
        _one_of(encoder["dtype"], {"float16", "bfloat16", "float32"})
        hidden_size = _bounded_int(encoder["hidden_size"], 4_096)
        _bounded_int(encoder["layers"], 48)
        heads = _bounded_int(encoder["attention_heads"], 64)
        _bounded_int(encoder["intermediate_size"], 16_384)
        positions = _bounded_int(encoder["max_positions"], 4_096)
        _bounded_int(encoder["type_vocab_size"], 16)
        if hidden_size % heads:
            _invalid()
        _one_of(fields["pooling"], {"cls", "masked_mean"})
        _one_of(fields["normalization"], {"none", "l2"})
        limit_maxima = {
            "max_items": 256,
            "max_item_bytes": 1024 * 1024,
            "max_aggregate_bytes": 16 * 1024 * 1024,
            "max_tokens": 4_096,
            "max_vectors": 16_384,
            "max_memory_bytes": 8 * 1024**3,
            "max_tokenizer_bytes": 16 * 1024 * 1024,
            "max_weights_bytes": 8 * 1024**3,
            "max_safetensors_header_bytes": 16 * 1024 * 1024,
            "max_conformance_fixture_bytes": 16 * 1024 * 1024,
        }
        values = {
            name: _bounded_int(limits[name], maximum)
            for name, maximum in limit_maxima.items()
        }
        if (
            values["max_tokens"] > positions
            or values["max_vectors"] < values["max_items"]
        ):
            _invalid()
        _one_of(conformance["fixture_filename"], {"conformance-fixture.json"})
        _hex(conformance["fixture_sha256"])
        _one_of(conformance["precision"], {"float32"})
        _one_of(conformance["metric"], {"max_abs"})
        error = conformance["max_error"]
        if (
            not isinstance(error, (int, float))
            or isinstance(error, bool)
            or not math.isfinite(error)
            or not 0 <= error <= 0.1
        ):
            _invalid()


def bert_encoder_mlx_v1_embedding_batch_limits(
    descriptor: ExecutionDescriptor,
) -> EmbeddingBatchLimits:
    """Project one admitted BERT ABI descriptor to private generic batch limits."""

    try:
        BertEncoderMlxV1DescriptorValidator().validate(descriptor)
        fields = descriptor.abi_fields
        limits = fields["limits"]
        encoder = fields["encoder"]
        if not isinstance(limits, Mapping) or not isinstance(encoder, Mapping):
            raise ValueError
        return EmbeddingBatchLimits(
            max_items=limits["max_items"],  # type: ignore[arg-type]
            max_item_utf8_bytes=limits["max_item_bytes"],  # type: ignore[arg-type]
            max_total_utf8_bytes=limits["max_aggregate_bytes"],  # type: ignore[arg-type]
            max_vector_dimension=encoder["hidden_size"],  # type: ignore[arg-type]
            max_total_vectors=limits["max_vectors"],  # type: ignore[arg-type]
        )
    except Exception as error:  # noqa: BLE001 - sealed ABI boundary.
        raise EmbeddingExecutionError("MLX embedding limits are unavailable") from error


def _mapping(value: object, keys: set[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != keys:
        _invalid()
    return value


class _EmbeddingMaterialReceipt(Protocol):
    execution_descriptor: ExecutionDescriptor


class BertEncoderMlxV1EmbeddingBackend:
    """Admit sealed BERT material before loading the MLX runtime."""

    def __init__(
        self,
        *,
        artifact_reader: Callable[[str], bytes],
        mlx_loader: Callable[[], object] | None = None,
    ) -> None:
        self._artifact_reader = artifact_reader
        self._mlx_loader = mlx_loader or _load_mlx_core

    def embed(
        self,
        items: Sequence[EmbeddingInputItem],
        materials: _EmbeddingMaterialReceipt,
    ) -> object:
        """Embed one admitted batch through the closed BERT ABI."""

        descriptor, limits = _admit_bert_descriptor(materials)
        _validate_embedding_inputs(items, limits)
        _validate_declared_memory(descriptor, limits, item_count=len(items))
        tokenizer, weights, header = _read_bert_artifacts(
            self._artifact_reader,
            descriptor,
            limits,
        )
        try:
            mlx = self._mlx_loader()
            with tempfile.TemporaryDirectory(prefix="dar-mlx-") as directory:
                path = f"{directory}/weights.safetensors"
                with open(path, "xb") as material_file:
                    material_file.write(weights)
                tensors = mlx.load(path)
            if not isinstance(tensors, Mapping) or set(tensors) != set(header):
                raise ValueError
            return _execute_bert_encoder(
                mlx,
                tensors,
                tokenizer,
                tuple(items),
                descriptor,
            )
        except EmbeddingExecutionError:
            raise
        except Exception as error:  # noqa: BLE001 - dependency and execution boundary.
            raise EmbeddingExecutionError("MLX embedding execution failed") from error


def _admit_bert_descriptor(
    materials: _EmbeddingMaterialReceipt,
) -> tuple[ExecutionDescriptor, Mapping[str, object]]:
    try:
        if not isinstance(materials.execution_descriptor, ExecutionDescriptor):
            raise ValueError
        descriptor = materials.execution_descriptor
        BertEncoderMlxV1DescriptorValidator().validate(descriptor)
        limits = descriptor.abi_fields["limits"]
        if not isinstance(limits, Mapping):
            raise ValueError
        return descriptor, limits
    except Exception as error:  # noqa: BLE001 - sealed descriptor boundary.
        raise EmbeddingExecutionError(
            "MLX embedding material is unavailable"
        ) from error


def _read_bert_artifacts(
    artifact_reader: Callable[[str], bytes],
    descriptor: ExecutionDescriptor,
    limits: Mapping[str, object],
) -> tuple[Mapping[str, object], bytes, Mapping[str, object]]:
    try:
        tokenizer_bytes = artifact_reader("tokenizer")
        if (
            not isinstance(tokenizer_bytes, bytes)
            or len(tokenizer_bytes) > limits["max_tokenizer_bytes"]
        ):
            raise ValueError
        tokenizer = json.loads(tokenizer_bytes.decode("utf-8"))
        if not isinstance(tokenizer, Mapping):
            raise ValueError
        _validate_wordpiece_tokenizer(tokenizer, descriptor)
        weights = artifact_reader("weights")
        if (
            not isinstance(weights, bytes)
            or len(weights) < 8
            or len(weights) > limits["max_weights_bytes"]
        ):
            raise ValueError
        header_size = int.from_bytes(weights[:8], "little")
        if (
            header_size > limits["max_safetensors_header_bytes"]
            or len(weights) < 8 + header_size
        ):
            raise ValueError
        header = json.loads(weights[8 : 8 + header_size].decode("utf-8"))
        if not isinstance(header, Mapping):
            raise ValueError
        _validate_bert_tensor_header(
            header,
            descriptor,
            data_size=len(weights) - 8 - header_size,
        )
        return tokenizer, weights, header
    except Exception as error:  # noqa: BLE001 - sealed artifact boundary.
        raise EmbeddingExecutionError(
            "MLX embedding material is unavailable"
        ) from error


def _bert_tensor_shapes(
    descriptor: ExecutionDescriptor,
) -> dict[str, tuple[int, ...]]:
    encoder = descriptor.abi_fields["encoder"]
    assert isinstance(encoder, Mapping)
    vocab_size = encoder["vocab_size"]
    hidden_size = encoder["hidden_size"]
    layers = encoder["layers"]
    intermediate_size = encoder["intermediate_size"]
    max_positions = encoder["max_positions"]
    type_vocab_size = encoder["type_vocab_size"]
    assert all(
        isinstance(value, int)
        for value in (
            vocab_size,
            hidden_size,
            layers,
            intermediate_size,
            max_positions,
            type_vocab_size,
        )
    )
    shapes = {
        "embeddings.word_embeddings.weight": (vocab_size, hidden_size),
        "embeddings.position_embeddings.weight": (max_positions, hidden_size),
        "embeddings.token_type_embeddings.weight": (type_vocab_size, hidden_size),
        "embeddings.LayerNorm.weight": (hidden_size,),
        "embeddings.LayerNorm.bias": (hidden_size,),
    }
    for index in range(layers):
        prefix = f"encoder.layer.{index}"
        for projection in ("query", "key", "value"):
            shapes[f"{prefix}.attention.self.{projection}.weight"] = (
                hidden_size,
                hidden_size,
            )
            shapes[f"{prefix}.attention.self.{projection}.bias"] = (hidden_size,)
        shapes.update(
            {
                f"{prefix}.attention.output.dense.weight": (
                    hidden_size,
                    hidden_size,
                ),
                f"{prefix}.attention.output.dense.bias": (hidden_size,),
                f"{prefix}.attention.output.LayerNorm.weight": (hidden_size,),
                f"{prefix}.attention.output.LayerNorm.bias": (hidden_size,),
                f"{prefix}.intermediate.dense.weight": (
                    intermediate_size,
                    hidden_size,
                ),
                f"{prefix}.intermediate.dense.bias": (intermediate_size,),
                f"{prefix}.output.dense.weight": (
                    hidden_size,
                    intermediate_size,
                ),
                f"{prefix}.output.dense.bias": (hidden_size,),
                f"{prefix}.output.LayerNorm.weight": (hidden_size,),
                f"{prefix}.output.LayerNorm.bias": (hidden_size,),
            }
        )
    return shapes


def _load_mlx_core() -> object:
    import mlx.core as mx

    return mx


def _execute_bert_encoder(
    mlx: object,
    tensors: Mapping[str, object],
    tokenizer: Mapping[str, object],
    items: tuple[EmbeddingInputItem, ...],
    descriptor: ExecutionDescriptor,
) -> EmbeddingBatchResult:
    token_ids, attention_mask = _tokenize_wordpiece_items(tokenizer, items, descriptor)
    token_array = mlx.array(token_ids, dtype=mlx.int32)
    mask_array = mlx.array(attention_mask, dtype=mlx.int32)
    batch_size, token_count = token_array.shape
    encoder = descriptor.abi_fields["encoder"]
    assert isinstance(encoder, Mapping)
    hidden_size = encoder["hidden_size"]
    heads = encoder["attention_heads"]
    layers = encoder["layers"]
    assert isinstance(hidden_size, int)
    assert isinstance(heads, int)
    assert isinstance(layers, int)
    hidden = (
        tensors["embeddings.word_embeddings.weight"][token_array]
        + tensors["embeddings.position_embeddings.weight"][mlx.arange(token_count)][
            None, :, :
        ]
        + tensors["embeddings.token_type_embeddings.weight"][
            mlx.zeros((batch_size, token_count), dtype=mlx.int32)
        ]
    )
    hidden = _layer_norm(
        mlx,
        hidden,
        tensors["embeddings.LayerNorm.weight"],
        tensors["embeddings.LayerNorm.bias"],
    )
    head_size = hidden_size // heads
    for index in range(layers):
        prefix = f"encoder.layer.{index}"
        query = _dense(
            hidden,
            tensors[f"{prefix}.attention.self.query.weight"],
            tensors[f"{prefix}.attention.self.query.bias"],
        )
        key = _dense(
            hidden,
            tensors[f"{prefix}.attention.self.key.weight"],
            tensors[f"{prefix}.attention.self.key.bias"],
        )
        value = _dense(
            hidden,
            tensors[f"{prefix}.attention.self.value.weight"],
            tensors[f"{prefix}.attention.self.value.bias"],
        )
        query = query.reshape(batch_size, token_count, heads, head_size).transpose(
            0, 2, 1, 3
        )
        key = key.reshape(batch_size, token_count, heads, head_size).transpose(
            0, 2, 1, 3
        )
        value = value.reshape(batch_size, token_count, heads, head_size).transpose(
            0, 2, 1, 3
        )
        scores = query @ key.transpose(0, 1, 3, 2) / math.sqrt(head_size)
        scores = scores + (1 - mask_array[:, None, None, :]) * -10000.0
        attended = mlx.softmax(scores, axis=-1) @ value
        attended = attended.transpose(0, 2, 1, 3).reshape(
            batch_size, token_count, hidden_size
        )
        attention_output = _dense(
            attended,
            tensors[f"{prefix}.attention.output.dense.weight"],
            tensors[f"{prefix}.attention.output.dense.bias"],
        )
        hidden = _layer_norm(
            mlx,
            hidden + attention_output,
            tensors[f"{prefix}.attention.output.LayerNorm.weight"],
            tensors[f"{prefix}.attention.output.LayerNorm.bias"],
        )
        intermediate = _dense(
            hidden,
            tensors[f"{prefix}.intermediate.dense.weight"],
            tensors[f"{prefix}.intermediate.dense.bias"],
        )
        intermediate = (
            0.5 * intermediate * (1.0 + mlx.erf(intermediate / math.sqrt(2.0)))
        )
        output = _dense(
            intermediate,
            tensors[f"{prefix}.output.dense.weight"],
            tensors[f"{prefix}.output.dense.bias"],
        )
        hidden = _layer_norm(
            mlx,
            hidden + output,
            tensors[f"{prefix}.output.LayerNorm.weight"],
            tensors[f"{prefix}.output.LayerNorm.bias"],
        )
    if descriptor.abi_fields["pooling"] == "cls":
        vectors = hidden[:, 0, :]
    else:
        mask = mask_array[:, :, None]
        vectors = mlx.sum(hidden * mask, axis=1) / mlx.sum(mask, axis=1, keepdims=False)
    if descriptor.abi_fields["normalization"] == "l2":
        vectors = vectors / mlx.sqrt(mlx.sum(vectors * vectors, axis=-1, keepdims=True))
    mlx.eval(vectors)
    values = vectors.tolist()
    if not isinstance(values, list) or len(values) != len(items):
        raise EmbeddingExecutionError("MLX embedding execution failed")
    result_items: list[EmbeddingVectorItem] = []
    for item, vector in zip(items, values, strict=True):
        if (
            not isinstance(vector, list)
            or len(vector) != hidden_size
            or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                for value in vector
            )
        ):
            raise EmbeddingExecutionError("MLX embedding execution failed")
        result_items.append(
            EmbeddingVectorItem(item.id, tuple(float(value) for value in vector))
        )
    return EmbeddingBatchResult(model=descriptor.digest, items=tuple(result_items))


def _dense(values: object, weight: object, bias: object) -> object:
    return values @ weight.T + bias


def _layer_norm(mlx: object, values: object, weight: object, bias: object) -> object:
    mean = mlx.mean(values, axis=-1, keepdims=True)
    variance = mlx.mean((values - mean) * (values - mean), axis=-1, keepdims=True)
    return (values - mean) / mlx.sqrt(variance + 1e-12) * weight + bias


def _tokenize_wordpiece_items(
    tokenizer: Mapping[str, object],
    items: tuple[EmbeddingInputItem, ...],
    descriptor: ExecutionDescriptor,
) -> tuple[list[list[int]], list[list[int]]]:
    model = tokenizer["model"]
    assert isinstance(model, Mapping)
    vocab = model["vocab"]
    assert isinstance(vocab, Mapping)
    fields = descriptor.abi_fields["tokenizer"]
    limits = descriptor.abi_fields["limits"]
    assert isinstance(fields, Mapping)
    assert isinstance(limits, Mapping)
    special_ids = fields["special_token_ids"]
    assert isinstance(special_ids, Mapping)
    lowercase = fields["normalization"] == "nfc-lowercase"
    max_tokens = limits["max_tokens"]
    assert isinstance(max_tokens, int)
    if max_tokens < 2:
        raise EmbeddingExecutionError("MLX embedding input is invalid")
    encoded = [
        [
            special_ids["cls"],
            *_wordpiece_ids(item.text, vocab, lowercase, special_ids["unk"])[
                : max_tokens - 2
            ],
            special_ids["sep"],
        ]
        for item in items
    ]
    width = max(len(token_ids) for token_ids in encoded)
    padded = [
        token_ids + [special_ids["pad"]] * (width - len(token_ids))
        for token_ids in encoded
    ]
    masks = [
        [1] * len(token_ids) + [0] * (width - len(token_ids)) for token_ids in encoded
    ]
    return padded, masks


def _wordpiece_ids(
    text: str, vocab: Mapping[str, object], lowercase: bool, unk_id: object
) -> list[int]:
    normalized = unicodedata.normalize("NFC", text)
    if lowercase:
        normalized = normalized.lower()
    ids: list[int] = []
    for token in _bert_basic_tokens(normalized):
        index = 0
        pieces: list[int] = []
        while index < len(token):
            match: int | None = None
            next_index = len(token)
            while next_index > index:
                piece = token[index:next_index]
                if index:
                    piece = f"##{piece}"
                value = vocab.get(piece)
                if isinstance(value, int) and not isinstance(value, bool):
                    match = value
                    break
                next_index -= 1
            if match is None:
                pieces = [unk_id]
                break
            pieces.append(match)
            index = next_index
        ids.extend(pieces)
    return ids


def _bert_basic_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    for character in text:
        category = unicodedata.category(character)
        if character.isspace() or category.startswith("C"):
            if current:
                tokens.append("".join(current))
                current.clear()
        elif category.startswith("P"):
            if current:
                tokens.append("".join(current))
                current.clear()
            tokens.append(character)
        else:
            current.append(character)
    if current:
        tokens.append("".join(current))
    return tokens


def _validate_bert_tensor_header(
    header: Mapping[str, object], descriptor: ExecutionDescriptor, *, data_size: int
) -> None:
    shapes = _bert_tensor_shapes(descriptor)
    if set(header) != set(shapes):
        raise ValueError
    expected_dtype, item_bytes = _bert_dtype_details(descriptor)
    spans: list[tuple[int, int]] = []
    for name, expected_shape in shapes.items():
        metadata = header[name]
        if not isinstance(metadata, Mapping):
            raise ValueError
        shape = metadata.get("shape")
        offsets = metadata.get("data_offsets")
        if (
            metadata.get("dtype") != expected_dtype
            or not isinstance(shape, list)
            or tuple(shape) != expected_shape
            or any(
                not isinstance(value, int) or isinstance(value, bool) for value in shape
            )
            or not isinstance(offsets, list)
            or len(offsets) != 2
            or any(
                not isinstance(value, int) or isinstance(value, bool)
                for value in offsets
            )
        ):
            raise ValueError
        start, end = offsets
        if start < 0 or end < start or end > data_size:
            raise ValueError
        if end - start != math.prod(expected_shape) * item_bytes:
            raise ValueError
        spans.append((start, end))
    previous_end = 0
    for start, end in sorted(spans):
        if start != previous_end:
            raise ValueError
        previous_end = end
    if previous_end != data_size:
        raise ValueError


def _validate_embedding_inputs(
    items: Sequence[EmbeddingInputItem], limits: Mapping[str, object]
) -> None:
    if not items or len(items) > limits["max_items"]:
        raise EmbeddingExecutionError("MLX embedding input is invalid")
    seen_ids: set[str] = set()
    aggregate_bytes = 0
    for item in items:
        if (
            not isinstance(item, EmbeddingInputItem)
            or not isinstance(item.id, str)
            or not item.id
            or item.id in seen_ids
            or not isinstance(item.text, str)
        ):
            raise EmbeddingExecutionError("MLX embedding input is invalid")
        try:
            item_bytes = len(item.text.encode("utf-8"))
        except UnicodeError as error:
            raise EmbeddingExecutionError("MLX embedding input is invalid") from error
        if item_bytes > limits["max_item_bytes"]:
            raise EmbeddingExecutionError("MLX embedding input is invalid")
        aggregate_bytes += item_bytes
        if aggregate_bytes > limits["max_aggregate_bytes"]:
            raise EmbeddingExecutionError("MLX embedding input is invalid")
        seen_ids.add(item.id)


def _validate_declared_memory(
    descriptor: ExecutionDescriptor, limits: Mapping[str, object], *, item_count: int
) -> None:
    _, item_bytes = _bert_dtype_details(descriptor)
    parameter_bytes = sum(
        math.prod(shape) * item_bytes
        for shape in _bert_tensor_shapes(descriptor).values()
    )
    encoder = descriptor.abi_fields["encoder"]
    assert isinstance(encoder, Mapping)
    activation_bytes = 4 * item_count * limits["max_tokens"] * encoder["hidden_size"]
    if parameter_bytes + activation_bytes > limits["max_memory_bytes"]:
        raise EmbeddingExecutionError("MLX embedding material is unavailable")


def _bert_dtype_details(descriptor: ExecutionDescriptor) -> tuple[str, int]:
    encoder = descriptor.abi_fields["encoder"]
    assert isinstance(encoder, Mapping)
    return {
        "float16": ("F16", 2),
        "bfloat16": ("BF16", 2),
        "float32": ("F32", 4),
    }[encoder["dtype"]]


def _validate_wordpiece_tokenizer(
    tokenizer: Mapping[str, object], descriptor: ExecutionDescriptor
) -> None:
    fields = descriptor.abi_fields
    descriptor_tokenizer = fields["tokenizer"]
    encoder = fields["encoder"]
    assert isinstance(descriptor_tokenizer, Mapping)
    assert isinstance(encoder, Mapping)
    model = tokenizer.get("model")
    normalizer = tokenizer.get("normalizer")
    pre_tokenizer = tokenizer.get("pre_tokenizer")
    if not all(
        isinstance(value, Mapping) for value in (model, normalizer, pre_tokenizer)
    ):
        raise ValueError
    if model.get("type") != "WordPiece":
        raise ValueError
    vocab = model.get("vocab")
    unk_token = model.get("unk_token")
    vocab_size = encoder["vocab_size"]
    if (
        not isinstance(vocab, Mapping)
        or not isinstance(unk_token, str)
        or not unk_token
        or not isinstance(vocab_size, int)
        or len(vocab) != vocab_size
    ):
        raise ValueError
    token_ids = set(range(vocab_size))
    if (
        any(not isinstance(token, str) or not token for token in vocab)
        or any(
            not isinstance(token_id, int) or isinstance(token_id, bool)
            for token_id in vocab.values()
        )
        or set(vocab.values()) != token_ids
    ):
        raise ValueError
    special_ids = descriptor_tokenizer["special_token_ids"]
    assert isinstance(special_ids, Mapping)
    if vocab.get(unk_token) != special_ids["unk"]:
        raise ValueError
    normalization = descriptor_tokenizer["normalization"]
    expected_lowercase = normalization == "nfc-lowercase"
    if (
        normalizer.get("type") != "BertNormalizer"
        or normalizer.get("lowercase") is not expected_lowercase
        or pre_tokenizer.get("type") != "BertPreTokenizer"
    ):
        raise ValueError


def _one_of(value: object, values: set[str]) -> None:
    if not isinstance(value, str) or value not in values:
        _invalid()


def _bounded_int(value: object, maximum: int) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 0 < value <= maximum
    ):
        _invalid()
    return value


def _nonnegative_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _invalid()
    return value


def _hex(value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _invalid()


def _invalid() -> None:
    raise ExecutionDescriptorError("execution descriptor ABI fields are invalid")
