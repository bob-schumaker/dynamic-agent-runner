"""Tests for the parent-only generic co-located worker factory."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from dynamic_agent_runner.local_model_preparation import (
    LocalModelArtifact,
    LocalModelPreparationRecipe,
    PreparedArtifactSet,
)
from dynamic_agent_runner.workflow_host.descriptor import DeclaredInputConverter
from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
    GenerationResourceBudget,
    GenerationRunnerCapability,
)
from dynamic_agent_runner.workflow_host.generation_worker import (
    GenerationWorkerProtocolError,
)
from dynamic_agent_runner.workflow_host.generation_worker_assets import (
    GenerationWorkerAssetHandleService,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


def _capability() -> GenerationRunnerCapability:
    return GenerationRunnerCapability(
        runner_id="runner-v1",
        max_effective_context_tokens=32,
        memory_admission_method="process_hard_limit",
        pre_packing_containment_method="process_hard_limit",
        supported_execution_devices=frozenset({"cpu"}),
        worker_protocol="generation-worker-v1",
        bootstrap_hard_limit_method="process_hard_limit",
        generation_hard_limit_method="process_hard_limit",
    )


def _factory_arguments(tmp_path) -> dict[str, object]:
    package_root = tmp_path / "package"
    package_root.mkdir()
    converter_path = package_root / "converter.py"
    converter_contents = b"converter = object()\n"
    converter_path.write_bytes(converter_contents)
    payload_path = tmp_path / "payload"
    payload_contents = b"sealed payload"
    payload_path.write_bytes(payload_contents)
    material_path = tmp_path / "material"
    material_contents = b"{}"
    material_path.write_bytes(material_contents)
    converter = DeclaredInputConverter(
        converter_id="converter-v1",
        converter_contract_version="1",
        compatible_runner_contract_id="runner-v1",
        entrypoint="converter.py",
        asset_digest=sha256(converter_contents).hexdigest(),
        max_input_bytes=64,
        max_output_bytes=64,
        timeout_seconds=1,
    )
    prepared_set = PreparedArtifactSet(
        LocalModelPreparationRecipe(
            model_id="model-v1",
            adapter_id="adapter-v1",
            runner_id="runner-v1",
            artifacts=(
                LocalModelArtifact(
                    role="material",
                    repo_id="test/model",
                    revision="0" * 40,
                    filename="material",
                    sha256=sha256(material_contents).hexdigest(),
                ),
            ),
            transformation=None,
        ),
        {"material": material_path},
    )
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return {
        "capability": _capability(),
        "asset_handles": GenerationWorkerAssetHandleService(
            store=PrivateStateStore(tmp_path / "state"), owner="test-owner"
        ),
        "invocation_digest": "a" * 64,
        "fragment_index": 0,
        "converter": converter,
        "package_root": package_root,
        "prepared_set": prepared_set,
        "sealed_payload_path": payload_path,
        "sealed_payload_digest": sha256(payload_contents).hexdigest(),
        "material_lock_digest": "d" * 64,
        "execution_descriptor_digest": "e" * 64,
        "execution_device": "cpu",
        "budget": GenerationResourceBudget(4, 1, 8, 64, 32, 1_000, 1_024),
        "expires_at": now + timedelta(minutes=1),
        "now": now,
    }


def test_factory_issues_one_bound_opaque_co_location_handle(tmp_path) -> None:
    from dynamic_agent_runner.workflow_host.generation_worker_factory import (
        GenerationWorkerCoLocatedFactory,
    )

    arguments = _factory_arguments(tmp_path)
    descriptor = GenerationWorkerCoLocatedFactory(
        **arguments
    ).create_launch_descriptor()

    assert descriptor.runner_id == "runner-v1"
    assert descriptor.capability_contract_digest == _capability().contract_digest
    assert descriptor.converter_id == "converter-v1"
    assert descriptor.asset_handles
    assert all("/" not in handle for handle in descriptor.asset_handles)


@pytest.mark.parametrize(
    "changes",
    (
        {"capability": object()},
        {"converter": object()},
        {"package_root": "/tmp/package"},
        {"prepared_set": object()},
        {"sealed_payload_path": b"sealed payload"},
        {"execution_device": "mps"},
    ),
)
def test_factory_rejects_unbound_or_incompatible_child_inputs(
    tmp_path, changes
) -> None:
    from dynamic_agent_runner.workflow_host.generation_worker_factory import (
        GenerationWorkerCoLocatedFactory,
    )

    arguments = _factory_arguments(tmp_path)
    arguments.update(changes)

    with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
        GenerationWorkerCoLocatedFactory(**arguments)
