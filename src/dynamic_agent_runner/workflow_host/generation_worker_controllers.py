"""Machine-specific lifecycle controllers for bounded generation workers."""

from __future__ import annotations

import multiprocessing
import platform
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

try:
    import resource
except ImportError:  # pragma: no cover - exercised on platforms without POSIX limits.
    resource = None  # type: ignore[assignment]

from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
    GenerationResourceBudget,
    GenerationResourceBudgetError,
)
from dynamic_agent_runner.workflow_host.generation_worker import (
    GenerationWorkerLaunchDescriptor,
    GenerationWorkerProtocolError,
    fixed_generation_worker_entry_point,
)


class MetalMpsWorkerRuntime(Protocol):
    """Receiver-installed Metal containment and lifecycle implementation."""

    def install_memory_envelope(self, budget: GenerationResourceBudget) -> bool:
        """Install an MPS-enforceable envelope before the worker can start."""

    def launch(self, descriptor: GenerationWorkerLaunchDescriptor) -> object:
        """Launch the reviewed worker under its already-installed envelope."""

    def wait_ready(self, child: object, timeout: float) -> bool:
        """Wait for the bounded child bootstrap acknowledgement."""

    def terminate(self, child: object) -> None:
        """Request child termination."""

    def kill(self, child: object) -> None:
        """Force child termination when graceful shutdown did not complete."""

    def reap(self, child: object, timeout: float) -> bool:
        """Confirm that a terminated child has been reaped."""


@dataclass
class _CpuWorkerChild:
    process: object
    command_connection: object
    ready_connection: object


class CpuMultiprocessingGenerationWorkerController:
    """CPU-only process isolation backed by ``multiprocessing`` and ``resource``."""

    supported_execution_devices = frozenset({"cpu"})

    def __init__(
        self,
        *,
        runner_id: str,
        process_context: object | None = None,
    ) -> None:
        if (
            not isinstance(runner_id, str)
            or not runner_id
            or not _cpu_limit_available()
        ):
            raise GenerationResourceBudgetError(
                "generation memory budget is unavailable"
            )
        self.runner_id = runner_id
        self._process_context = (
            process_context
            if process_context is not None
            else multiprocessing.get_context("spawn")
        )

    def launch(self, descriptor: GenerationWorkerLaunchDescriptor) -> _CpuWorkerChild:
        """Start a fixed entry-point worker after validating CPU applicability."""

        _require_descriptor(descriptor, runner_id=self.runner_id, device="cpu")
        try:
            ready_receiver, ready_sender = self._process_context.Pipe(duplex=False)
            child_command, parent_command = self._process_context.Pipe(duplex=False)
            process = self._process_context.Process(
                target=_cpu_worker_entry,
                args=(ready_sender, child_command, descriptor.to_wire()),
            )
            process.start()
            ready_sender.close()
            child_command.close()
            return _CpuWorkerChild(
                process=process,
                command_connection=parent_command,
                ready_connection=ready_receiver,
            )
        except Exception as error:
            raise GenerationResourceBudgetError(
                "generation memory budget is unavailable"
            ) from error

    def wait_ready(self, child: object, timeout: float) -> bool:
        """Return only the fixed, redacted child readiness acknowledgement."""

        worker = _cpu_child(child)
        if not _positive_timeout(timeout):
            return False
        try:
            if not worker.ready_connection.poll(timeout):
                return False
            return worker.ready_connection.recv() == ("ready",)
        except Exception:
            return False
        finally:
            _close(worker.ready_connection)

    def terminate(self, child: object) -> None:
        """Terminate a live CPU child without relying on its command protocol."""

        worker = _cpu_child(child)
        if worker.process.is_alive():
            worker.process.terminate()

    def kill(self, child: object) -> None:
        """Escalate to a process kill if the platform provides it."""

        worker = _cpu_child(child)
        if not worker.process.is_alive():
            return
        kill = getattr(worker.process, "kill", None)
        if callable(kill):
            kill()
        else:
            worker.process.terminate()

    def reap(self, child: object, timeout: float) -> bool:
        """Close the command channel and confirm that the process exited."""

        worker = _cpu_child(child)
        if not _nonnegative_timeout(timeout):
            return False
        try:
            if worker.process.is_alive():
                try:
                    worker.command_connection.send("close")
                except Exception:
                    pass
            worker.process.join(timeout)
            return not worker.process.is_alive()
        except Exception:
            return False
        finally:
            _close(worker.command_connection)
            _close(worker.ready_connection)


class MacMpsGenerationWorkerController:
    """Darwin-only controller that delegates to reviewed Metal/MPS containment."""

    supported_execution_devices = frozenset({"mps"})

    def __init__(
        self,
        *,
        runner_id: str,
        metal_runtime: MetalMpsWorkerRuntime,
        platform_system: Callable[[], str] = platform.system,
    ) -> None:
        operations = (
            "install_memory_envelope",
            "launch",
            "wait_ready",
            "terminate",
            "kill",
            "reap",
        )
        if (
            not isinstance(runner_id, str)
            or not runner_id
            or not callable(platform_system)
            or platform_system() != "Darwin"
            or any(
                not callable(getattr(metal_runtime, operation, None))
                for operation in operations
            )
        ):
            raise GenerationResourceBudgetError(
                "generation memory budget is unavailable"
            )
        self.runner_id = runner_id
        self._metal_runtime = metal_runtime

    def launch(self, descriptor: GenerationWorkerLaunchDescriptor) -> object:
        """Require MPS memory enforcement before delegation can launch a worker."""

        _require_descriptor(descriptor, runner_id=self.runner_id, device="mps")
        try:
            if (
                self._metal_runtime.install_memory_envelope(descriptor.budget)
                is not True
            ):
                raise GenerationResourceBudgetError(
                    "generation memory budget is unavailable"
                )
            return self._metal_runtime.launch(descriptor)
        except GenerationResourceBudgetError:
            raise
        except Exception as error:
            raise GenerationResourceBudgetError(
                "generation memory budget is unavailable"
            ) from error

    def wait_ready(self, child: object, timeout: float) -> bool:
        return self._metal_runtime.wait_ready(child, timeout)

    def terminate(self, child: object) -> None:
        self._metal_runtime.terminate(child)

    def kill(self, child: object) -> None:
        self._metal_runtime.kill(child)

    def reap(self, child: object, timeout: float) -> bool:
        return self._metal_runtime.reap(child, timeout)


@dataclass(frozen=True)
class _SelectedWorkerChild:
    controller: object
    child: object


class GenerationWorkerControllerSet:
    """Select one reviewed machine controller by its exact execution device."""

    def __init__(self, *, runner_id: str, controllers: Mapping[str, object]) -> None:
        if (
            not isinstance(runner_id, str)
            or not runner_id
            or not isinstance(controllers, Mapping)
        ):
            raise GenerationResourceBudgetError(
                "generation memory budget is unavailable"
            )
        selected = dict(controllers)
        if not selected or any(
            not isinstance(device, str)
            or not device
            or getattr(controller, "runner_id", None) != runner_id
            or device
            not in getattr(controller, "supported_execution_devices", frozenset())
            or any(
                not callable(getattr(controller, operation, None))
                for operation in ("launch", "wait_ready", "terminate", "kill", "reap")
            )
            for device, controller in selected.items()
        ):
            raise GenerationResourceBudgetError(
                "generation memory budget is unavailable"
            )
        self.runner_id = runner_id
        self._controllers = selected
        self.supported_execution_devices = frozenset(selected)

    def launch(
        self, descriptor: GenerationWorkerLaunchDescriptor
    ) -> _SelectedWorkerChild:
        """Dispatch only to the controller reviewed for this descriptor's device."""

        if (
            not isinstance(descriptor, GenerationWorkerLaunchDescriptor)
            or descriptor.runner_id != self.runner_id
        ):
            raise GenerationResourceBudgetError(
                "generation memory budget is unavailable"
            )
        try:
            controller = self._controllers[descriptor.execution_device]
        except KeyError as error:
            raise GenerationResourceBudgetError(
                "generation memory budget is unavailable"
            ) from error
        return _SelectedWorkerChild(controller, controller.launch(descriptor))

    def wait_ready(self, child: object, timeout: float) -> bool:
        selected = _selected_child(child)
        return selected.controller.wait_ready(selected.child, timeout)

    def terminate(self, child: object) -> None:
        selected = _selected_child(child)
        selected.controller.terminate(selected.child)

    def kill(self, child: object) -> None:
        selected = _selected_child(child)
        selected.controller.kill(selected.child)

    def reap(self, child: object, timeout: float) -> bool:
        selected = _selected_child(child)
        return selected.controller.reap(selected.child, timeout)


def machine_generation_worker_controllers(
    *,
    runner_id: str,
    metal_runtime: MetalMpsWorkerRuntime | None = None,
    platform_system: Callable[[], str] = platform.system,
    process_context: object | None = None,
) -> GenerationWorkerControllerSet:
    """Build only the CPU/MPS controllers the receiving machine can enforce."""

    controllers: dict[str, object] = {}
    try:
        controllers["cpu"] = CpuMultiprocessingGenerationWorkerController(
            runner_id=runner_id,
            process_context=process_context,
        )
    except GenerationResourceBudgetError:
        pass
    if metal_runtime is not None:
        try:
            controllers["mps"] = MacMpsGenerationWorkerController(
                runner_id=runner_id,
                metal_runtime=metal_runtime,
                platform_system=platform_system,
            )
        except GenerationResourceBudgetError:
            pass
    if not controllers:
        raise GenerationResourceBudgetError("generation memory budget is unavailable")
    return GenerationWorkerControllerSet(runner_id=runner_id, controllers=controllers)


def install_cpu_memory_limit(
    max_memory_bytes: int, *, resource_module: object = resource
) -> None:
    """Set a no-greater-than address-space limit before the worker entry point."""

    if (
        not isinstance(max_memory_bytes, int)
        or isinstance(max_memory_bytes, bool)
        or max_memory_bytes <= 0
    ):
        raise GenerationResourceBudgetError("generation memory budget is unavailable")
    try:
        limit = resource_module.RLIMIT_AS
        current_soft, current_hard = resource_module.getrlimit(limit)
        infinity = resource_module.RLIM_INFINITY
        hard_limit = max_memory_bytes if current_hard == infinity else current_hard
        effective_limit = min(max_memory_bytes, hard_limit)
        if effective_limit <= 0:
            raise ValueError("invalid resource limit")
        resource_module.setrlimit(limit, (effective_limit, effective_limit))
    except Exception as error:
        raise GenerationResourceBudgetError(
            "generation memory budget is unavailable"
        ) from error


def _cpu_worker_entry(
    ready_connection: object,
    command_connection: object,
    wire_descriptor: object,
) -> None:
    """Fixed CPU bootstrap: validate, cap process memory, then acknowledge ready."""

    try:
        descriptor = fixed_generation_worker_entry_point(wire_descriptor)
        install_cpu_memory_limit(descriptor.budget.max_memory_bytes)
        ready_connection.send(("ready",))
        command_connection.recv()
    except Exception:
        try:
            ready_connection.send(("failed",))
        except Exception:
            pass
    finally:
        _close(ready_connection)
        _close(command_connection)


def _require_descriptor(
    descriptor: object, *, runner_id: str, device: str
) -> GenerationWorkerLaunchDescriptor:
    if (
        not isinstance(descriptor, GenerationWorkerLaunchDescriptor)
        or descriptor.runner_id != runner_id
        or descriptor.execution_device != device
    ):
        raise GenerationResourceBudgetError("generation memory budget is unavailable")
    return descriptor


def _cpu_limit_available() -> bool:
    return resource is not None and all(
        hasattr(resource, attribute) for attribute in ("RLIMIT_AS", "RLIM_INFINITY")
    )


def _cpu_child(value: object) -> _CpuWorkerChild:
    if not isinstance(value, _CpuWorkerChild):
        raise GenerationWorkerProtocolError("generation worker protocol invalid")
    return value


def _selected_child(value: object) -> _SelectedWorkerChild:
    if not isinstance(value, _SelectedWorkerChild):
        raise GenerationWorkerProtocolError("generation worker protocol invalid")
    return value


def _positive_timeout(value: object) -> bool:
    return isinstance(value, float) and value > 0


def _nonnegative_timeout(value: object) -> bool:
    return isinstance(value, float) and value >= 0


def _close(connection: object) -> None:
    close = getattr(connection, "close", None)
    if callable(close):
        close()
