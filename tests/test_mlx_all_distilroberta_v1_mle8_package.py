"""Offline admission coverage for the approved MLE8 RoBERTa package."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dynamic_agent_runner.workflow_host.capabilities import CapabilityRequirements
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptorError,
    ExecutionDescriptorValidatorRegistry,
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.mlx_roberta_embedding_abi import (
    ROBERTA_ENCODER_MLX_V1_ABI,
    RobertaEncoderMlxV1DescriptorValidator,
)
from dynamic_agent_runner.workflow_host.mlx_roberta_weight_preparation import (
    MLX_ROBERTA_V1_WEIGHT_PREPARATION_CONTRACT,
    MLX_ROBERTA_V1_WEIGHT_PREPARATION_CONTRACT_DIGEST,
)
from dynamic_agent_runner.workflow_host.model_materials import (
    parse_model_dependency_lock,
)


_PACKAGE = (
    Path(__file__).parent / "fixtures" / "mlx-all-distilroberta-v1" / "mle8-package"
)
_REVISION = "842eaed40bee4d61673a81c92d5689a8fed7a09f"


def _json(name: str) -> dict[str, object]:
    value = json.loads((_PACKAGE / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_approved_mle8_package_is_bound_without_mlx_or_material_io() -> None:
    lock = parse_model_dependency_lock(_json("model-materials.json"))
    descriptor = parse_execution_descriptor(_json("execution-descriptor.json"))
    requirements = CapabilityRequirements.from_mapping(
        _json("capability-requirements.json")
    )

    assert lock.logical_model_id == "mlx-all-distilroberta-v1-embedding-v1"
    assert [source.role for source in lock.sources] == [
        "merges",
        "modules_manifest",
        "pooling_config",
        "roberta_config",
        "source_weights",
        "tokenizer_config",
        "tokenizer_special_tokens",
        "vocab",
    ]
    assert all(source.revision == _REVISION for source in lock.sources)
    assert (
        lock.preparation[0].capability_id
        == MLX_ROBERTA_V1_WEIGHT_PREPARATION_CONTRACT.contract_id
    )
    assert (
        lock.preparation[0].contract_digest
        == MLX_ROBERTA_V1_WEIGHT_PREPARATION_CONTRACT_DIGEST
    )
    assert lock.execution_descriptor is not None
    assert lock.execution_descriptor.sha256 == descriptor.digest
    RobertaEncoderMlxV1DescriptorValidator().validate(descriptor)
    assert descriptor.architecture_abi == ROBERTA_ENCODER_MLX_V1_ABI
    assert requirements.bindings == {"runner": "embedding.execute.v1"}
    assert "Apache-2.0" in (_PACKAGE / "mle8-approval.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("role", ("source_weights", "vocab", "merges"))
def test_changed_material_cannot_match_the_approved_package_identity(role: str) -> None:
    approved = parse_model_dependency_lock(_json("model-materials.json"))
    changed = _json("model-materials.json")
    sources = changed["sources"]
    assert isinstance(sources, list)
    source = next(item for item in sources if item["role"] == role)
    assert isinstance(source, dict)
    source["sha256"] = "e" * 64

    assert parse_model_dependency_lock(changed).digest != approved.digest


def test_changed_abi_rejects_before_model_execution() -> None:
    changed = _json("execution-descriptor.json")
    abi = changed["architecture_abi"]
    assert isinstance(abi, dict)
    abi["id"] = "other-encoder-v1"

    with pytest.raises(ExecutionDescriptorError, match="ABI is unavailable"):
        ExecutionDescriptorValidatorRegistry(
            (RobertaEncoderMlxV1DescriptorValidator(),)
        ).validate(parse_execution_descriptor(changed))
