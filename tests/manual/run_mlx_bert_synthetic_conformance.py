"""Run the generic BERT MLX ABI against its sealed synthetic fixture."""

from __future__ import annotations

import hashlib
import json
import math
import resource
import struct
import time
from pathlib import Path
from typing import Any

from dynamic_agent_runner.local_models import EmbeddingInputItem
from dynamic_agent_runner.mlx_local_embedding import MLXPreparedEmbeddingArtifacts
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.mlx_embedding_abi import (
    BERT_ENCODER_MLX_V1_ABI,
    BertEncoderMlxV1EmbeddingBackend,
    _bert_tensor_shapes,
    _tokenize_wordpiece_items,
)


_ROOT = Path(__file__).parents[2]
_FIXTURE_ROOT = _ROOT / "tests" / "fixtures" / "mlx-bert-synthetic"
_DESCRIPTOR_PATH = _FIXTURE_ROOT / "execution-descriptor.json"
_FIXTURE_PATH = _FIXTURE_ROOT / "conformance-fixture.json"


def main() -> int:
    """Execute the authorized local competency check without network access."""

    descriptor_mapping = _load_json(_DESCRIPTOR_PATH)
    fixture = _load_json(_FIXTURE_PATH)
    _validate_contract(descriptor_mapping, fixture, _FIXTURE_PATH)
    descriptor = parse_execution_descriptor(descriptor_mapping)
    materials = MLXPreparedEmbeddingArtifacts(
        execution_abi_id=BERT_ENCODER_MLX_V1_ABI.abi_id,
        execution_abi_version=BERT_ENCODER_MLX_V1_ABI.version,
        execution_abi_contract_digest=BERT_ENCODER_MLX_V1_ABI.contract_digest,
        execution_descriptor_digest=descriptor.digest,
        material_lock_digest="0" * 64,
        execution_descriptor=descriptor,
    )
    tokenizer = _tokenizer_bytes()
    weights = _weights_bytes(descriptor)
    items = tuple(
        EmbeddingInputItem(item["id"], item["text"]) for item in fixture["texts"]
    )
    token_ids, masks = _tokenize_wordpiece_items(
        json.loads(tokenizer), items, descriptor
    )
    _validate_token_evidence(token_ids, masks, fixture)
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    started = time.monotonic()
    result = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=lambda role: tokenizer if role == "tokenizer" else weights
    ).embed(items, materials)
    duration_ms = round((time.monotonic() - started) * 1000, 3)
    after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    max_error = _validate_vectors(result, fixture)
    try:
        import mlx.core as mx
    except Exception as error:  # noqa: BLE001 - redacted competency boundary.
        raise RuntimeError("MLX conformance runtime is unavailable") from error
    evidence = {
        "descriptor_digest": descriptor.digest,
        "duration_ms": duration_ms,
        "fixture_digest": hashlib.sha256(_FIXTURE_PATH.read_bytes()).hexdigest(),
        "max_abs_error": max_error,
        "max_rss_bytes": max(before, after),
        "mlx_version": mx.__version__,
        "padding_tokens": fixture["padding"]["padding_tokens"],
        "shape": [len(result.items), len(result.items[0].vector)],
        "truncation_tokens": fixture["truncation"]["token_count"],
    }
    print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
    return 0


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("synthetic conformance fixture is invalid")
    return value


def _validate_contract(
    descriptor: dict[str, Any], fixture: dict[str, Any], fixture_path: Path
) -> None:
    try:
        conformance = descriptor["abi_fields"]["conformance"]
        valid = (
            descriptor["architecture_abi"] == BERT_ENCODER_MLX_V1_ABI.to_mapping()
            and descriptor["material_roles"] == ["tokenizer", "weights"]
            and conformance["fixture_filename"] == fixture_path.name
            and conformance["fixture_sha256"]
            == hashlib.sha256(fixture_path.read_bytes()).hexdigest()
            and fixture["format_version"] == 1
            and fixture["max_error"] == conformance["max_error"]
            and fixture["padding"] == {"item_id": "padded", "padding_tokens": 1}
            and fixture["truncation"] == {"item_id": "truncated", "token_count": 4}
            and fixture["expected_vectors"]
            == [
                {"id": "padded", "vector": [1.0, -1.0]},
                {"id": "truncated", "vector": [1.0, -1.0]},
            ]
        )
    except (KeyError, TypeError):
        valid = False
    if not valid:
        raise RuntimeError("synthetic conformance fixture is invalid")


def _tokenizer_bytes() -> bytes:
    vocab = {
        "[PAD]"
        if index == 0
        else "[UNK]"
        if index == 100
        else "[CLS]"
        if index == 101
        else "[SEP]"
        if index == 102
        else f"token-{index}": index
        for index in range(200)
    }
    vocab.update({"alpha": 103, "beta": 104, "gamma": 105, "delta": 106})
    for index in range(103, 107):
        del vocab[f"token-{index}"]
    return json.dumps(
        {
            "model": {"type": "WordPiece", "unk_token": "[UNK]", "vocab": vocab},
            "normalizer": {"type": "BertNormalizer", "lowercase": False},
            "pre_tokenizer": {"type": "BertPreTokenizer"},
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _weights_bytes(descriptor: object) -> bytes:
    shapes = _bert_tensor_shapes(descriptor)
    header: dict[str, dict[str, object]] = {}
    cursor = 0
    payload = bytearray(sum(4 * math.prod(shape) for shape in shapes.values()))
    for name, shape in shapes.items():
        size = 4 * math.prod(shape)
        header[name] = {
            "data_offsets": [cursor, cursor + size],
            "dtype": "F32",
            "shape": list(shape),
        }
        cursor += size
    word_offset = header["embeddings.word_embeddings.weight"]["data_offsets"][0]
    assert isinstance(word_offset, int)
    struct.pack_into("<2f", payload, word_offset + 101 * 2 * 4, 1.0, -1.0)
    for name in (
        "embeddings.LayerNorm.weight",
        "encoder.layer.0.attention.output.LayerNorm.weight",
        "encoder.layer.0.output.LayerNorm.weight",
    ):
        offset = header[name]["data_offsets"][0]
        assert isinstance(offset, int)
        struct.pack_into("<2f", payload, offset, 1.0, 1.0)
    header_bytes = json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
    return len(header_bytes).to_bytes(8, "little") + header_bytes + payload


def _validate_token_evidence(
    token_ids: list[list[int]], masks: list[list[int]], fixture: dict[str, Any]
) -> None:
    if (
        len(token_ids) != 2
        or any(len(item) != 4 for item in token_ids)
        or masks[0].count(0) != fixture["padding"]["padding_tokens"]
        or sum(masks[1]) != fixture["truncation"]["token_count"]
    ):
        raise RuntimeError("synthetic conformance token evidence is invalid")


def _validate_vectors(result: object, fixture: dict[str, Any]) -> float:
    items = getattr(result, "items", ())
    expected = fixture["expected_vectors"]
    if len(items) != len(expected):
        raise RuntimeError("synthetic conformance result is invalid")
    maximum = 0.0
    for actual, reference in zip(items, expected, strict=True):
        if actual.id != reference["id"] or len(actual.vector) != len(
            reference["vector"]
        ):
            raise RuntimeError("synthetic conformance result is invalid")
        maximum = max(
            maximum,
            *(
                abs(value - expected_value)
                for value, expected_value in zip(
                    actual.vector, reference["vector"], strict=True
                )
            ),
        )
    if maximum > fixture["max_error"]:
        raise RuntimeError("synthetic conformance tolerance exceeded")
    return maximum


if __name__ == "__main__":
    raise SystemExit(main())
