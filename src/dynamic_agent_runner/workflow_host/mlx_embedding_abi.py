"""Pure descriptor validation for the generic MLX BERT encoder ABI."""

from __future__ import annotations

import math
import json
from collections.abc import Mapping
from collections.abc import Callable, Sequence
from typing import Protocol

from dynamic_agent_runner.errors import EmbeddingExecutionError
from dynamic_agent_runner.local_models import EmbeddingInputItem
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptor,
    ExecutionDescriptorAbi,
    ExecutionDescriptorError,
)


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


def _mapping(value: object, keys: set[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != keys:
        _invalid()
    return value


class _EmbeddingMaterialReceipt(Protocol):
    execution_descriptor: ExecutionDescriptor


class BertEncoderMlxV1EmbeddingBackend:
    """Validate sealed artifacts before any injected tokenizer or encoder call."""

    def __init__(
        self,
        *,
        artifact_reader: Callable[[str], bytes],
        tokenizer: Callable[[tuple[EmbeddingInputItem, ...]], object],
        encoder: Callable[[object], object],
    ) -> None:
        self._artifact_reader = artifact_reader
        self._tokenizer = tokenizer
        self._encoder = encoder

    def embed(
        self,
        items: Sequence[EmbeddingInputItem],
        materials: _EmbeddingMaterialReceipt,
    ) -> object:
        """Reject malformed tokenizer material before any execution collaborator."""

        try:
            if not isinstance(materials.execution_descriptor, ExecutionDescriptor):
                raise ValueError
            tokenizer_bytes = self._artifact_reader("tokenizer")
            if not isinstance(tokenizer_bytes, bytes):
                raise ValueError
            value = json.loads(tokenizer_bytes.decode("utf-8"))
            if not isinstance(value, Mapping):
                raise ValueError
            weights = self._artifact_reader("weights")
            if not isinstance(weights, bytes) or len(weights) < 8:
                raise ValueError
            header_size = int.from_bytes(weights[:8], "little")
            if header_size > 16 * 1024 * 1024 or len(weights) < 8 + header_size:
                raise ValueError
            header = json.loads(weights[8 : 8 + header_size].decode("utf-8"))
            if not isinstance(header, Mapping):
                raise ValueError
        except Exception as error:  # noqa: BLE001 - sealed artifact boundary.
            raise EmbeddingExecutionError(
                "MLX embedding material is unavailable"
            ) from error
        raise EmbeddingExecutionError("MLX embedding backend is unavailable")


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
