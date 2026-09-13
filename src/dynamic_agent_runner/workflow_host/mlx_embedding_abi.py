"""Pure descriptor validation for the generic MLX BERT encoder ABI."""

from __future__ import annotations

import math
import json
import tempfile
import struct
from collections.abc import Mapping
from collections.abc import Callable, Sequence
from dataclasses import dataclass
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

BERT_ENCODER_MLX_V2_ABI = ExecutionDescriptorAbi(
    "bert-encoder-mlx-v2",
    "2",
    "646e958aae4752c3fdb2503d257929b95ad037c5462a35a7fa9e5d23aa14d35d",
)

BERT_ENCODER_MLX_V3_ABI = ExecutionDescriptorAbi(
    "bert-encoder-mlx-v3",
    "3",
    "18f1131a9ab9e42ab07163914552f2099a891e0d8fec696290804480f47538a6",
)

BERT_ENCODER_MLX_V4_ABI = ExecutionDescriptorAbi(
    "bert-encoder-mlx-v4",
    "5",
    "1db6568e50f14b1fd7752772573024e2da87518674cd78ba4f9c57cb84febb4f",
)


class BertEncoderMlxV1DescriptorValidator:
    """Validate the finite, model-neutral BERT encoder descriptor grammar."""

    identity = BERT_ENCODER_MLX_V1_ABI
    encoder_keys = {
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
    }
    tokenizer_keys = {
        "role",
        "format",
        "normalization",
        "pre_tokenizer",
        "special_token_ids",
        "truncation",
    }

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
        tokenizer = _mapping(fields["tokenizer"], self.tokenizer_keys)
        encoder = _mapping(fields["encoder"], self.encoder_keys)
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
        self._validate_tokenizer_format(tokenizer["format"])
        self._validate_tokenizer_normalization(tokenizer["normalization"])
        self._validate_pre_tokenizer(tokenizer["pre_tokenizer"])
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
        self._validate_dtypes(encoder)
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

    def _validate_dtypes(self, encoder: Mapping[str, object]) -> None:
        _one_of(encoder["dtype"], {"float16", "bfloat16", "float32"})

    def _validate_tokenizer_normalization(self, normalization: object) -> None:
        _one_of(normalization, {"nfc", "nfc-lowercase"})

    def _validate_tokenizer_format(self, format_name: object) -> None:
        _one_of(format_name, {"wordpiece-json-v1"})

    def _validate_pre_tokenizer(self, pre_tokenizer: object) -> None:
        _one_of(pre_tokenizer, {"bert-basic-v1"})


class BertEncoderMlxV2DescriptorValidator(BertEncoderMlxV1DescriptorValidator):
    """Validate the closed mixed-precision BERT descriptor grammar."""

    identity = BERT_ENCODER_MLX_V2_ABI
    encoder_keys = BertEncoderMlxV1DescriptorValidator.encoder_keys | {
        "layer_norm_dtype"
    }

    def _validate_dtypes(self, encoder: Mapping[str, object]) -> None:
        _one_of(encoder["dtype"], {"float16"})
        _one_of(encoder["layer_norm_dtype"], {"float32"})


class BertEncoderMlxV3DescriptorValidator(BertEncoderMlxV2DescriptorValidator):
    """Validate the closed accent-stripping BERT descriptor grammar."""

    identity = BERT_ENCODER_MLX_V3_ABI

    def _validate_tokenizer_normalization(self, normalization: object) -> None:
        _one_of(normalization, {"nfc-lowercase-strip-accents"})


class BertEncoderMlxV4DescriptorValidator(BertEncoderMlxV2DescriptorValidator):
    """Validate the closed SentencePiece-Unigram BERT descriptor grammar."""

    identity = BERT_ENCODER_MLX_V4_ABI
    tokenizer_keys = BertEncoderMlxV1DescriptorValidator.tokenizer_keys | {"id_offset"}

    def _validate_tokenizer_format(self, format_name: object) -> None:
        _one_of(format_name, {"sentencepiece-unigram-model-v1"})

    def _validate_pre_tokenizer(self, pre_tokenizer: object) -> None:
        _one_of(pre_tokenizer, {"sentencepiece-unigram-v1"})

    def validate(self, descriptor: ExecutionDescriptor) -> None:
        super().validate(descriptor)
        tokenizer = descriptor.abi_fields["tokenizer"]
        assert isinstance(tokenizer, Mapping)
        if tokenizer["id_offset"] != 1 or tokenizer["special_token_ids"] != {
            "cls": 0,
            "sep": 2,
            "pad": 1,
            "unk": 3,
        }:
            _invalid()

    def _validate_tokenizer_normalization(self, normalization: object) -> None:
        _one_of(normalization, {"nmt-nfkc"})


def bert_encoder_mlx_v1_embedding_batch_limits(
    descriptor: ExecutionDescriptor,
) -> EmbeddingBatchLimits:
    """Project one admitted BERT ABI descriptor to private generic batch limits."""

    try:
        _validate_supported_bert_descriptor(descriptor)
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
            if not isinstance(tensors, Mapping) or set(tensors) != (
                set(header) - {"__metadata__"}
            ):
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
        _validate_supported_bert_descriptor(descriptor)
        limits = descriptor.abi_fields["limits"]
        if not isinstance(limits, Mapping):
            raise ValueError
        return descriptor, limits
    except Exception as error:  # noqa: BLE001 - sealed descriptor boundary.
        raise EmbeddingExecutionError(
            "MLX embedding material is unavailable"
        ) from error


def _validate_supported_bert_descriptor(descriptor: ExecutionDescriptor) -> None:
    validators = {
        BERT_ENCODER_MLX_V1_ABI: BertEncoderMlxV1DescriptorValidator(),
        BERT_ENCODER_MLX_V2_ABI: BertEncoderMlxV2DescriptorValidator(),
        BERT_ENCODER_MLX_V3_ABI: BertEncoderMlxV3DescriptorValidator(),
        BERT_ENCODER_MLX_V4_ABI: BertEncoderMlxV4DescriptorValidator(),
    }
    validator = validators.get(descriptor.architecture_abi)
    if validator is None:
        _invalid()
    validator.validate(descriptor)


def _read_bert_artifacts(
    artifact_reader: Callable[[str], bytes],
    descriptor: ExecutionDescriptor,
    limits: Mapping[str, object],
) -> tuple[object, bytes, Mapping[str, object]]:
    try:
        tokenizer_bytes = artifact_reader("tokenizer")
        if (
            not isinstance(tokenizer_bytes, bytes)
            or len(tokenizer_bytes) > limits["max_tokenizer_bytes"]
        ):
            raise ValueError
        tokenizer_fields = descriptor.abi_fields["tokenizer"]
        assert isinstance(tokenizer_fields, Mapping)
        if tokenizer_fields["format"] == "sentencepiece-unigram-model-v1":
            tokenizer = _parse_sentencepiece_unigram_model(tokenizer_bytes, descriptor)
        else:
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
    tokenizer: object,
    items: tuple[EmbeddingInputItem, ...],
    descriptor: ExecutionDescriptor,
) -> EmbeddingBatchResult:
    if isinstance(tokenizer, _SentencePieceUnigramTokenizer):
        token_ids, attention_mask = _tokenize_sentencepiece_unigram_items(
            tokenizer, items, descriptor
        )
    elif isinstance(tokenizer, Mapping):
        token_ids, attention_mask = _tokenize_wordpiece_items(
            tokenizer, items, descriptor
        )
    else:
        raise EmbeddingExecutionError("MLX embedding material is unavailable")
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
    normalization = fields["normalization"]
    assert isinstance(normalization, str)
    max_tokens = limits["max_tokens"]
    assert isinstance(max_tokens, int)
    if max_tokens < 2:
        raise EmbeddingExecutionError("MLX embedding input is invalid")
    encoded = [
        [
            special_ids["cls"],
            *_wordpiece_ids(item.text, vocab, normalization, special_ids["unk"])[
                : max_tokens - 2
            ],
            special_ids["sep"],
        ]
        for item in items
    ]
    width = max_tokens
    padded = [
        token_ids + [special_ids["pad"]] * (width - len(token_ids))
        for token_ids in encoded
    ]
    masks = [
        [1] * len(token_ids) + [0] * (width - len(token_ids)) for token_ids in encoded
    ]
    return padded, masks


def _wordpiece_ids(
    text: str, vocab: Mapping[str, object], normalization: str, unk_id: object
) -> list[int]:
    normalized = unicodedata.normalize("NFC", text)
    if normalization != "nfc":
        normalized = normalized.lower()
    if normalization == "nfc-lowercase-strip-accents":
        normalized = "".join(
            character
            for character in unicodedata.normalize("NFD", normalized)
            if unicodedata.category(character) != "Mn"
        )
        normalized = unicodedata.normalize("NFC", normalized)
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


@dataclass
class _SentencePieceUnigramTrieNode:
    children: dict[str, _SentencePieceUnigramTrieNode]
    token: tuple[int, float] | None = None


@dataclass(frozen=True)
class _SentencePieceUnigramTokenizer:
    trie: _SentencePieceUnigramTrieNode
    min_score: float
    normalizer_map: bytes


def _parse_sentencepiece_unigram_model(  # noqa: C901 - the closed profile is one boundary.
    model_bytes: bytes, descriptor: ExecutionDescriptor
) -> _SentencePieceUnigramTokenizer:
    """Decode the finite SentencePiece Unigram ModelProto profile used by v4."""

    fields = _protobuf_fields(model_bytes, {1: 2, 2: 2, 3: 2})
    piece_messages = fields.get(1)
    trainer_messages = fields.get(2)
    normalizer_messages = fields.get(3)
    if (
        not piece_messages
        or len(piece_messages) > 500_000
        or not _single_bytes(trainer_messages)
        or not _single_bytes(normalizer_messages)
    ):
        raise ValueError
    trainer = _protobuf_fields(
        _single_bytes(trainer_messages),
        {
            1: 2,
            2: 2,
            3: 0,
            4: 0,
            5: 2,
            6: 0,
            7: 2,
            10: 5,
            11: 0,
            12: 0,
            13: 0,
            14: 0,
            15: 5,
            16: 0,
            17: 0,
            18: 0,
            19: 0,
            20: 0,
            21: 0,
            22: 0,
            23: 0,
            24: 0,
            25: 0,
            26: 0,
            30: 2,
            31: 2,
            32: 0,
            33: 0,
            34: 0,
            35: 0,
            36: 2,
            40: 0,
            41: 0,
            42: 0,
            43: 0,
            44: 2,
            45: 2,
            46: 2,
            47: 2,
            48: 2,
            49: 0,
            50: 0,
            51: 1,
            52: 0,
            53: 2,
        },
    )
    if _single_int(trainer.get(3)) != 1:
        raise ValueError
    if trainer.get(35) and _single_int(trainer.get(35)) != 0:
        raise ValueError
    pieces = tuple(_parse_sentencepiece_piece(value) for value in piece_messages)
    if _single_int(trainer.get(4)) != len(pieces):
        raise ValueError
    normalizer_map = _validate_sentencepiece_normalizer(
        _single_bytes(normalizer_messages)
    )
    tokenizer_fields = descriptor.abi_fields["tokenizer"]
    encoder = descriptor.abi_fields["encoder"]
    assert isinstance(tokenizer_fields, Mapping)
    assert isinstance(encoder, Mapping)
    special_ids = tokenizer_fields["special_token_ids"]
    assert isinstance(special_ids, Mapping)
    id_offset = tokenizer_fields["id_offset"]
    if (
        id_offset != 1
        or len(pieces) + id_offset > encoder["vocab_size"]
        or len(pieces) < 3
    ):
        raise ValueError
    if (
        special_ids != {"cls": 0, "sep": 2, "pad": 1, "unk": 3}
        or pieces[0][0] != "<unk>"
        or pieces[0][2] != 2
        or pieces[1][0] != "<s>"
        or pieces[1][2] != 3
        or pieces[2][0] != "</s>"
        or pieces[2][2] != 3
    ):
        raise ValueError
    trie = _SentencePieceUnigramTrieNode({})
    min_score = math.inf
    for index, (piece, score, kind) in enumerate(pieces):
        if kind == 1:
            node = trie
            for character in piece:
                node = node.children.setdefault(
                    character, _SentencePieceUnigramTrieNode({})
                )
            if node.token is not None:
                raise ValueError
            node.token = (index + id_offset, score)
            min_score = min(min_score, score)
    if not math.isfinite(min_score):
        raise ValueError
    return _SentencePieceUnigramTokenizer(trie, min_score, normalizer_map)


def _parse_sentencepiece_piece(value: object) -> tuple[str, float, int]:
    if not isinstance(value, bytes):
        raise ValueError
    fields = _protobuf_fields(value, {1: 2, 2: 5, 3: 0})
    piece_bytes = _single_bytes(fields.get(1))
    score_bytes = _single_bytes(fields.get(2))
    kind = 1 if fields.get(3) is None else _single_int(fields.get(3))
    if len(piece_bytes) > 1_024 or len(score_bytes) != 4 or kind not in {1, 2, 3}:
        raise ValueError
    piece = piece_bytes.decode("utf-8")
    score = struct.unpack("<f", score_bytes)[0]
    if not piece or not math.isfinite(score):
        raise ValueError
    return piece, score, kind


def _validate_sentencepiece_normalizer(value: bytes) -> bytes:
    fields = _protobuf_fields(value, {1: 2, 2: 2, 3: 0, 4: 0, 5: 0, 6: 2})
    if (
        _single_bytes(fields.get(1)) != b"nmt_nfkc"
        or _single_int(fields.get(3)) != 1
        or _single_int(fields.get(4)) != 1
        or (fields.get(5) and _single_int(fields.get(5)) != 1)
        or fields.get(6) not in (None, [b""])
    ):
        raise ValueError
    charsmap = _single_bytes(fields.get(2)) if fields.get(2) else b""
    if charsmap:
        _sentencepiece_normalizer_parts(charsmap)
    return charsmap


def _sentencepiece_normalizer_parts(charsmap: bytes) -> tuple[tuple[int, ...], bytes]:
    if len(charsmap) < 1_029:
        raise ValueError
    trie_size = int.from_bytes(charsmap[:4], "little")
    if (
        trie_size < 1_024
        or trie_size % 1_024
        or trie_size >= len(charsmap) - 4
        or len(charsmap) > 16 * 1024 * 1024
    ):
        raise ValueError
    normalized = charsmap[4 + trie_size :]
    if not normalized.endswith(b"\0"):
        raise ValueError
    units = tuple(
        int.from_bytes(charsmap[offset : offset + 4], "little")
        for offset in range(4, 4 + trie_size, 4)
    )
    _validate_sentencepiece_darts_units(units)
    return units, normalized


def _validate_sentencepiece_darts_units(units: tuple[int, ...]) -> None:
    for index, unit in enumerate(units):
        if _darts_label(unit) > 0xFF:
            continue
        base = index ^ _darts_offset(unit)
        if any(base ^ byte >= len(units) for byte in range(256)):
            raise ValueError


def _protobuf_fields(
    data: bytes, allowed: Mapping[int, int]
) -> dict[int, list[object]]:
    fields: dict[int, list[object]] = {}
    offset = 0
    while offset < len(data):
        key, offset = _protobuf_varint(data, offset)
        field = key >> 3
        wire = key & 7
        if field == 0 or allowed.get(field) != wire:
            raise ValueError
        if wire == 0:
            value, offset = _protobuf_varint(data, offset)
        elif wire == 2:
            size, offset = _protobuf_varint(data, offset)
            if size > len(data) - offset:
                raise ValueError
            value = data[offset : offset + size]
            offset += size
        elif wire == 1:
            if len(data) - offset < 8:
                raise ValueError
            value = data[offset : offset + 8]
            offset += 8
        elif wire == 5:
            if len(data) - offset < 4:
                raise ValueError
            value = data[offset : offset + 4]
            offset += 4
        else:
            raise ValueError
        fields.setdefault(field, []).append(value)
    return fields


def _protobuf_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            if shift and byte == 0:
                raise ValueError
            return value, offset
    raise ValueError


def _single_bytes(values: object) -> bytes:
    if (
        not isinstance(values, list)
        or len(values) != 1
        or not isinstance(values[0], bytes)
    ):
        raise ValueError
    return values[0]


def _single_int(values: object) -> int:
    if (
        not isinstance(values, list)
        or len(values) != 1
        or not isinstance(values[0], int)
    ):
        raise ValueError
    return values[0]


def _tokenize_sentencepiece_unigram_items(
    tokenizer: _SentencePieceUnigramTokenizer,
    items: tuple[EmbeddingInputItem, ...],
    descriptor: ExecutionDescriptor,
) -> tuple[list[list[int]], list[list[int]]]:
    fields = descriptor.abi_fields["tokenizer"]
    limits = descriptor.abi_fields["limits"]
    assert isinstance(fields, Mapping)
    assert isinstance(limits, Mapping)
    special_ids = fields["special_token_ids"]
    assert isinstance(special_ids, Mapping)
    max_tokens = limits["max_tokens"]
    assert isinstance(max_tokens, int)
    if max_tokens < 2:
        raise EmbeddingExecutionError("MLX embedding input is invalid")
    encoded = [
        [
            special_ids["cls"],
            *_sentencepiece_unigram_ids(item.text, tokenizer, special_ids["unk"])[
                : max_tokens - 2
            ],
            special_ids["sep"],
        ]
        for item in items
    ]
    return (
        [ids + [special_ids["pad"]] * (max_tokens - len(ids)) for ids in encoded],
        [[1] * len(ids) + [0] * (max_tokens - len(ids)) for ids in encoded],
    )


def _sentencepiece_unigram_ids(
    text: str, tokenizer: _SentencePieceUnigramTokenizer, unk_id: object
) -> list[int]:
    normalized = _normalize_sentencepiece_text(text, tokenizer.normalizer_map)
    if normalized == "▁":
        return []
    scores = [-math.inf] * (len(normalized) + 1)
    tokens: list[tuple[int, int] | None] = [None] * (len(normalized) + 1)
    scores[0] = 0.0
    for start in range(len(normalized)):
        if not math.isfinite(scores[start]):
            continue
        candidates, has_single_piece = _sentencepiece_unigram_candidates(
            normalized, tokenizer.trie, start
        )
        for end, token_id, token_score in candidates:
            candidate = scores[start] + token_score
            if candidate > scores[end + 1]:
                scores[end + 1] = candidate
                tokens[end + 1] = (start, token_id)
        if not has_single_piece:
            candidate = scores[start] + tokenizer.min_score - 10.0
            if candidate > scores[start + 1]:
                scores[start + 1] = candidate
                tokens[start + 1] = (start, unk_id)
    result: list[int] = []
    position = len(normalized)
    while position:
        token = tokens[position]
        if token is None:
            raise ValueError
        position, token_id = token
        result.append(token_id)
    return list(reversed(result))


def _sentencepiece_unigram_candidates(
    normalized: str, trie: _SentencePieceUnigramTrieNode, start: int
) -> tuple[list[tuple[int, int, float]], bool]:
    node = trie
    candidates: list[tuple[int, int, float]] = []
    has_single_piece = False
    for end in range(start, len(normalized)):
        node = node.children.get(normalized[end])
        if node is None:
            break
        if node.token is not None:
            token_id, token_score = node.token
            candidates.append((end, token_id, token_score))
            has_single_piece |= end == start
    return candidates, has_single_piece


def _normalize_sentencepiece_text(text: str, charsmap: bytes) -> str:
    source = text.encode("utf-8")
    if not charsmap:
        mapped = unicodedata.normalize("NFKC", text).encode("utf-8")
    else:
        units, replacements = _sentencepiece_normalizer_parts(charsmap)
        output = bytearray()
        offset = 0
        while offset < len(source):
            length, value = _sentencepiece_longest_prefix(units, source, offset)
            if length:
                end = replacements.find(b"\0", value)
                if end < value:
                    raise ValueError
                output.extend(replacements[value:end])
                offset += length
            else:
                width = _utf8_width(source[offset])
                output.extend(source[offset : offset + width])
                offset += width
        mapped = bytes(output)
    return "▁" + "▁".join(mapped.decode("utf-8").split())


def _sentencepiece_longest_prefix(
    units: tuple[int, ...], source: bytes, start: int
) -> tuple[int, int]:
    if not units:
        raise ValueError
    node = _darts_offset(units[0])
    if node >= len(units):
        raise ValueError
    longest = (0, 0)
    for index in range(start, len(source)):
        node ^= source[index]
        if node >= len(units) or _darts_label(units[node]) != source[index]:
            break
        unit = units[node]
        node ^= _darts_offset(unit)
        if node >= len(units):
            raise ValueError
        if unit & 0x100:
            longest = (index - start + 1, units[node] & 0x7FFFFFFF)
    return longest


def _darts_label(unit: int) -> int:
    return unit & 0x800000FF


def _darts_offset(unit: int) -> int:
    return (unit >> 10) << ((unit & 0x200) >> 6)


def _utf8_width(first: int) -> int:
    if first < 0x80:
        return 1
    if 0xC2 <= first <= 0xDF:
        return 2
    if 0xE0 <= first <= 0xEF:
        return 3
    if 0xF0 <= first <= 0xF4:
        return 4
    return 1


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
    optional_shapes = _bert_optional_pooler_shapes(descriptor)
    tensor_header = _tensor_header(header, shapes, optional_shapes)
    if set(optional_shapes).issubset(tensor_header):
        shapes.update(optional_shapes)
    spans: list[tuple[int, int]] = []
    for name, expected_shape in shapes.items():
        expected_dtype, item_bytes = _bert_dtype_details(descriptor, name)
        tensor_metadata = tensor_header[name]
        if not isinstance(tensor_metadata, Mapping):
            raise ValueError
        shape = tensor_metadata.get("shape")
        offsets = tensor_metadata.get("data_offsets")
        if (
            tensor_metadata.get("dtype") != expected_dtype
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


def _tensor_header(
    header: Mapping[str, object],
    shapes: Mapping[str, tuple[int, ...]],
    optional_shapes: Mapping[str, tuple[int, ...]],
) -> dict[str, object]:
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
    tensor_names = set(tensor_header)
    optional_names = set(optional_shapes)
    if (
        not set(shapes).issubset(tensor_names)
        or tensor_names - set(shapes) - optional_names
        or (tensor_names & optional_names and not optional_names.issubset(tensor_names))
    ):
        raise ValueError
    return tensor_header


def _bert_optional_pooler_shapes(
    descriptor: ExecutionDescriptor,
) -> dict[str, tuple[int, ...]]:
    encoder = descriptor.abi_fields["encoder"]
    assert isinstance(encoder, Mapping)
    hidden_size = encoder["hidden_size"]
    assert isinstance(hidden_size, int)
    return {
        "pooler.dense.bias": (hidden_size,),
        "pooler.dense.weight": (hidden_size, hidden_size),
    }


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
    parameter_shapes = _bert_tensor_shapes(descriptor)
    parameter_shapes.update(_bert_optional_pooler_shapes(descriptor))
    parameter_bytes = sum(
        math.prod(shape) * _bert_dtype_details(descriptor, name)[1]
        for name, shape in parameter_shapes.items()
    )
    encoder = descriptor.abi_fields["encoder"]
    assert isinstance(encoder, Mapping)
    activation_bytes = 4 * item_count * limits["max_tokens"] * encoder["hidden_size"]
    if parameter_bytes + activation_bytes > limits["max_memory_bytes"]:
        raise EmbeddingExecutionError("MLX embedding material is unavailable")


def _bert_dtype_details(
    descriptor: ExecutionDescriptor, tensor_name: str
) -> tuple[str, int]:
    encoder = descriptor.abi_fields["encoder"]
    assert isinstance(encoder, Mapping)
    dtype = encoder["dtype"]
    if (
        descriptor.architecture_abi
        in (BERT_ENCODER_MLX_V2_ABI, BERT_ENCODER_MLX_V3_ABI, BERT_ENCODER_MLX_V4_ABI)
        and ".LayerNorm." in tensor_name
    ):
        dtype = encoder["layer_norm_dtype"]
    return {
        "float16": ("F16", 2),
        "bfloat16": ("BF16", 2),
        "float32": ("F32", 4),
    }[dtype]


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
    expected_lowercase = normalization != "nfc"
    expected_strip_accents = (
        None if normalization == "nfc-lowercase-strip-accents" else False
    )
    if (
        normalizer.get("type") != "BertNormalizer"
        or normalizer.get("lowercase") is not expected_lowercase
        or normalizer.get("strip_accents") is not expected_strip_accents
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
