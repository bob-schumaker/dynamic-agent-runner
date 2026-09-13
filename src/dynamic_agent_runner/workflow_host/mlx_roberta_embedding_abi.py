"""Pure descriptor validation for the closed MLX RoBERTa encoder ABI."""

from __future__ import annotations

import math
from collections.abc import Mapping

from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptor,
    ExecutionDescriptorAbi,
    ExecutionDescriptorError,
)


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
