"""Fake-only contract tests for the closed MLX RoBERTa embedding ABI."""

from __future__ import annotations

import pytest

from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptorError,
    ExecutionDescriptorValidatorRegistry,
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.mlx_roberta_embedding_abi import (
    ROBERTA_ENCODER_MLX_V1_ABI,
    RobertaEncoderMlxV1DescriptorValidator,
)


def _descriptor():
    return parse_execution_descriptor(
        {
            "format_version": 1,
            "architecture_abi": ROBERTA_ENCODER_MLX_V1_ABI.to_mapping(),
            "material_roles": ["merges", "vocab", "weights"],
            "abi_fields": {
                "tokenizer": {
                    "vocab_role": "vocab",
                    "merges_role": "merges",
                    "format": "roberta-byte-level-bpe-v1",
                    "pre_tokenizer": "gpt2-byte-level-v1",
                    "add_prefix_space": False,
                    "special_token_ids": {
                        "bos": 0,
                        "eos": 2,
                        "pad": 1,
                        "unk": 3,
                        "mask": 50_264,
                    },
                    "truncation": "longest-first",
                },
                "encoder": {
                    "weights_role": "weights",
                    "tensor_layout": "roberta-encoder-safetensors-v1",
                    "dtype": "float32",
                    "vocab_size": 50_265,
                    "hidden_size": 768,
                    "layers": 6,
                    "attention_heads": 12,
                    "intermediate_size": 3_072,
                    "max_positions": 514,
                    "type_vocab_size": 1,
                    "position_ids": "roberta-padding-index-v1",
                    "layer_norm_epsilon": 0.00001,
                },
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


def test_validator_accepts_the_closed_roberta_encoder_descriptor() -> None:
    descriptor = _descriptor()

    RobertaEncoderMlxV1DescriptorValidator().validate(descriptor)

    assert ROBERTA_ENCODER_MLX_V1_ABI.to_mapping() == {
        "id": "roberta-encoder-mlx-v1",
        "version": "1",
        "contract_digest": "7770aa3d61b26984d2e549f99092459935d0237f67cae2e8b176c0516ce04391",
    }


def test_validator_allows_only_the_closed_pooling_and_normalization_choices() -> None:
    descriptor = _descriptor()
    descriptor.abi_fields["pooling"] = "cls"
    descriptor.abi_fields["normalization"] = "none"

    ExecutionDescriptorValidatorRegistry(
        (RobertaEncoderMlxV1DescriptorValidator(),)
    ).validate(descriptor)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda fields: fields["tokenizer"].update(add_prefix_space=True),
        lambda fields: fields["tokenizer"].update(format="wordpiece-json-v1"),
        lambda fields: fields["encoder"].update(position_ids="sequence-index-v1"),
        lambda fields: fields["encoder"].update(layer_norm_epsilon=1e-12),
        lambda fields: fields["encoder"].update(type_vocab_size=2),
        lambda fields: fields["tokenizer"].update(tokenizer_json_role="tokenizer"),
    ),
)
def test_validator_rejects_alternate_or_executable_tokenizer_semantics(mutate) -> None:
    descriptor = _descriptor()
    mutate(descriptor.abi_fields)

    with pytest.raises(ExecutionDescriptorError, match="ABI fields"):
        RobertaEncoderMlxV1DescriptorValidator().validate(descriptor)
