"""Fake-only contract tests for the closed MLX RoBERTa embedding ABI."""

from __future__ import annotations

import json

import pytest

from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptorError,
    ExecutionDescriptorValidatorRegistry,
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.mlx_roberta_embedding_abi import (
    ROBERTA_ENCODER_MLX_V1_ABI,
    RobertaEncoderMlxV1DescriptorValidator,
    _parse_roberta_byte_level_bpe,
    _roberta_position_ids,
    _tokenize_roberta_byte_level_bpe_items,
)
from dynamic_agent_runner.local_models import EmbeddingInputItem


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


def _tokenizer_assets() -> tuple[bytes, bytes]:
    vocab = {
        "<s>": 0,
        "<pad>": 1,
        "</s>": 2,
        "<unk>": 3,
        "<mask>": 4,
        "h": 5,
        "i": 6,
        "Ġ": 7,
        "Ġh": 8,
        "Ġhi": 9,
        "!": 10,
        "Ã": 11,
        "©": 12,
        "Ã©": 13,
    }
    return (
        json.dumps(vocab, sort_keys=True).encode("utf-8"),
        b"#version: 0.2\n\xc4\xa0 h\n\xc4\xa0h i\n\xc3\x83 \xc2\xa9\n",
    )


def test_byte_level_bpe_vectors_preserve_leading_space_and_utf8_bytes() -> None:
    descriptor = _descriptor()
    descriptor.abi_fields["limits"]["max_tokens"] = 6
    descriptor.abi_fields["encoder"]["vocab_size"] = 14
    descriptor.abi_fields["tokenizer"]["special_token_ids"] = {
        "bos": 0,
        "eos": 2,
        "pad": 1,
        "unk": 3,
        "mask": 4,
    }
    vocab, merges = _tokenizer_assets()
    tokenizer = _parse_roberta_byte_level_bpe(vocab, merges, descriptor)

    token_ids, masks = _tokenize_roberta_byte_level_bpe_items(
        tokenizer,
        (
            EmbeddingInputItem("plain", "hi"),
            EmbeddingInputItem("space", " hi"),
            EmbeddingInputItem("unicode", "é!"),
        ),
        descriptor,
    )

    assert token_ids == [
        [0, 5, 6, 2, 1, 1],
        [0, 9, 2, 1, 1, 1],
        [0, 13, 10, 2, 1, 1],
    ]
    assert masks == [
        [1, 1, 1, 1, 0, 0],
        [1, 1, 1, 0, 0, 0],
        [1, 1, 1, 1, 0, 0],
    ]


def test_byte_level_bpe_rejects_malformed_or_unbounded_execution_assets() -> None:
    descriptor = _descriptor()
    vocab, merges = _tokenizer_assets()

    with pytest.raises(ValueError):
        _parse_roberta_byte_level_bpe(vocab, b"not-a-header\n", descriptor)
    with pytest.raises(ValueError):
        _parse_roberta_byte_level_bpe(
            vocab, merges + b"duplicate merge\nduplicate merge\n", descriptor
        )
    with pytest.raises(ValueError):
        _parse_roberta_byte_level_bpe(
            json.dumps({"<s>": 0, "<pad>": 1}).encode(), merges, descriptor
        )


def test_roberta_position_ids_skip_padding_from_its_padding_index() -> None:
    assert _roberta_position_ids([[0, 5, 2, 1], [1, 0, 2, 1]], pad_id=1) == [
        [2, 3, 4, 1],
        [1, 2, 3, 1],
    ]
