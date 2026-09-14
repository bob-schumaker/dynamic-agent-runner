"""Exact matrix-admission evidence for the sealed MLE8 package."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from dynamic_agent_runner.workflow_host.capabilities import CapabilityRequirements
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.model_materials import (
    parse_model_dependency_lock,
)


_PACKAGE = (
    Path(__file__).parent / "fixtures" / "mlx-all-distilroberta-v1" / "mle8-package"
)


def _json(name: str) -> dict[str, object]:
    value = json.loads((_PACKAGE / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _matches_package(
    row: dict[str, object],
    *,
    lock: object,
    descriptor: object,
    requirements: CapabilityRequirements,
) -> bool:
    required = next(
        item
        for item in requirements.required_capabilities
        if item.capability_id == "embedding.execute.v1"
    )
    return (
        row.get("package_id") == lock.logical_model_id  # type: ignore[attr-defined]
        and row.get("material_lock_digest") == lock.digest  # type: ignore[attr-defined]
        and row.get("execution_descriptor_digest") == descriptor.digest  # type: ignore[attr-defined]
        and row.get("architecture_abi") == descriptor.architecture_abi.to_mapping()  # type: ignore[attr-defined]
        and row.get("required_material_roles") == list(descriptor.material_roles)  # type: ignore[attr-defined]
        and row.get("required_capability")
        == {
            "id": required.capability_id,
            "version": required.contract_version,
            "contract_digest": required.contract_digest,
            "required_features": list(required.required_features),
        }
    )


def test_mle8_matrix_row_is_bound_to_the_exact_supported_package() -> None:
    row = _json("support-matrix-row.json")
    lock = parse_model_dependency_lock(_json("model-materials.json"))
    descriptor = parse_execution_descriptor(_json("execution-descriptor.json"))
    requirements = CapabilityRequirements.from_mapping(
        _json("capability-requirements.json")
    )

    assert row["profile_id"] == "embedding-index-sealed-v1"
    assert row["workflow_family"] == "embedding-index"
    assert row["test_mode"] == "darwin-mlx-competency"
    assert row["status"] == "supported"
    assert _matches_package(
        row, lock=lock, descriptor=descriptor, requirements=requirements
    )
    receipt = _PACKAGE / str(row["receipt_filename"])
    assert sha256(receipt.read_bytes()).hexdigest() == row["receipt_sha256"]


def test_different_package_or_material_cannot_inherit_the_mle8_matrix_row() -> None:
    row = _json("support-matrix-row.json")
    lock = parse_model_dependency_lock(_json("model-materials.json"))
    descriptor = parse_execution_descriptor(_json("execution-descriptor.json"))
    requirements = CapabilityRequirements.from_mapping(
        _json("capability-requirements.json")
    )
    other_package = dict(row)
    other_package["package_id"] = "other-embedding-package"
    changed_material = _json("model-materials.json")
    sources = changed_material["sources"]
    assert isinstance(sources, list)
    assert isinstance(sources[0], dict)
    sources[0]["sha256"] = "e" * 64
    changed_lock = parse_model_dependency_lock(changed_material)

    assert not _matches_package(
        other_package, lock=lock, descriptor=descriptor, requirements=requirements
    )
    assert not _matches_package(
        row, lock=changed_lock, descriptor=descriptor, requirements=requirements
    )
