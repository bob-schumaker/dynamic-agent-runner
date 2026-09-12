"""Client-supplied factories for prepared local model runners."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.local_model_preparation import PreparedArtifactSet
from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
    GenerationRunnerCapability,
)
from dynamic_agent_runner.workflow_host.profiles import LocalModelProfile


_DAR_OWNED_RUNNER_IDS = frozenset({"transformers-peft-v1"})


class LocalModelRunner(Protocol):
    """One client-owned factory that turns a prepared set into a model adapter."""

    runner_id: str
    generation_capability: GenerationRunnerCapability

    def create_adapter(
        self,
        profile: LocalModelProfile,
        resolve_prepared_set: Callable[[], PreparedArtifactSet],
    ) -> object:
        """Build one model adapter for an exact matching profile."""


class LocalModelRunnerCatalog:
    """Exact lookup of runners supplied by the embedding client."""

    def __init__(self, runners: Sequence[LocalModelRunner]) -> None:
        resolved: dict[str, LocalModelRunner] = {}
        for runner in runners:
            if not isinstance(runner.runner_id, str) or not runner.runner_id:
                raise ModelExecutionError("local model runner is unavailable")
            if (
                runner.runner_id in resolved
                or runner.runner_id in _DAR_OWNED_RUNNER_IDS
                or not isinstance(
                    getattr(runner, "generation_capability", None),
                    GenerationRunnerCapability,
                )
                or runner.generation_capability.runner_id != runner.runner_id
                or not _has_valid_worker_bindings(runner)
            ):
                raise ModelExecutionError("local model runner is unavailable")
            resolved[runner.runner_id] = runner
        self._runners = resolved

    def create_adapter(
        self,
        profile: LocalModelProfile,
        resolve_prepared_set: Callable[[], PreparedArtifactSet],
    ) -> object:
        """Create through the profile's exact private runner identifier."""

        try:
            runner = self._runners[profile.runner_id]
        except KeyError as error:
            raise ModelExecutionError("local model runner is unavailable") from error
        adapter = runner.create_adapter(profile, resolve_prepared_set)
        if runner.generation_capability.worker_protocol != "generation-worker-v1":
            return adapter
        bind_worker = getattr(adapter, "bind_generation_worker", None)
        if not callable(bind_worker):
            raise ModelExecutionError("local model runner is unavailable")
        try:
            bind_worker(
                factory=runner.generation_worker_factory,
                controller=runner.generation_worker_controller,
                capability=runner.generation_capability,
            )
        except Exception as error:  # noqa: BLE001 - client binding remains private.
            raise ModelExecutionError("local model runner is unavailable") from error
        return adapter


def _has_valid_worker_bindings(runner: LocalModelRunner) -> bool:
    """Require worker-only components to bind to the reviewed capability."""

    capability = runner.generation_capability
    factory = getattr(runner, "generation_worker_factory", None)
    controller = getattr(runner, "generation_worker_controller", None)
    worker_capability = capability.worker_protocol == "generation-worker-v1"
    if not worker_capability:
        return factory is None and controller is None
    if (
        factory is None
        or controller is None
        or getattr(factory, "runner_id", None) != runner.runner_id
        or getattr(factory, "capability", None) is not capability
        or not any(
            callable(getattr(factory, operation, None))
            for operation in ("create_launch_descriptor", "create_for_invocation")
        )
        or getattr(controller, "runner_id", None) != runner.runner_id
        or not isinstance(
            getattr(controller, "supported_execution_devices", None), frozenset
        )
        or not capability.supported_execution_devices
        & controller.supported_execution_devices
        or any(
            not callable(getattr(controller, operation, None))
            for operation in ("launch", "wait_ready", "terminate", "kill", "reap")
        )
    ):
        return False
    return True
