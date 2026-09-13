"""Offline admission coverage for the approved MLX GTE Tiny package."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from dynamic_agent_runner.workflow_host.capabilities import (
    CapabilityRequirement,
    CapabilityRequirements,
)
from dynamic_agent_runner.workflow_host.embedding_execution import (
    EmbeddingExecutionBindingError,
    derive_embedding_execution_binding,
)
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptorError,
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.mlx_embedding_abi import (
    BertEncoderMlxV1DescriptorValidator,
)
from dynamic_agent_runner.workflow_host.model_execution_binding import (
    ModelExecutionBindingError,
    derive_model_execution_binding,
)
from dynamic_agent_runner.workflow_host.model_materials import (
    parse_model_dependency_lock,
)


_PACKAGE = Path(__file__).parent / "fixtures" / "mlx-gte-tiny" / "mle6-package"
_SOURCE = "TaylorAI/gte-tiny"
_REVISION = "4cc5e73d86a67c601897257b467187234aa3bca3"
_EMBEDDING_CAPABILITY = "embedding.execute.v1"


def _json(name: str) -> dict[str, object]:
    value = json.loads((_PACKAGE / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _lock():
    return parse_model_dependency_lock(_json("model-materials.json"))


def _descriptor():
    return parse_execution_descriptor(_json("execution-descriptor.json"))


def _requirements() -> CapabilityRequirements:
    return CapabilityRequirements.from_mapping(_json("capability-requirements.json"))


def test_approved_gte_tiny_v2_package_is_admitted_without_mlx_or_material_io() -> None:
    lock = _lock()
    descriptor = _descriptor()
    requirements = _requirements()
    documents = _json("synthetic-documents.json")

    assert lock.format_version == 2
    assert lock.logical_model_id == "mlx-gte-tiny-embedding-v1"
    assert [(source.role, source.filename) for source in lock.sources] == [
        ("bert_config", "config.json"),
        ("modules_manifest", "modules.json"),
        ("pooling_config", "1_Pooling/config.json"),
        ("sentence_transformer_config", "sentence_bert_config.json"),
        ("tokenizer", "tokenizer.json"),
        ("tokenizer_added_tokens", "added_tokens.json"),
        ("tokenizer_config", "tokenizer_config.json"),
        ("tokenizer_special_tokens", "special_tokens_map.json"),
        ("tokenizer_vocab", "vocab.txt"),
        ("weights", "model.safetensors"),
    ]
    assert all(
        source.repository == _SOURCE and source.revision == _REVISION
        for source in lock.sources
    )
    assert lock.execution_descriptor is not None
    assert lock.execution_descriptor.sha256 == descriptor.digest
    BertEncoderMlxV1DescriptorValidator().validate(descriptor)
    conformance = descriptor.abi_fields["conformance"]
    assert isinstance(conformance, dict)
    assert (
        conformance["fixture_sha256"]
        == sha256((_PACKAGE / "conformance-fixture.json").read_bytes()).hexdigest()
    )
    assert requirements.bindings == {"runner": _EMBEDDING_CAPABILITY}
    assert [
        requirement.capability_id for requirement in requirements.required_capabilities
    ] == [_EMBEDDING_CAPABILITY]
    assert documents == {
        "documents": [
            {"id": "empty", "text": ""},
            {"id": "ascii", "text": "The quick brown fox jumps over the lazy dog."},
            {"id": "unicode", "text": "Café naïve — punctuation!"},
        ],
        "format_version": 1,
    }


def test_changed_material_cannot_match_the_approved_package_identity() -> None:
    approved = _lock()
    changed = _json("model-materials.json")
    sources = changed["sources"]
    assert isinstance(sources, list)
    assert isinstance(sources[0], dict)
    sources[0]["sha256"] = "e" * 64

    assert parse_model_dependency_lock(changed).digest != approved.digest


def test_changed_descriptor_or_capability_rejects_before_model_execution() -> None:
    lock = _lock()
    descriptor = _descriptor()
    requirements = _requirements()

    changed_descriptor = _json("execution-descriptor.json")
    abi = changed_descriptor["architecture_abi"]
    assert isinstance(abi, dict)
    abi["id"] = "other-encoder-v1"
    with pytest.raises(ExecutionDescriptorError, match="ABI fields"):
        BertEncoderMlxV1DescriptorValidator().validate(
            parse_execution_descriptor(changed_descriptor)
        )

    with pytest.raises(ModelExecutionBindingError, match="runner_unavailable"):
        derive_model_execution_binding(
            lock=lock,
            requirements=requirements,
            execution_descriptor=parse_execution_descriptor(changed_descriptor),
            descriptor_validators=_descriptor_validators(),
        )

    with pytest.raises(EmbeddingExecutionBindingError, match="unavailable"):
        derive_embedding_execution_binding(
            model_binding=_model_binding(lock, descriptor, requirements),
            requirements=CapabilityRequirements(
                (
                    CapabilityRequirement(
                        "other.execute.v1", "1", "d" * 64, ("deterministic",)
                    ),
                ),
                {"runner": "other.execute.v1"},
            ),
        )


def _descriptor_validators():
    from dynamic_agent_runner.workflow_host.execution_descriptors import (
        ExecutionDescriptorValidatorRegistry,
    )

    return ExecutionDescriptorValidatorRegistry(
        (BertEncoderMlxV1DescriptorValidator(),)
    )


def _model_binding(lock, descriptor, requirements):
    return derive_model_execution_binding(
        lock=lock,
        requirements=requirements,
        execution_descriptor=descriptor,
        descriptor_validators=_descriptor_validators(),
    )
