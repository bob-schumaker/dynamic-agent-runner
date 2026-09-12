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
