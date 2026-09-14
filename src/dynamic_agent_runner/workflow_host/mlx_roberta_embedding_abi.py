"""Pure descriptor validation for the closed MLX RoBERTa encoder ABI."""

from __future__ import annotations

import json
import math
import tempfile
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

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


ROBERTA_ENCODER_MLX_V1_ABI = ExecutionDescriptorAbi(
    "roberta-encoder-mlx-v1",
    "1",
    "7770aa3d61b26984d2e549f99092459935d0237f67cae2e8b176c0516ce04391",
)


class RobertaEncoderMlxV1DescriptorValidator:
    """Validate the finite byte-level-BPE RoBERTa encoder descriptor grammar."""

    identity = ROBERTA_ENCODER_MLX_V1_ABI
    _encoder_keys = {
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
        "position_ids",
        "layer_norm_epsilon",
    }
    _tokenizer_keys = {
        "vocab_role",
        "merges_role",
        "format",
        "pre_tokenizer",
        "add_prefix_space",
        "special_token_ids",
        "truncation",
    }
    _limit_keys = {
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
    }
    _limit_maxima = {
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

    def validate(self, descriptor: ExecutionDescriptor) -> None:
        """Reject every descriptor fact outside this receiver-owned grammar."""

        if descriptor.architecture_abi != self.identity:
            _invalid()
        if descriptor.material_roles != ("merges", "vocab", "weights"):
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
        tokenizer = _mapping(fields["tokenizer"], self._tokenizer_keys)
        encoder = _mapping(fields["encoder"], self._encoder_keys)
        limits = _mapping(fields["limits"], self._limit_keys)
        conformance = _mapping(
            fields["conformance"],
            {"fixture_filename", "fixture_sha256", "precision", "metric", "max_error"},
        )

        _one_of(tokenizer["vocab_role"], {"vocab"})
        _one_of(tokenizer["merges_role"], {"merges"})
        _one_of(tokenizer["format"], {"roberta-byte-level-bpe-v1"})
        _one_of(tokenizer["pre_tokenizer"], {"gpt2-byte-level-v1"})
        if tokenizer["add_prefix_space"] is not False:
            _invalid()
        _one_of(tokenizer["truncation"], {"longest-first"})
        token_ids = _mapping(
            tokenizer["special_token_ids"], {"bos", "eos", "pad", "unk", "mask"}
        )

        vocab_size = _bounded_int(encoder["vocab_size"], 500_000)
        ids = [
            _nonnegative_int(token_ids[name])
            for name in ("bos", "eos", "pad", "unk", "mask")
        ]
        if len(set(ids)) != 5 or any(value >= vocab_size for value in ids):
            _invalid()
        _one_of(encoder["weights_role"], {"weights"})
        _one_of(encoder["tensor_layout"], {"roberta-encoder-safetensors-v1"})
        _one_of(encoder["dtype"], {"float32"})
        hidden_size = _bounded_int(encoder["hidden_size"], 4_096)
        _bounded_int(encoder["layers"], 48)
        heads = _bounded_int(encoder["attention_heads"], 64)
        _bounded_int(encoder["intermediate_size"], 16_384)
        positions = _bounded_int(encoder["max_positions"], 4_096)
        if encoder["type_vocab_size"] != 1:
            _invalid()
        _one_of(encoder["position_ids"], {"roberta-padding-index-v1"})
        if encoder["layer_norm_epsilon"] != 1e-5 or hidden_size % heads:
            _invalid()
        _one_of(fields["pooling"], {"cls", "masked_mean"})
        _one_of(fields["normalization"], {"none", "l2"})

        values = {
            name: _bounded_int(limits[name], maximum)
            for name, maximum in self._limit_maxima.items()
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


def _mapping(value: object, keys: set[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != keys:
        _invalid()
    return value


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


def _one_of(value: object, choices: set[object]) -> None:
    if value not in choices:
        _invalid()


def _hex(value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _invalid()


def _invalid() -> None:
    raise ExecutionDescriptorError("MLX RoBERTa encoder ABI fields are invalid")


@dataclass(frozen=True)
class _RobertaByteLevelBpeTokenizer:
    vocab: Mapping[str, int]
    merge_ranks: Mapping[tuple[str, str], int]
    byte_encoder: Mapping[int, str]
    unk_id: int


class _EmbeddingMaterialReceipt(Protocol):
    execution_descriptor: ExecutionDescriptor


class RobertaEncoderMlxV1EmbeddingBackend:
    """Admit and execute only the closed RoBERTa ABI material grammar."""

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
    ) -> EmbeddingBatchResult:
        """Embed one finite batch after material admission and before no fallback."""

        try:
            descriptor = materials.execution_descriptor
            RobertaEncoderMlxV1DescriptorValidator().validate(descriptor)
            limits = _roberta_embedding_limits(descriptor)
            _validate_embedding_inputs(items, limits)
            tokenizer, weights, header = _read_roberta_artifacts(
                self._artifact_reader, descriptor
            )
            mlx = self._mlx_loader()
            with tempfile.TemporaryDirectory(prefix="dar-mlx-") as directory:
                path = f"{directory}/weights.safetensors"
                with open(path, "xb") as material_file:
                    material_file.write(weights)
                tensors = mlx.load(path)
            if not isinstance(tensors, Mapping) or set(tensors) != set(header) - {
                "__metadata__"
            }:
                raise ValueError
            return _execute_roberta_encoder(
                mlx, tensors, tokenizer, tuple(items), descriptor
            )
        except EmbeddingExecutionError:
            raise
        except Exception as error:  # noqa: BLE001 - receiver material boundary.
            raise EmbeddingExecutionError(
                "MLX embedding material is unavailable"
            ) from error


def _roberta_embedding_limits(descriptor: ExecutionDescriptor) -> Mapping[str, object]:
    limits = descriptor.abi_fields.get("limits")
    if not isinstance(limits, Mapping):
        raise ValueError
    return limits


def roberta_encoder_mlx_v1_embedding_batch_limits(
    descriptor: ExecutionDescriptor,
) -> EmbeddingBatchLimits:
    """Project one admitted RoBERTa ABI descriptor to generic batch limits."""

    try:
        RobertaEncoderMlxV1DescriptorValidator().validate(descriptor)
        limits = _roberta_embedding_limits(descriptor)
        encoder = descriptor.abi_fields["encoder"]
        if not isinstance(encoder, Mapping):
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


def _read_roberta_artifacts(
    artifact_reader: Callable[[str], bytes], descriptor: ExecutionDescriptor
) -> tuple[_RobertaByteLevelBpeTokenizer, bytes, Mapping[str, object]]:
    limits = _roberta_embedding_limits(descriptor)
    vocab = artifact_reader("vocab")
    merges = artifact_reader("merges")
    tokenizer = _parse_roberta_byte_level_bpe(vocab, merges, descriptor)
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
    _validate_roberta_tensor_header(
        header, descriptor, data_size=len(weights) - 8 - header_size
    )
    return tokenizer, weights, header


def _roberta_tensor_shapes(
    descriptor: ExecutionDescriptor,
) -> dict[str, tuple[int, ...]]:
    encoder = descriptor.abi_fields["encoder"]
    if not isinstance(encoder, Mapping):
        raise ValueError
    values = tuple(
        encoder[name]
        for name in (
            "vocab_size",
            "hidden_size",
            "layers",
            "intermediate_size",
            "max_positions",
            "type_vocab_size",
        )
    )
    if not all(isinstance(value, int) for value in values):
        raise ValueError
    (
        vocab_size,
        hidden_size,
        layers,
        intermediate_size,
        max_positions,
        type_vocab_size,
    ) = values
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
                f"{prefix}.attention.output.dense.weight": (hidden_size, hidden_size),
                f"{prefix}.attention.output.dense.bias": (hidden_size,),
                f"{prefix}.attention.output.LayerNorm.weight": (hidden_size,),
                f"{prefix}.attention.output.LayerNorm.bias": (hidden_size,),
                f"{prefix}.intermediate.dense.weight": (intermediate_size, hidden_size),
                f"{prefix}.intermediate.dense.bias": (intermediate_size,),
                f"{prefix}.output.dense.weight": (hidden_size, intermediate_size),
                f"{prefix}.output.dense.bias": (hidden_size,),
                f"{prefix}.output.LayerNorm.weight": (hidden_size,),
                f"{prefix}.output.LayerNorm.bias": (hidden_size,),
            }
        )
    return shapes


def _validate_roberta_tensor_header(
    header: Mapping[str, object], descriptor: ExecutionDescriptor, *, data_size: int
) -> None:
    tensor_header = dict(header)
    metadata = tensor_header.pop("__metadata__", None)
    if metadata is not None and (
        not isinstance(metadata, Mapping)
        or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in metadata.items()
        )
    ):
        raise ValueError
    shapes = _roberta_tensor_shapes(descriptor)
    if set(tensor_header) != set(shapes):
        raise ValueError
    spans: list[tuple[int, int]] = []
    for name, expected_shape in shapes.items():
        entry = tensor_header[name]
        if not isinstance(entry, Mapping):
            raise ValueError
        shape = entry.get("shape")
        offsets = entry.get("data_offsets")
        if (
            entry.get("dtype") != "F32"
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
        if (
            start < 0
            or end < start
            or end > data_size
            or end - start != math.prod(expected_shape) * 4
        ):
            raise ValueError
        spans.append((start, end))
    previous_end = 0
    for start, end in sorted(spans):
        if start != previous_end:
            raise ValueError
        previous_end = end
    if previous_end != data_size:
        raise ValueError


def _execute_roberta_encoder(
    mlx: object,
    tensors: Mapping[str, object],
    tokenizer: _RobertaByteLevelBpeTokenizer,
    items: tuple[EmbeddingInputItem, ...],
    descriptor: ExecutionDescriptor,
) -> EmbeddingBatchResult:
    token_ids, attention_mask = _tokenize_roberta_byte_level_bpe_items(
        tokenizer, items, descriptor
    )
    fields = descriptor.abi_fields
    encoder = fields["encoder"]
    tokenizer_fields = fields["tokenizer"]
    if not isinstance(encoder, Mapping) or not isinstance(tokenizer_fields, Mapping):
        raise ValueError
    special_ids = tokenizer_fields["special_token_ids"]
    if not isinstance(special_ids, Mapping):
        raise ValueError
    token_array = mlx.array(token_ids, dtype=mlx.int32)
    mask_array = mlx.array(attention_mask, dtype=mlx.int32)
    position_array = mlx.array(
        _roberta_position_ids(token_ids, pad_id=special_ids["pad"]), dtype=mlx.int32
    )
    batch_size, token_count = token_array.shape
    hidden_size = encoder["hidden_size"]
    heads = encoder["attention_heads"]
    layers = encoder["layers"]
    epsilon = encoder["layer_norm_epsilon"]
    if (
        not all(isinstance(value, int) for value in (hidden_size, heads, layers))
        or epsilon != 1e-5
    ):
        raise ValueError
    hidden = (
        tensors["embeddings.word_embeddings.weight"][token_array]
        + tensors["embeddings.position_embeddings.weight"][position_array]
        + tensors["embeddings.token_type_embeddings.weight"][
            mlx.zeros((batch_size, token_count), dtype=mlx.int32)
        ]
    )
    hidden = _roberta_layer_norm(
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
        attended = (
            mlx.softmax(scores + (1 - mask_array[:, None, None, :]) * -10000.0, axis=-1)
            @ value
        )
        attended = attended.transpose(0, 2, 1, 3).reshape(
            batch_size, token_count, hidden_size
        )
        hidden = _roberta_layer_norm(
            mlx,
            hidden
            + _dense(
                attended,
                tensors[f"{prefix}.attention.output.dense.weight"],
                tensors[f"{prefix}.attention.output.dense.bias"],
            ),
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
        hidden = _roberta_layer_norm(
            mlx,
            hidden
            + _dense(
                intermediate,
                tensors[f"{prefix}.output.dense.weight"],
                tensors[f"{prefix}.output.dense.bias"],
            ),
            tensors[f"{prefix}.output.LayerNorm.weight"],
            tensors[f"{prefix}.output.LayerNorm.bias"],
        )
    if fields["pooling"] == "cls":
        vectors = hidden[:, 0, :]
    else:
        mask = mask_array[:, :, None]
        vectors = mlx.sum(hidden * mask, axis=1) / mlx.sum(mask, axis=1, keepdims=False)
    if fields["normalization"] == "l2":
        vectors = vectors / mlx.sqrt(mlx.sum(vectors * vectors, axis=-1, keepdims=True))
    mlx.eval(vectors)
    values = vectors.tolist()
    if not isinstance(values, list) or len(values) != len(items):
        raise ValueError
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
            raise ValueError
        result_items.append(
            EmbeddingVectorItem(item.id, tuple(float(value) for value in vector))
        )
    return EmbeddingBatchResult(model=descriptor.digest, items=tuple(result_items))


def _dense(values: object, weight: object, bias: object) -> object:
    return values @ weight.T + bias


def _roberta_layer_norm(
    mlx: object, values: object, weight: object, bias: object
) -> object:
    mean = mlx.mean(values, axis=-1, keepdims=True)
    variance = mlx.mean((values - mean) * (values - mean), axis=-1, keepdims=True)
    return (values - mean) / mlx.sqrt(variance + 1e-5) * weight + bias


def _validate_embedding_inputs(
    items: Sequence[EmbeddingInputItem], limits: Mapping[str, object]
) -> None:
    if not items or len(items) > limits["max_items"]:
        raise EmbeddingExecutionError("MLX embedding input is invalid")
    aggregate_bytes = 0
    seen_ids: set[str] = set()
    for item in items:
        if (
            not isinstance(item, EmbeddingInputItem)
            or not item.id
            or item.id in seen_ids
        ):
            raise EmbeddingExecutionError("MLX embedding input is invalid")
        try:
            item_bytes = len(item.text.encode("utf-8"))
        except UnicodeError as error:
            raise EmbeddingExecutionError("MLX embedding input is invalid") from error
        aggregate_bytes += item_bytes
        if (
            item_bytes > limits["max_item_bytes"]
            or aggregate_bytes > limits["max_aggregate_bytes"]
        ):
            raise EmbeddingExecutionError("MLX embedding input is invalid")
        seen_ids.add(item.id)


def _load_mlx_core() -> object:
    import mlx.core as mx

    return mx


def _parse_roberta_byte_level_bpe(  # noqa: C901 - one closed asset-admission boundary.
    vocab_bytes: bytes, merges_bytes: bytes, descriptor: ExecutionDescriptor
) -> _RobertaByteLevelBpeTokenizer:
    """Admit only the ABI's bounded `vocab.json` and `merges.txt` grammar."""

    try:
        RobertaEncoderMlxV1DescriptorValidator().validate(descriptor)
        fields = descriptor.abi_fields["tokenizer"]
        encoder = descriptor.abi_fields["encoder"]
        limits = descriptor.abi_fields["limits"]
        if not all(isinstance(value, Mapping) for value in (fields, encoder, limits)):
            raise ValueError
        if (
            len(vocab_bytes) > limits["max_tokenizer_bytes"]
            or len(merges_bytes) > limits["max_tokenizer_bytes"]
        ):
            raise ValueError
        vocab_value = json.loads(vocab_bytes.decode("utf-8"))
        if (
            not isinstance(vocab_value, dict)
            or len(vocab_value) != encoder["vocab_size"]
        ):
            raise ValueError
        vocab: dict[str, int] = {}
        for token, token_id in vocab_value.items():
            if (
                not isinstance(token, str)
                or not isinstance(token_id, int)
                or isinstance(token_id, bool)
                or token_id < 0
                or token_id >= encoder["vocab_size"]
                or token in vocab
            ):
                raise ValueError
            vocab[token] = token_id
        if set(vocab.values()) != set(range(encoder["vocab_size"])):
            raise ValueError
        special_ids = fields["special_token_ids"]
        if not isinstance(special_ids, Mapping) or any(
            vocab.get(token) != special_ids[name]
            for name, token in (
                ("bos", "<s>"),
                ("eos", "</s>"),
                ("pad", "<pad>"),
                ("unk", "<unk>"),
                ("mask", "<mask>"),
            )
        ):
            raise ValueError
        lines = merges_bytes.decode("utf-8").splitlines()
        if (
            not lines
            or lines[0]
            not in {
                "#version: 0.2",
                "#version: 0.2 - Trained by `huggingface/tokenizers`",
            }
            or len(lines) - 1 > len(vocab)
        ):
            raise ValueError
        merge_ranks: dict[tuple[str, str], int] = {}
        for rank, line in enumerate(lines[1:]):
            pair = tuple(line.split(" "))
            if len(pair) != 2 or not all(pair) or pair in merge_ranks:
                raise ValueError
            if (
                pair[0] not in vocab
                or pair[1] not in vocab
                or "".join(pair) not in vocab
            ):
                raise ValueError
            merge_ranks[pair] = rank
        return _RobertaByteLevelBpeTokenizer(
            vocab=vocab,
            merge_ranks=merge_ranks,
            byte_encoder=_gpt2_byte_encoder(),
            unk_id=special_ids["unk"],
        )
    except (
        ExecutionDescriptorError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ) as error:
        raise ValueError("RoBERTa tokenizer material is invalid") from error


def _tokenize_roberta_byte_level_bpe_items(
    tokenizer: _RobertaByteLevelBpeTokenizer,
    items: tuple[object, ...],
    descriptor: ExecutionDescriptor,
) -> tuple[list[list[int]], list[list[int]]]:
    """Frame bounded byte-level BPE IDs with the ABI's RoBERTa special tokens."""

    fields = descriptor.abi_fields["tokenizer"]
    limits = descriptor.abi_fields["limits"]
    if not isinstance(fields, Mapping) or not isinstance(limits, Mapping):
        raise ValueError
    special_ids = fields["special_token_ids"]
    max_tokens = limits["max_tokens"]
    if (
        not isinstance(special_ids, Mapping)
        or not isinstance(max_tokens, int)
        or max_tokens < 2
    ):
        raise ValueError
    encoded: list[list[int]] = []
    for item in items:
        text = getattr(item, "text", None)
        if not isinstance(text, str):
            raise ValueError
        token_ids = _roberta_byte_level_bpe_ids(text, tokenizer)[: max_tokens - 2]
        encoded.append([special_ids["bos"], *token_ids, special_ids["eos"]])
    return (
        [ids + [special_ids["pad"]] * (max_tokens - len(ids)) for ids in encoded],
        [[1] * len(ids) + [0] * (max_tokens - len(ids)) for ids in encoded],
    )


def _roberta_position_ids(
    token_ids: list[list[int]], *, pad_id: int
) -> list[list[int]]:
    """Derive RoBERTa's padding-aware absolute position IDs without MLX."""

    if not isinstance(pad_id, int) or isinstance(pad_id, bool) or pad_id < 0:
        raise ValueError
    result: list[list[int]] = []
    for row in token_ids:
        position = pad_id
        positions: list[int] = []
        for token_id in row:
            if (
                not isinstance(token_id, int)
                or isinstance(token_id, bool)
                or token_id < 0
            ):
                raise ValueError
            if token_id == pad_id:
                positions.append(pad_id)
            else:
                position += 1
                positions.append(position)
        result.append(positions)
    return result


def _roberta_byte_level_bpe_ids(
    text: str, tokenizer: _RobertaByteLevelBpeTokenizer
) -> list[int]:
    token_ids: list[int] = []
    for piece in _gpt2_pretokens(text):
        symbols = [tokenizer.byte_encoder[value] for value in piece.encode("utf-8")]
        while len(symbols) > 1:
            candidates = [
                (tokenizer.merge_ranks[pair], index, pair)
                for index, pair in enumerate(zip(symbols, symbols[1:], strict=False))
                if pair in tokenizer.merge_ranks
            ]
            if not candidates:
                break
            _rank, index, pair = min(candidates)
            symbols[index : index + 2] = [pair[0] + pair[1]]
        token_ids.extend(
            tokenizer.vocab.get(symbol, tokenizer.unk_id) for symbol in symbols
        )
    return token_ids


def _gpt2_pretokens(text: str) -> list[str]:
    """Implement the ABI-fixed GPT-2 Unicode-category pre-tokenizer."""

    pieces: list[str] = []
    index = 0
    contractions = ("'s", "'t", "'re", "'ve", "'m", "'ll", "'d")
    while index < len(text):
        contraction = next(
            (value for value in contractions if text.startswith(value, index)), None
        )
        if contraction is not None:
            pieces.append(contraction)
            index += len(contraction)
            continue
        start = index
        if text[index] == " " and index + 1 < len(text):
            category = unicodedata.category(text[index + 1])
            if category[0] in {"L", "N"} or not text[index + 1].isspace():
                index += 1
        if index < len(text) and unicodedata.category(text[index])[0] in {"L", "N"}:
            kind = unicodedata.category(text[index])[0]
            index += 1
            while index < len(text) and unicodedata.category(text[index])[0] == kind:
                index += 1
        elif index < len(text) and not text[index].isspace():
            index += 1
            while (
                index < len(text)
                and not text[index].isspace()
                and unicodedata.category(text[index])[0] not in {"L", "N"}
            ):
                index += 1
        else:
            index += 1
            while index < len(text) and text[index].isspace():
                index += 1
        pieces.append(text[start:index])
    return pieces


def _gpt2_byte_encoder() -> dict[int, str]:
    bytes_in_order = (
        list(range(ord("!"), ord("~") + 1))
        + list(range(161, 173))
        + list(range(174, 256))
    )
    code_points = list(bytes_in_order)
    for index, value in enumerate(
        value for value in range(256) if value not in bytes_in_order
    ):
        bytes_in_order.append(value)
        code_points.append(256 + index)
    return dict(zip(bytes_in_order, map(chr, code_points), strict=True))
