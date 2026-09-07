"""Client-supplied factories for prepared local model runners."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.local_model_preparation import PreparedArtifactSet
from dynamic_agent_runner.workflow_host.profiles import LocalModelProfile


_DAR_OWNED_RUNNER_IDS = frozenset({"transformers-peft-v1"})


class LocalModelRunner(Protocol):
    """One client-owned factory that turns a prepared set into a model adapter."""

    runner_id: str

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
        return runner.create_adapter(profile, resolve_prepared_set)
