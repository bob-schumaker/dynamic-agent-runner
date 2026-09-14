"""Tests for the sealed generic MLX BERT encoder descriptor ABI."""

from __future__ import annotations

import struct

import pytest

from dynamic_agent_runner.local_models import EmbeddingInputItem

from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptorError,
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.mlx_embedding_abi import (
    BERT_ENCODER_MLX_V1_ABI,
    BERT_ENCODER_MLX_V2_ABI,
    BERT_ENCODER_MLX_V3_ABI,
    BERT_ENCODER_MLX_V4_ABI,
    BertEncoderMlxV1DescriptorValidator,
    BertEncoderMlxV2DescriptorValidator,
    BertEncoderMlxV3DescriptorValidator,
    BertEncoderMlxV4DescriptorValidator,
    _bert_dtype_details,
    _normalize_sentencepiece_text,
    _parse_sentencepiece_unigram_model,
    _sentencepiece_normalizer_parts,
    _sentencepiece_unigram_ids,
    _tokenize_sentencepiece_unigram_items,
)


def _descriptor(*, abi=BERT_ENCODER_MLX_V1_ABI):
    encoder = {
        "weights_role": "weights",
        "tensor_layout": "bert-encoder-safetensors-v1",
        "dtype": "float32",
        "vocab_size": 30_522,
        "hidden_size": 768,
        "layers": 12,
        "attention_heads": 12,
        "intermediate_size": 3_072,
        "max_positions": 512,
        "type_vocab_size": 2,
    }
    if abi in (
        BERT_ENCODER_MLX_V2_ABI,
        BERT_ENCODER_MLX_V3_ABI,
        BERT_ENCODER_MLX_V4_ABI,
    ):
        encoder.update(dtype="float16", layer_norm_dtype="float32")
    normalization = "nfc"
    if abi == BERT_ENCODER_MLX_V3_ABI:
        normalization = "nfc-lowercase-strip-accents"
    if abi == BERT_ENCODER_MLX_V4_ABI:
        normalization = "nmt-nfkc"
    return parse_execution_descriptor(
        {
            "format_version": 1,
            "architecture_abi": abi.to_mapping(),
            "material_roles": ["tokenizer", "weights"],
            "abi_fields": {
                "tokenizer": {
                    "role": "tokenizer",
                    "format": (
                        "sentencepiece-unigram-model-v1"
                        if abi == BERT_ENCODER_MLX_V4_ABI
                        else "wordpiece-json-v1"
                    ),
                    "normalization": normalization,
                    "pre_tokenizer": (
                        "sentencepiece-unigram-v1"
                        if abi == BERT_ENCODER_MLX_V4_ABI
                        else "bert-basic-v1"
                    ),
                    **({"id_offset": 1} if abi == BERT_ENCODER_MLX_V4_ABI else {}),
                    "special_token_ids": (
                        {"cls": 0, "sep": 2, "pad": 1, "unk": 3}
                        if abi == BERT_ENCODER_MLX_V4_ABI
                        else {"cls": 101, "sep": 102, "pad": 0, "unk": 100}
                    ),
                    "truncation": "longest-first",
                },
                "encoder": encoder,
                "pooling": "masked_mean",
                "normalization": "l2",
                "limits": {
                    "max_items": 8,
                    "max_item_bytes": 1_024,
                    "max_aggregate_bytes": 8_192,
                    "max_tokens": 512,
                    "max_vectors": 8,
                    "max_memory_bytes": 1_000_000_000,
                    "max_tokenizer_bytes": 1_000_000,
                    "max_weights_bytes": 1_000_000_000,
                    "max_safetensors_header_bytes": 1_000_000,
                    "max_conformance_fixture_bytes": 1_000_000,
                },
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


def test_validator_accepts_the_closed_generic_bert_encoder_descriptor() -> None:
    descriptor = _descriptor()

    BertEncoderMlxV1DescriptorValidator().validate(descriptor)


def test_two_distinct_descriptors_are_accepted_by_the_same_abi() -> None:
    first = _descriptor()
    second = _descriptor()
    second.abi_fields["pooling"] = "cls"
    validator = BertEncoderMlxV1DescriptorValidator()

    validator.validate(first)
    validator.validate(second)

    assert first.architecture_abi == second.architecture_abi
    assert first.digest != second.digest


def test_v2_accepts_only_the_declared_float32_layer_norm_override() -> None:
    descriptor = _descriptor(abi=BERT_ENCODER_MLX_V2_ABI)

    BertEncoderMlxV2DescriptorValidator().validate(descriptor)


def test_v3_accepts_only_lowercase_accent_stripping_normalization() -> None:
    descriptor = _descriptor(abi=BERT_ENCODER_MLX_V3_ABI)

    BertEncoderMlxV3DescriptorValidator().validate(descriptor)


def test_v3_retains_the_v2_float32_layer_norm_tensor_rule() -> None:
    descriptor = _descriptor(abi=BERT_ENCODER_MLX_V3_ABI)

    assert _bert_dtype_details(descriptor, "embeddings.LayerNorm.weight") == (
        "F32",
        4,
    )


def test_v4_identifies_the_closed_sentencepiece_unigram_bert_descriptor() -> None:
    descriptor = _descriptor(abi=BERT_ENCODER_MLX_V4_ABI)

    BertEncoderMlxV4DescriptorValidator().validate(descriptor)
    assert BERT_ENCODER_MLX_V4_ABI.to_mapping() == {
        "id": "bert-encoder-mlx-v4",
        "version": "5",
        "contract_digest": "1db6568e50f14b1fd7752772573024e2da87518674cd78ba4f9c57cb84febb4f",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("format", "wordpiece-json-v1"),
        ("normalization", "nfc-lowercase-strip-accents"),
        ("pre_tokenizer", "bert-basic-v1"),
    ),
)
def test_v4_rejects_any_non_sentencepiece_tokenizer_contract(
    field: str, value: str
) -> None:
    descriptor = _descriptor(abi=BERT_ENCODER_MLX_V4_ABI)
    descriptor.abi_fields["tokenizer"][field] = value

    with pytest.raises(ExecutionDescriptorError, match="ABI fields"):
        BertEncoderMlxV4DescriptorValidator().validate(descriptor)


def test_sentencepiece_compiled_normalizer_applies_its_longest_prefix_map() -> None:
    units = [0] * 256
    units[0] = 1 << 10
    units[64] = ord("A") | (1 << 8) | (32 << 10)
    units[96] = 0
    units[194] = 0xC3 | (128 << 10)
    units[66] = 1 << 10
    units[235] = 0xA9 | (1 << 8) | (64 << 10)
    units[171] = 2
    charsmap = (
        (1_024).to_bytes(4, "little")
        + b"".join(unit.to_bytes(4, "little") for unit in units)
        + b"a\0x\0"
    )

    assert _normalize_sentencepiece_text("A", charsmap) == "▁a"
    assert _normalize_sentencepiece_text("é", charsmap) == "▁x"


def test_sentencepiece_unigram_admission_and_tokenization_are_sealed() -> None:
    descriptor = _descriptor(abi=BERT_ENCODER_MLX_V4_ABI)
    descriptor.abi_fields["limits"]["max_tokens"] = 5
    tokenizer = _parse_sentencepiece_unigram_model(_unigram_model_bytes(), descriptor)

    assert _sentencepiece_unigram_ids("a", tokenizer, 3) == [8]
    assert _sentencepiece_unigram_ids("ab", tokenizer, 3) == [4, 7]
    assert _sentencepiece_unigram_ids("z", tokenizer, 3) == [4, 3]
    assert _sentencepiece_unigram_ids("", tokenizer, 3) == []
    assert _sentencepiece_unigram_ids(" \t\n\u00a0", tokenizer, 3) == []
    assert _tokenize_sentencepiece_unigram_items(
        tokenizer,
        (EmbeddingInputItem(id="item", text="ab"),),
        descriptor,
    ) == ([[0, 4, 7, 2, 1]], [[1, 1, 1, 1, 0]])
    assert _tokenize_sentencepiece_unigram_items(
        tokenizer,
        (EmbeddingInputItem(id="empty", text=""),),
        descriptor,
    ) == ([[0, 2, 1, 1, 1]], [[1, 1, 0, 0, 0]])


def test_sentencepiece_unigram_rejects_unknown_modelproto_fields() -> None:
    descriptor = _descriptor(abi=BERT_ENCODER_MLX_V4_ABI)

    with pytest.raises(ValueError):
        _parse_sentencepiece_unigram_model(
            _unigram_model_bytes() + _protobuf_bytes(4, b"unknown"), descriptor
        )


def test_sentencepiece_normalizer_rejects_an_out_of_bounds_darts_offset() -> None:
    units = [0] * 256
    units[0] = 512 << 10
    charsmap = (
        (1_024).to_bytes(4, "little")
        + b"".join(unit.to_bytes(4, "little") for unit in units)
        + b"\0"
    )

    with pytest.raises(ValueError):
        _sentencepiece_normalizer_parts(charsmap)


def _unigram_model_bytes() -> bytes:
    pieces = (
        ("<unk>", -1.0, 2),
        ("<s>", -1.0, 3),
        ("</s>", -1.0, 3),
        ("▁", -1.0, 1),
        ("a", -2.0, 1),
        ("b", -3.0, 1),
        ("ab", 5.0, 1),
        ("▁a", 1.0, 1),
    )
    trainer = _protobuf_int(3, 1) + _protobuf_int(4, len(pieces))
    normalizer = (
        _protobuf_bytes(1, b"nmt_nfkc") + _protobuf_int(3, 1) + _protobuf_int(4, 1)
    )
    return b"".join(
        [
            *(
                _protobuf_bytes(
                    1,
                    _protobuf_bytes(1, piece.encode("utf-8"))
                    + _protobuf_fixed32(2, struct.pack("<f", score))
                    + _protobuf_int(3, kind),
                )
                for piece, score, kind in pieces
            ),
            _protobuf_bytes(2, trainer),
            _protobuf_bytes(3, normalizer),
        ]
    )


def _protobuf_bytes(field: int, value: bytes) -> bytes:
    return _protobuf_varint((field << 3) | 2) + _protobuf_varint(len(value)) + value


def _protobuf_int(field: int, value: int) -> bytes:
    return _protobuf_varint(field << 3) + _protobuf_varint(value)


def _protobuf_fixed32(field: int, value: bytes) -> bytes:
    return _protobuf_varint((field << 3) | 5) + value


def _protobuf_varint(value: int) -> bytes:
    encoded = bytearray()
    while value > 0x7F:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


@pytest.mark.parametrize(
    ("field", "value"),
    (("dtype", "float32"), ("layer_norm_dtype", "float16")),
)
def test_v2_rejects_other_precision_patterns(field: str, value: str) -> None:
    descriptor = _descriptor(abi=BERT_ENCODER_MLX_V2_ABI)
    descriptor.abi_fields["encoder"][field] = value

    with pytest.raises(ExecutionDescriptorError, match="ABI fields"):
        BertEncoderMlxV2DescriptorValidator().validate(descriptor)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda fields: fields.update(unexpected=True),
        lambda fields: fields["tokenizer"].update(role="weights"),
        lambda fields: fields["tokenizer"]["special_token_ids"].update(cls=100),
        lambda fields: fields["encoder"].update(attention_heads=7),
        lambda fields: fields["limits"].update(max_tokens=513),
        lambda fields: fields["conformance"].update(fixture_filename="elsewhere.json"),
        lambda fields: fields["conformance"].update(max_error=0.2),
    ),
)
def test_validator_rejects_closed_schema_and_cross_field_violations(mutate) -> None:
    descriptor = _descriptor()
    mutate(descriptor.abi_fields)

    with pytest.raises(ExecutionDescriptorError, match="ABI fields"):
        BertEncoderMlxV1DescriptorValidator().validate(descriptor)
