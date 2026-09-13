"""Offline admission coverage for the approved MLX multilingual E5 package."""

from __future__ import annotations

import json
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
    ExecutionDescriptorValidatorRegistry,
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.mlx_embedding_abi import (
    BERT_ENCODER_MLX_V4_ABI,
    BertEncoderMlxV4DescriptorValidator,
)
from dynamic_agent_runner.workflow_host.mlx_v4_weight_preparation import (
    MLX_V4_WEIGHT_PREPARATION_CONTRACT,
    MLX_V4_WEIGHT_PREPARATION_CONTRACT_DIGEST,
)
from dynamic_agent_runner.workflow_host.model_execution_binding import (
    ModelExecutionBindingError,
    derive_model_execution_binding,
)
from dynamic_agent_runner.workflow_host.model_materials import (
    parse_model_dependency_lock,
)


_PACKAGE = (
    Path(__file__).parent / "fixtures" / "mlx-multilingual-e5-small" / "mle7-package"
)
_SOURCE = "intfloat/multilingual-e5-small"
_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
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


def _validators() -> ExecutionDescriptorValidatorRegistry:
    return ExecutionDescriptorValidatorRegistry(
        (BertEncoderMlxV4DescriptorValidator(),)
    )


def test_approved_multilingual_e5_package_is_admitted_without_mlx_or_material_io() -> (
    None
):
    lock = _lock()
    descriptor = _descriptor()
    requirements = _requirements()

    assert lock.format_version == 2
    assert lock.logical_model_id == "mlx-multilingual-e5-small-embedding-v1"
    assert [(source.role, source.filename) for source in lock.sources] == [
        ("bert_config", "config.json"),
        ("modules_manifest", "modules.json"),
        ("pooling_config", "1_Pooling/config.json"),
        ("sentence_transformer_config", "sentence_bert_config.json"),
        ("source_weights", "model.safetensors"),
        ("tokenizer", "sentencepiece.bpe.model"),
        ("tokenizer_config", "tokenizer_config.json"),
        ("tokenizer_special_tokens", "special_tokens_map.json"),
    ]
    assert all(
        source.repository == _SOURCE and source.revision == _REVISION
        for source in lock.sources
    )
    assert len(lock.preparation) == 1
    operation = lock.preparation[0]
    assert operation.capability_id == MLX_V4_WEIGHT_PREPARATION_CONTRACT.contract_id
    assert operation.contract_version == MLX_V4_WEIGHT_PREPARATION_CONTRACT.version
    assert operation.contract_digest == MLX_V4_WEIGHT_PREPARATION_CONTRACT_DIGEST
    assert operation.inputs == ("source_weights",)
    assert (operation.output.role, operation.output.filename) == (
        "weights",
        "model.safetensors",
    )
    assert lock.execution_descriptor is not None
    assert lock.execution_descriptor.sha256 == descriptor.digest
    BertEncoderMlxV4DescriptorValidator().validate(descriptor)
    assert descriptor.architecture_abi == BERT_ENCODER_MLX_V4_ABI
    assert requirements.bindings == {"runner": _EMBEDDING_CAPABILITY}
    assert [
        requirement.capability_id for requirement in requirements.required_capabilities
    ] == [
        _EMBEDDING_CAPABILITY,
        MLX_V4_WEIGHT_PREPARATION_CONTRACT.contract_id,
    ]
    approval = (_PACKAGE / "mle7-approval.md").read_text(encoding="utf-8")
    assert "MIT" in approval
    assert _REVISION in approval


@pytest.mark.parametrize("role", ("source_weights", "tokenizer"))
def test_changed_material_cannot_match_the_approved_package_identity(role: str) -> None:
    approved = _lock()
    changed = _json("model-materials.json")
    sources = changed["sources"]
    assert isinstance(sources, list)
    source = next(item for item in sources if item["role"] == role)
    assert isinstance(source, dict)
    source["sha256"] = "e" * 64

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
        BertEncoderMlxV4DescriptorValidator().validate(
            parse_execution_descriptor(changed_descriptor)
        )

    with pytest.raises(ModelExecutionBindingError, match="runner_unavailable"):
        derive_model_execution_binding(
            lock=lock,
            requirements=requirements,
            execution_descriptor=parse_execution_descriptor(changed_descriptor),
            descriptor_validators=_validators(),
        )

    with pytest.raises(EmbeddingExecutionBindingError, match="unavailable"):
        derive_embedding_execution_binding(
            model_binding=derive_model_execution_binding(
                lock=lock,
                requirements=requirements,
                execution_descriptor=descriptor,
                descriptor_validators=_validators(),
            ),
            requirements=CapabilityRequirements(
                (
                    CapabilityRequirement(
                        "other.execute.v1", "1", "d" * 64, ("deterministic",)
                    ),
                ),
                {"runner": "other.execute.v1"},
            ),
        )
