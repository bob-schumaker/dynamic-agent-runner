"""Child-local construction bridge for generic converter-capable workers."""

from __future__ import annotations

from datetime import datetime

from dynamic_agent_runner.workflow_host.generation_worker import (
    GenerationWorkerLaunchDescriptor,
    GenerationWorkerProtocolError,
)
from dynamic_agent_runner.workflow_host.generation_worker_assets import (
    GenerationWorkerCoLocatedAssets,
)
from dynamic_agent_runner.workflow_host.input_converter_loader import (
    InputConverterLoadError,
    load_input_converter,
)


class GenerationWorkerCoLocatedRuntimeFactory:
    """Build one receiver-installed scalar runtime from child-private assets."""

    def __init__(
        self, *, asset_handles: object, runner_runtime_factory: object
    ) -> None:
        if not callable(getattr(asset_handles, "resolve", None)) or not callable(
            getattr(runner_runtime_factory, "create_runtime", None)
        ):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        self._asset_handles = asset_handles
        self._runner_runtime_factory = runner_runtime_factory

    def create_for_worker(
        self, *, descriptor: GenerationWorkerLaunchDescriptor, now: datetime
    ) -> object:
        """Resolve and load only fixed typed inputs before runner construction."""

        if not isinstance(
            descriptor, GenerationWorkerLaunchDescriptor
        ) or not isinstance(now, datetime):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        try:
            assets = tuple(
                self._asset_handles.resolve(
                    handle=handle, descriptor=descriptor, now=now
                )
                for handle in descriptor.asset_handles
            )
            if len(assets) != 1 or not isinstance(
                assets[0], GenerationWorkerCoLocatedAssets
            ):
                raise GenerationWorkerProtocolError(
                    "generation worker protocol invalid"
                )
            converter = load_input_converter(
                package_root=assets[0].package_root, converter=assets[0].converter
            )
            runtime = self._runner_runtime_factory.create_runtime(
                assets=assets[0], converter=converter
            )
        except GenerationWorkerProtocolError:
            raise
        except InputConverterLoadError as error:
            raise GenerationWorkerProtocolError(
                "generation worker protocol invalid"
            ) from error
        except Exception as error:
            raise GenerationWorkerProtocolError(
                "generation worker protocol invalid"
            ) from error
        if any(
            not callable(getattr(runtime, operation, None))
            for operation in (
                "install_bootstrap_limit",
                "pack",
                "authorize",
                "generate",
            )
        ):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        return runtime
