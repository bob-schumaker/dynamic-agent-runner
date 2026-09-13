"""Tests for the sealed generic MLX BERT encoder descriptor ABI."""

from __future__ import annotations

import pytest

from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptorError,
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.mlx_embedding_abi import (
    BERT_ENCODER_MLX_V1_ABI,
    BERT_ENCODER_MLX_V2_ABI,
    BERT_ENCODER_MLX_V3_ABI,
    BertEncoderMlxV1DescriptorValidator,
    BertEncoderMlxV2DescriptorValidator,
    BertEncoderMlxV3DescriptorValidator,
    _bert_dtype_details,
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
    if abi in (BERT_ENCODER_MLX_V2_ABI, BERT_ENCODER_MLX_V3_ABI):
        encoder.update(dtype="float16", layer_norm_dtype="float32")
    normalization = "nfc"
    if abi == BERT_ENCODER_MLX_V3_ABI:
        normalization = "nfc-lowercase-strip-accents"
    return parse_execution_descriptor(
        {
            "format_version": 1,
            "architecture_abi": abi.to_mapping(),
            "material_roles": ["tokenizer", "weights"],
            "abi_fields": {
                "tokenizer": {
                    "role": "tokenizer",
                    "format": "wordpiece-json-v1",
                    "normalization": normalization,
                    "pre_tokenizer": "bert-basic-v1",
                    "special_token_ids": {
                        "cls": 101,
                        "sep": 102,
                        "pad": 0,
                        "unk": 100,
                    },
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
