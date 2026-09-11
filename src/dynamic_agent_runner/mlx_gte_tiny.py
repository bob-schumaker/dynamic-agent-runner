"""MLX-free validation primitives for the closed GTE Tiny embedding profile."""

from __future__ import annotations

import json
import math
import struct
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from dynamic_agent_runner.errors import EmbeddingExecutionError
from dynamic_agent_runner.local_models import (
    EmbeddingBatchResult,
    EmbeddingInputItem,
    EmbeddingVectorItem,
)


@dataclass(frozen=True)
class MLXGteTinyLimits:
    """Fixed upper bounds before the closed encoder allocates model arrays."""

    max_items: int = 128
    max_item_bytes: int = 64 * 1024
    max_batch_bytes: int = 1024 * 1024
    max_tokens: int = 512
    vector_dimension: int = 384
    max_observed_memory_bytes: int = 1024 * 1024 * 1024


@dataclass(frozen=True)
class MLXGteTinyVector:
    """One untrusted vector candidate returned by the private backend."""

    item_id: str
    values: tuple[object, ...]


class MLXGteTinyMaterialReader(Protocol):
    """Receiver-private reader that verifies a role before exposing its bytes."""

    def list_roles(self) -> tuple[str, ...]:
        """Return exactly the roles offered by one prepared material set."""

    def read_verified(
        self, role: str, expected_bytes: int, expected_sha256: str
    ) -> bytes:
        """Return one already verified, regular, nonsymlinked source file."""


_MATERIALS = (
    (
        "bert_config",
        669,
        "d3e8bc1261c0933b87dfaa12e984e311158a723c5593a0a57f9558f2a8262e3c",
    ),
    (
        "bert_weights",
        45_457_576,
        "41282c37ddd19dbf7352fca3bafd3d187baffacd7231f3f0cd69b7525630e08d",
    ),
    (
        "modules_manifest",
        229,
        "8f4b264b80206c830bebbdcae377e137925650a433b689343a63bdc9b3145460",
    ),
    (
        "pooling_config",
        190,
        "4be450dde3b0273bb9787637cfbd28fe04a7ba6ab9d36ac48e92b11e350ffc23",
    ),
    (
        "sentence_transformer_config",
        53,
        "ec8e29d6dcb61b611b7d3fdd2982c4524e6ad985959fa7194eacfb655a8d0d51",
    ),
    (
        "tokenizer_added_tokens",
        82,
        "909e96cb32d92ce728a01bc99850cbba26196d74115c17ebeb019275412588f2",
    ),
    (
        "tokenizer_config",
        1_536,
        "69033fe64b478a07aa521133752d2772a9dc7b823bc2a7bb5b8944def1c9c5fd",
    ),
    (
        "tokenizer_json",
        711_661,
        "da0e79933b9ed51798a3ae27893d3c5fa4a201126cef75586296df9b4d2c62a0",
    ),
    (
        "tokenizer_special_tokens",
        228,
        "cb63d0cbbf45160dc9cd786a257759593b798ae0c72957011016dbc3972df4e4",
    ),
    (
        "tokenizer_vocab",
        231_508,
        "07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3",
    ),
)


def resolve_closed_material_roles(
    reader: MLXGteTinyMaterialReader,
) -> dict[str, bytes]:
    """Read only the exact, lock-bound material role set in fixed order."""

    expected_roles = tuple(role for role, _, _ in _MATERIALS)
    try:
        if reader.list_roles() != expected_roles:
            raise EmbeddingExecutionError("MLX embedding material is unavailable")
        return {
            role: reader.read_verified(role, expected_bytes, expected_sha256)
            for role, expected_bytes, expected_sha256 in _MATERIALS
        }
    except EmbeddingExecutionError:
        raise
    except Exception as error:  # noqa: BLE001 - receiver file reader boundary.
        raise EmbeddingExecutionError(
            "MLX embedding material is unavailable"
        ) from error


def rewrite_bert_weight_name(source_name: str) -> str:
    """Map one locked Hugging Face BERT tensor name to the closed MLX module."""

    if not isinstance(source_name, str) or not source_name.startswith("bert."):
        raise EmbeddingExecutionError("MLX embedding material is unavailable")
    name = source_name.removeprefix("bert.")
    for old, new in (
        ("encoder.layer.", "encoder.layers."),
        ("attention.self.key.", "attention.key_proj."),
        ("attention.self.query.", "attention.query_proj."),
        ("attention.self.value.", "attention.value_proj."),
        ("attention.output.dense.", "attention.out_proj."),
        ("attention.output.LayerNorm.", "attention.ln1."),
        ("output.LayerNorm.", "ln2."),
        ("intermediate.dense.", "linear1."),
        ("output.dense.", "linear2."),
        ("embeddings.LayerNorm.", "embeddings.norm."),
        ("pooler.dense.", "pooler."),
    ):
        name = name.replace(old, new)
    if not name:
        raise EmbeddingExecutionError("MLX embedding material is unavailable")
    return name


def parse_safetensors_header(
    payload: bytes, *, allocate: Callable[[], object]
) -> dict[str, object]:
    """Parse only an admitted, bounded safetensors metadata header."""

    if len(payload) < 8:
        raise EmbeddingExecutionError("MLX embedding material is unavailable")
    header_length = struct.unpack("<Q", payload[:8])[0]
    if header_length > 16_384 or len(payload) < 8 + header_length:
        raise EmbeddingExecutionError("MLX embedding material is unavailable")
    try:
        parsed = json.loads(
            payload[8 : 8 + header_length].decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise EmbeddingExecutionError(
            "MLX embedding material is unavailable"
        ) from error
    if not isinstance(parsed, dict) or len(parsed) != 103:
        raise EmbeddingExecutionError("MLX embedding material is unavailable")
    allocate()
    return parsed


def masked_mean_pool(  # noqa: C901 - closed pooling validation is intentionally adjacent.
    *,
    hidden_states: Sequence[Sequence[Sequence[float]]],
    attention_masks: Sequence[Sequence[int]],
) -> tuple[tuple[float, ...], ...]:
    """Compute non-normalized float pooling over attended sequence positions."""

    if len(hidden_states) != len(attention_masks):
        raise EmbeddingExecutionError("MLX embedding pooling is unavailable")
    pooled: list[tuple[float, ...]] = []
    for states, mask in zip(hidden_states, attention_masks, strict=True):
        if len(states) != len(mask) or not states:
            raise EmbeddingExecutionError("MLX embedding pooling is unavailable")
        dimension = len(states[0])
        if not dimension or any(len(state) != dimension for state in states):
            raise EmbeddingExecutionError("MLX embedding pooling is unavailable")
        totals = [0.0] * dimension
        attended = 0
        for state, included in zip(states, mask, strict=True):
            if included not in (0, 1):
                raise EmbeddingExecutionError("MLX embedding pooling is unavailable")
            if included:
                attended += 1
                for index, value in enumerate(state):
                    if not isinstance(value, (int, float)) or isinstance(value, bool):
                        raise EmbeddingExecutionError(
                            "MLX embedding pooling is unavailable"
                        )
                    totals[index] += float(value)
        if not attended:
            raise EmbeddingExecutionError("MLX embedding pooling is unavailable")
        pooled.append(tuple(total / attended for total in totals))
    return tuple(pooled)


def validate_gte_tiny_vectors(
    inputs: Sequence[EmbeddingInputItem],
    vectors: Sequence[MLXGteTinyVector],
    *,
    limits: MLXGteTinyLimits,
) -> EmbeddingBatchResult:
    """Validate exact, ordered finite vectors before exposing them to callers."""

    normalized_inputs = _validate_inputs(inputs, limits)
    normalized_vectors = tuple(vectors)
    if len(normalized_vectors) != len(normalized_inputs):
        raise EmbeddingExecutionError("MLX embedding result is unavailable")
    result_items: list[EmbeddingVectorItem] = []
    for item, vector in zip(normalized_inputs, normalized_vectors, strict=True):
        if not isinstance(vector, MLXGteTinyVector) or vector.item_id != item.id:
            raise EmbeddingExecutionError("MLX embedding result is unavailable")
        if len(vector.values) != limits.vector_dimension:
            raise EmbeddingExecutionError("MLX embedding result is unavailable")
        values: list[float] = []
        for value in vector.values:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise EmbeddingExecutionError("MLX embedding result is unavailable")
            normalized = float(value)
            if not math.isfinite(normalized):
                raise EmbeddingExecutionError("MLX embedding result is unavailable")
            values.append(normalized)
        result_items.append(EmbeddingVectorItem(id=item.id, vector=tuple(values)))
    return EmbeddingBatchResult(model="mlx-gte-tiny-v1", items=tuple(result_items))


def _validate_inputs(
    inputs: Sequence[EmbeddingInputItem], limits: MLXGteTinyLimits
) -> tuple[EmbeddingInputItem, ...]:
    normalized = tuple(inputs)
    if not normalized or len(normalized) > limits.max_items:
        raise EmbeddingExecutionError("MLX embedding input is unavailable")
    total_bytes = 0
    seen_ids: set[str] = set()
    for item in normalized:
        if (
            not isinstance(item, EmbeddingInputItem)
            or not item.id
            or item.id in seen_ids
        ):
            raise EmbeddingExecutionError("MLX embedding input is unavailable")
        if not isinstance(item.text, str):
            raise EmbeddingExecutionError("MLX embedding input is unavailable")
        try:
            text_bytes = len(item.text.encode("utf-8"))
        except UnicodeError as error:
            raise EmbeddingExecutionError(
                "MLX embedding input is unavailable"
            ) from error
        if text_bytes > limits.max_item_bytes:
            raise EmbeddingExecutionError("MLX embedding input is unavailable")
        total_bytes += text_bytes
        if total_bytes > limits.max_batch_bytes:
            raise EmbeddingExecutionError("MLX embedding input is unavailable")
        seen_ids.add(item.id)
    return normalized


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result
