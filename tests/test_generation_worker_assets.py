"""Tests for host-private, descriptor-bound generation-worker assets."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from dataclasses import replace
from hashlib import sha256

import pytest

from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
    GenerationResourceBudget,
)
from dynamic_agent_runner.workflow_host.generation_worker import (
    GenerationWorkerLaunchDescriptor,
)
from dynamic_agent_runner.workflow_host.generation_worker_assets import (
    GenerationWorkerAssetHandleError,
    GenerationWorkerAssetHandleService,
)
from dynamic_agent_runner.workflow_host.descriptor import DeclaredInputConverter
from dynamic_agent_runner.local_model_preparation import (
    LocalModelArtifact,
    LocalModelPreparationRecipe,
    PreparedArtifactSet,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


def _descriptor(*, asset_handles: tuple[str, ...]) -> GenerationWorkerLaunchDescriptor:
    return GenerationWorkerLaunchDescriptor(
        protocol_version="generation-worker-v1",
        invocation_digest="a" * 64,
        fragment_index=0,
        runner_id="runner-v1",
        capability_contract_digest="b" * 64,
        converter_id="converter-v1",
        converter_asset_digest="c" * 64,
        material_lock_digest="d" * 64,
        execution_descriptor_digest="e" * 64,
        execution_device="cpu",
        budget=GenerationResourceBudget(4, 1, 8, 64, 32, 1_000, 1_024),
        asset_handles=asset_handles,
    )


def _service(tmp_path) -> GenerationWorkerAssetHandleService:
    return GenerationWorkerAssetHandleService(
        store=PrivateStateStore(tmp_path / "state"), owner="test-owner"
    )


def test_issued_asset_handle_resolves_only_for_its_exact_descriptor(tmp_path) -> None:
    asset = tmp_path / "converter.py"
    content = b"converter = object()\n"
    asset.write_bytes(content)
    service = _service(tmp_path)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    provisional = _descriptor(asset_handles=("placeholder",))
    handle = service.issue(
        descriptor=provisional,
        source_path=asset,
        expected_digest=sha256(content).hexdigest(),
        expires_at=now + timedelta(minutes=1),
        now=now,
    )
    descriptor = _descriptor(asset_handles=(handle,))

    assert service.resolve(handle=handle, descriptor=descriptor, now=now) == asset

    with pytest.raises(GenerationWorkerAssetHandleError, match="unavailable"):
        service.resolve(
            handle=handle,
            descriptor=_descriptor(asset_handles=("other-handle",)),
            now=now,
        )
    with pytest.raises(GenerationWorkerAssetHandleError, match="unavailable"):
        service.resolve(
            handle=handle,
            descriptor=replace(
                descriptor,
                budget=GenerationResourceBudget(4, 1, 8, 64, 32, 999, 1_024),
            ),
            now=now,
        )


def test_resolving_a_changed_or_nonregular_asset_fails_closed(tmp_path) -> None:
    asset = tmp_path / "converter.py"
    content = b"converter = object()\n"
    asset.write_bytes(content)
    service = _service(tmp_path)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    descriptor = _descriptor(asset_handles=("placeholder",))
    handle = service.issue(
        descriptor=descriptor,
        source_path=asset,
        expected_digest=sha256(content).hexdigest(),
        expires_at=now + timedelta(minutes=1),
        now=now,
    )
    bound = _descriptor(asset_handles=(handle,))
    asset.write_bytes(b"changed")

    with pytest.raises(GenerationWorkerAssetHandleError, match="unavailable"):
        service.resolve(handle=handle, descriptor=bound, now=now)


def test_issuing_a_symlinked_asset_fails_closed(tmp_path) -> None:
    asset = tmp_path / "converter.py"
    content = b"converter = object()\n"
    asset.write_bytes(content)
    link = tmp_path / "converter-link.py"
    link.symlink_to(asset)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    with pytest.raises(GenerationWorkerAssetHandleError, match="unavailable"):
        _service(tmp_path).issue(
            descriptor=_descriptor(asset_handles=("placeholder",)),
            source_path=link,
            expected_digest=sha256(content).hexdigest(),
            expires_at=now + timedelta(minutes=1),
            now=now,
        )


def _co_located_arguments(tmp_path, *, now: datetime) -> dict[str, object]:
    package_root = tmp_path / "package"
    package_root.mkdir()
    converter_asset = package_root / "converter.py"
    converter_content = b"converter = object()\n"
    converter_asset.write_bytes(converter_content)
    payload_asset = tmp_path / "sealed-payload"
    payload_content = b"sealed input"
    payload_asset.write_bytes(payload_content)
    artifact_path = tmp_path / "base-config"
    artifact_content = b"{}"
    artifact_path.write_bytes(artifact_content)
    converter = DeclaredInputConverter(
        converter_id="converter-v1",
        converter_contract_version="1",
        compatible_runner_contract_id="runner-v1",
        entrypoint="converter.py",
        asset_digest=sha256(converter_content).hexdigest(),
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
                    role="base_config",
                    repo_id="test/model",
                    revision="0" * 40,
                    filename="base-config",
                    sha256=sha256(artifact_content).hexdigest(),
                ),
            ),
            transformation=None,
        ),
        {"base_config": artifact_path},
    )
    return {
        "descriptor": _descriptor(asset_handles=("placeholder",)),
        "package_root": package_root,
        "converter": converter,
        "prepared_set": prepared_set,
        "sealed_payload_path": payload_asset,
        "sealed_payload_digest": sha256(payload_content).hexdigest(),
        "expires_at": now + timedelta(minutes=1),
        "now": now,
    }


def test_co_located_handle_binds_converter_material_and_sealed_payload(
    tmp_path,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    arguments = _co_located_arguments(tmp_path, now=now)

    service = _service(tmp_path)
    handle = service.issue_co_located(**arguments)
    descriptor = _descriptor(asset_handles=(handle,))

    assets = service.resolve_co_located(handle=handle, descriptor=descriptor, now=now)

    assert descriptor.to_wire()["asset_handles"] == (handle,)
    assert assets.package_root == arguments["package_root"]
    assert assets.converter == arguments["converter"]
    assert assets.prepared_set.recipe_digest == arguments["prepared_set"].recipe_digest
    assert assets.sealed_payload_path == arguments["sealed_payload_path"]


@pytest.mark.parametrize(
    "changes",
    (
        {"package_root": "/tmp/package"},
        {"converter": object()},
        {"prepared_set": object()},
        {"sealed_payload_path": b"sealed input"},
        {"sealed_payload_digest": "not-a-digest"},
    ),
)
def test_co_located_handle_rejects_untyped_host_inputs(tmp_path, changes) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    arguments = _co_located_arguments(tmp_path, now=now)
    arguments.update(changes)

    with pytest.raises(GenerationWorkerAssetHandleError, match="unavailable"):
        _service(tmp_path).issue_co_located(**arguments)
