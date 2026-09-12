"""Tests for child-local converter and runner runtime construction."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from dynamic_agent_runner.workflow_host.descriptor import DeclaredInputConverter
from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
    GenerationResourceBudget,
)
from dynamic_agent_runner.workflow_host.generation_worker import (
    GenerationWorkerLaunchDescriptor,
    GenerationWorkerPackReceipt,
)
from dynamic_agent_runner.workflow_host.generation_worker_assets import (
    GenerationWorkerCoLocatedAssets,
)


def _descriptor() -> GenerationWorkerLaunchDescriptor:
    return GenerationWorkerLaunchDescriptor(
        "generation-worker-v1",
        "a" * 64,
        0,
        "runner-v1",
        "b" * 64,
        "converter-v1",
        "c" * 64,
        "d" * 64,
        "e" * 64,
        "cpu",
        GenerationResourceBudget(4, 1, 8, 64, 32, 1_000, 1_024),
        ("co-located-handle",),
    )


def test_child_runtime_builds_runner_from_typed_assets_and_loaded_converter(
    monkeypatch, tmp_path
) -> None:
    from dynamic_agent_runner.workflow_host.generation_worker_child_runtime import (
        GenerationWorkerCoLocatedRuntimeFactory,
    )

    descriptor = _descriptor()
    converter = DeclaredInputConverter(
        converter_id="converter-v1",
        converter_contract_version="1",
        compatible_runner_contract_id="runner-v1",
        entrypoint="converter.py",
        asset_digest="c" * 64,
        max_input_bytes=64,
        max_output_bytes=64,
        timeout_seconds=1,
    )
    assets = GenerationWorkerCoLocatedAssets(
        package_root=tmp_path,
        converter=converter,
        prepared_set=SimpleNamespace(recipe_digest="prepared-set"),
        messages=({"role": "user", "content": "describe"},),
        sealed_payload_path=tmp_path / "payload",
    )
    assets.sealed_payload_path.write_bytes(b"sealed payload")
    loaded_converter = object()
    created: list[tuple[object, object]] = []

    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.generation_worker_child_runtime.load_input_converter",
        lambda **_kwargs: loaded_converter,
    )

    class Handles:
        def resolve(self, **_kwargs: object) -> object:
            return assets

    class Runtime:
        def install_bootstrap_limit(self, _memory: int, _device: str) -> None:
            pass

        def pack(self) -> int:
            return 3

        def authorize(
            self, _receipt: GenerationWorkerPackReceipt, _remaining: int
        ) -> None:
            pass

        def generate(self) -> tuple[bytes, int]:
            return b"{}", 2

    runtime = Runtime()

    class RunnerRuntimeFactory:
        def create_runtime(self, *, assets: object, converter: object) -> object:
            created.append((assets, converter))
            return runtime

    child_runtime = GenerationWorkerCoLocatedRuntimeFactory(
        asset_handles=Handles(), runner_runtime_factory=RunnerRuntimeFactory()
    ).create_for_worker(descriptor=descriptor, now=datetime(2026, 1, 1, tzinfo=UTC))

    assert child_runtime is runtime
    assert created == [(assets, loaded_converter)]
