"""RED conformance contract for the private GTE Tiny MLX encoder helpers."""

from __future__ import annotations

import math
import struct

import pytest

from dynamic_agent_runner.errors import EmbeddingExecutionError
from dynamic_agent_runner.local_models import EmbeddingInputItem
from dynamic_agent_runner.mlx_gte_tiny import (
    MLXGteTinyLimits,
    MLXGteTinyVector,
    masked_mean_pool,
    parse_safetensors_header,
    resolve_closed_material_roles,
    validate_gte_tiny_vectors,
)


class _Reader:
    def __init__(self, roles: tuple[str, ...]) -> None:
        self.roles = roles
        self.reads: list[tuple[str, int, str]] = []

    def list_roles(self) -> tuple[str, ...]:
        return self.roles

    def read_verified(
        self, role: str, expected_bytes: int, expected_sha256: str
    ) -> bytes:
        self.reads.append((role, expected_bytes, expected_sha256))
        return b"verified"


def test_safetensors_header_ceiling_rejects_before_json_or_array_allocation() -> None:
    allocations: list[str] = []
    oversized_header = struct.pack("<Q", 16_385) + b"{" * 16_385

    with pytest.raises(EmbeddingExecutionError, match="material"):
        parse_safetensors_header(
            oversized_header, allocate=lambda: allocations.append("mlx")
        )

    assert allocations == []


def test_closed_material_roles_reject_missing_or_extra_before_any_read() -> None:
    reader = _Reader(("bert_config",))

    with pytest.raises(EmbeddingExecutionError, match="material"):
        resolve_closed_material_roles(reader)

    assert reader.reads == []


def test_closed_material_roles_use_only_the_locked_role_byte_and_hash_table() -> None:
    roles = (
        "bert_config",
        "bert_weights",
        "modules_manifest",
        "pooling_config",
        "sentence_transformer_config",
        "tokenizer_added_tokens",
        "tokenizer_config",
        "tokenizer_json",
        "tokenizer_special_tokens",
        "tokenizer_vocab",
    )
    reader = _Reader(roles)

    materials = resolve_closed_material_roles(reader)

    assert tuple(materials) == roles
    assert [role for role, _, _ in reader.reads] == list(roles)
    assert reader.reads[0][1:] == (
        669,
        "d3e8bc1261c0933b87dfaa12e984e311158a723c5593a0a57f9558f2a8262e3c",
    )


@pytest.mark.parametrize(
    "payload",
    (
        b"",
        struct.pack("<Q", 16_384),
        struct.pack("<Q", 2) + b"{}",
        struct.pack("<Q", 7) + b'{"x":1}',
    ),
)
def test_safetensors_header_rejects_truncated_or_nonconforming_metadata(
    payload: bytes,
) -> None:
    with pytest.raises(EmbeddingExecutionError, match="material"):
        parse_safetensors_header(payload, allocate=lambda: pytest.fail("allocated"))


def test_masked_mean_pooling_uses_only_attended_tokens_and_never_normalizes() -> None:
    result = masked_mean_pool(
        hidden_states=(((3.0, 4.0), (100.0, 100.0)),),
        attention_masks=((1, 0),),
    )

    assert result == ((3.0, 4.0),)


def test_masked_mean_pooling_rejects_empty_attention_before_result_return() -> None:
    with pytest.raises(EmbeddingExecutionError, match="pooling"):
        masked_mean_pool(hidden_states=(((3.0, 4.0),),), attention_masks=((0,),))


def test_result_validation_preserves_input_order_and_requires_384_finite_values() -> (
    None
):
    items = (EmbeddingInputItem("first", "alpha"), EmbeddingInputItem("second", "beta"))
    vectors = (
        MLXGteTinyVector("first", (0.25,) * 384),
        MLXGteTinyVector("second", (0.5,) * 384),
    )

    result = validate_gte_tiny_vectors(items, vectors, limits=MLXGteTinyLimits())

    assert tuple(item.id for item in result.items) == ("first", "second")
    assert result.items[0].vector == (0.25,) * 384


@pytest.mark.parametrize(
    "vectors",
    (
        (),
        (MLXGteTinyVector("second", (0.5,) * 384),),
        (MLXGteTinyVector("first", (0.25,) * 383),),
        (MLXGteTinyVector("first", (math.nan,) * 384),),
        (MLXGteTinyVector("first", (True,) * 384),),
        (
            MLXGteTinyVector("first", (0.25,) * 384),
            MLXGteTinyVector("first", (0.5,) * 384),
        ),
    ),
)
def test_result_validation_rejects_invalid_vectors(
    vectors: tuple[MLXGteTinyVector, ...],
) -> None:
    with pytest.raises(EmbeddingExecutionError, match="result"):
        validate_gte_tiny_vectors(
            (EmbeddingInputItem("first", "alpha"),),
            vectors,
            limits=MLXGteTinyLimits(),
        )


def test_limits_are_positive_and_stop_oversized_input_before_tokenization() -> None:
    limits = MLXGteTinyLimits()
    assert limits.max_items > 0
    assert limits.max_item_bytes > 0
    assert limits.max_batch_bytes > 0
    assert limits.max_tokens == 512
    assert limits.vector_dimension == 384
    assert limits.max_observed_memory_bytes > 0

    with pytest.raises(EmbeddingExecutionError, match="input"):
        validate_gte_tiny_vectors(
            (EmbeddingInputItem("first", "x" * (limits.max_item_bytes + 1)),),
            (),
            limits=limits,
        )
