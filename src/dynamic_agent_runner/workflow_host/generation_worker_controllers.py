"""Machine-specific lifecycle controllers for bounded generation workers."""

from __future__ import annotations

import multiprocessing
import platform
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
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
    GenerationWorkerDeadlineExceeded,
    GenerationWorkerExecutionFailed,
    GenerationWorkerLaunchDescriptor,
    GenerationWorkerPackReceipt,
    GenerationWorkerProtocolError,
    fixed_generation_worker_entry_point,
)


_IPC_TIMEOUT_SECONDS = 5.0


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


class CpuGenerationWorkerRuntime(Protocol):
    """Receiver-installed child behavior exposed through fixed scalar frames."""

    def install_bootstrap_limit(
        self, max_memory_bytes: int, execution_device: str
    ) -> None: ...

    def pack(self) -> int | tuple[int, bool]: ...

    def authorize(
        self, receipt: GenerationWorkerPackReceipt, remaining_generated_tokens: int
    ) -> None: ...

    def generate(
        self,
    ) -> (
        tuple[bytes, int]
        | tuple[bytes, int, bool]
        | tuple[bytes, int, int, int]
        | tuple[bytes, int, int, int, bool]
    ): ...


@dataclass
class _CpuWorkerChild:
    process: object
    command_connection: object
    response_connection: object
    ready_connection: object
    _deadline_timeout: float | None = None

    def install_bootstrap_limit(
        self, max_memory_bytes: int, execution_device: str
    ) -> None:
        self._request(
            {
                "type": "pack",
                "max_memory_bytes": max_memory_bytes,
                "execution_device": execution_device,
            },
            "packed",
        )

    def pack(self) -> int:
        response = getattr(self, "_last_response", None)
        packed_context_tokens = (
            response.get("packed_context_tokens")
            if isinstance(response, Mapping)
            else None
        )
        if not _nonnegative_int(packed_context_tokens):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        return packed_context_tokens

    def authorize(
        self, receipt: GenerationWorkerPackReceipt, remaining_generated_tokens: int
    ) -> None:
        self._request(
            {
                "type": "authorize",
                "receipt": _receipt_to_wire(receipt),
                "remaining_generated_tokens": remaining_generated_tokens,
            },
            "authorized",
        )

    def generate(
        self,
    ) -> (
        tuple[bytes, int]
        | tuple[bytes, int, bool]
        | tuple[bytes, int, int, int]
        | tuple[bytes, int, int, int, bool]
    ):
        response = self._request(
            {"type": "generate"}, "result", timeout=self._deadline_timeout
        )
        candidate = response.get("candidate")
        generated_tokens = response.get("generated_tokens")
        aggregate_generated_tokens = response.get("aggregate_generated_tokens")
        aggregate_output_bytes = response.get("aggregate_output_bytes")
        exhausted = response.get("exhausted")
        if not isinstance(candidate, bytes) or not _nonnegative_int(generated_tokens):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        if aggregate_generated_tokens is None and aggregate_output_bytes is None:
            if exhausted is None:
                return candidate, generated_tokens
            if not isinstance(exhausted, bool):
                raise GenerationWorkerProtocolError(
                    "generation worker protocol invalid"
                )
            return candidate, generated_tokens, exhausted
        if exhausted is None:
            exhaustion_suffix: tuple[bool, ...] = ()
        elif isinstance(exhausted, bool):
            exhaustion_suffix = (exhausted,)
        else:
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        if not _nonnegative_int(aggregate_generated_tokens) or not _nonnegative_int(
            aggregate_output_bytes
        ):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        return (
            candidate,
            generated_tokens,
            aggregate_generated_tokens,
            aggregate_output_bytes,
            *exhaustion_suffix,
        )

    def _request(
        self,
        request: Mapping[str, object],
        response_type: str,
        *,
        timeout: float | None = None,
    ) -> Mapping[str, object]:
        timeout_seconds = _IPC_TIMEOUT_SECONDS if timeout is None else timeout
        if not _positive_timeout(timeout_seconds):
            raise GenerationWorkerDeadlineExceeded("generation deadline exceeded")
        try:
            self.command_connection.send(dict(request))
            if not self.response_connection.poll(timeout_seconds):
                if response_type == "result" and timeout is not None:
                    raise GenerationWorkerDeadlineExceeded(
                        "generation deadline exceeded"
                    )
                raise GenerationWorkerProtocolError(
                    "generation worker protocol invalid"
                )
            response = self.response_connection.recv()
        except GenerationWorkerProtocolError:
            raise
        except Exception as error:
            raise GenerationWorkerProtocolError(
                "generation worker protocol invalid"
            ) from error
        if isinstance(response, Mapping) and dict(response) == {"type": "failed"}:
            raise GenerationWorkerExecutionFailed("generation execution failed")
        if (
            not isinstance(response, Mapping)
            or response.get("type") != response_type
            or (
                response_type == "packed"
                and set(response) != {"type", "packed_context_tokens"}
            )
            or (response_type == "authorized" and set(response) != {"type"})
            or (
                response_type == "result"
                and set(response)
                not in (
                    {"type", "candidate", "generated_tokens"},
                    {
                        "type",
                        "candidate",
                        "generated_tokens",
                        "aggregate_generated_tokens",
                        "aggregate_output_bytes",
                    },
                    {"type", "candidate", "generated_tokens", "exhausted"},
                    {
                        "type",
                        "candidate",
                        "generated_tokens",
                        "aggregate_generated_tokens",
                        "aggregate_output_bytes",
                        "exhausted",
                    },
                )
            )
        ):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        self._last_response = response
        return response

    def set_deadline_timeout(self, timeout: float) -> None:
        """Bound the next result wait by the parent's remaining deadline."""

        if not _positive_timeout(timeout):
            raise GenerationWorkerDeadlineExceeded("generation deadline exceeded")
        self._deadline_timeout = timeout


class CpuMultiprocessingGenerationWorkerController:
    """CPU-only process isolation backed by ``multiprocessing`` and ``resource``."""

    supported_execution_devices = frozenset({"cpu"})

    def __init__(
        self,
        *,
        runner_id: str,
        process_context: object | None = None,
        asset_handles: object | None = None,
        worker_runtime: CpuGenerationWorkerRuntime | None = None,
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
        self._asset_handles = asset_handles
        self._worker_runtime = worker_runtime

    def launch(self, descriptor: GenerationWorkerLaunchDescriptor) -> _CpuWorkerChild:
        """Start a fixed entry-point worker after validating CPU applicability."""

        _require_descriptor(descriptor, runner_id=self.runner_id, device="cpu")
        try:
            ready_receiver, ready_sender = self._process_context.Pipe(duplex=False)
            child_command, parent_command = self._process_context.Pipe(duplex=False)
            response_receiver, response_sender = self._process_context.Pipe(
                duplex=False
            )
            process = self._process_context.Process(
                target=_cpu_worker_entry,
                args=(
                    ready_sender,
                    child_command,
                    response_sender,
                    descriptor.to_wire(),
                    self._asset_handles,
                    self._worker_runtime,
                ),
            )
            process.start()
            ready_sender.close()
            child_command.close()
            response_sender.close()
            return _CpuWorkerChild(
                process=process,
                command_connection=parent_command,
                response_connection=response_receiver,
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
            worker.process.join(timeout if timeout > 0 else 0.05)
            return not worker.process.is_alive()
        except Exception:
            return False
        finally:
            _close(worker.command_connection)
            _close(worker.response_connection)
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
    asset_handles: object | None = None,
    worker_runtime: CpuGenerationWorkerRuntime | None = None,
) -> GenerationWorkerControllerSet:
    """Build only the CPU/MPS controllers the receiving machine can enforce."""

    controllers: dict[str, object] = {}
    try:
        controllers["cpu"] = CpuMultiprocessingGenerationWorkerController(
            runner_id=runner_id,
            process_context=process_context,
            asset_handles=asset_handles,
            worker_runtime=worker_runtime,
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
    response_connection: object,
    wire_descriptor: object,
    asset_handles: object | None,
    worker_runtime: CpuGenerationWorkerRuntime | None,
) -> None:
    """Fixed CPU bootstrap: validate, cap process memory, then acknowledge ready."""

    try:
        bootstrap_descriptor = GenerationWorkerLaunchDescriptor.from_wire(
            wire_descriptor
        )
        install_cpu_memory_limit(bootstrap_descriptor.budget.max_memory_bytes)
        descriptor = fixed_generation_worker_entry_point(
            wire_descriptor,
            asset_handles=asset_handles,
            now=datetime.now(UTC) if asset_handles is not None else None,
        )
        active_worker_runtime = _materialize_child_runtime(worker_runtime, descriptor)
        ready_connection.send(("ready",))
        _run_cpu_worker_protocol(
            command_connection=command_connection,
            response_connection=response_connection,
            descriptor=descriptor,
            worker_runtime=active_worker_runtime,
        )
    except Exception:
        try:
            ready_connection.send(("failed",))
        except Exception:
            pass
    finally:
        _close(ready_connection)
        _close(command_connection)
        _close(response_connection)


def _materialize_child_runtime(
    worker_runtime: CpuGenerationWorkerRuntime | None,
    descriptor: GenerationWorkerLaunchDescriptor,
) -> CpuGenerationWorkerRuntime | None:
    """Create receiver-installed child state only after fixed bootstrap checks."""

    create_for_worker = getattr(worker_runtime, "create_for_worker", None)
    if not callable(create_for_worker):
        return worker_runtime
    try:
        return create_for_worker(descriptor=descriptor, now=datetime.now(UTC))
    except Exception as error:
        raise GenerationWorkerProtocolError(
            "generation worker protocol invalid"
        ) from error


def _run_cpu_worker_protocol(
    *,
    command_connection: object,
    response_connection: object,
    descriptor: GenerationWorkerLaunchDescriptor,
    worker_runtime: CpuGenerationWorkerRuntime | None,
) -> None:
    """Serve one fixed pack/authorize/generate transcript without object frames."""

    packed_context_tokens: int | None = None
    authorized_remaining_generated_tokens: int | None = None
    while True:
        try:
            request = command_connection.recv()
            if request == "close":
                return
            response = _cpu_worker_response(
                request=request,
                descriptor=descriptor,
                worker_runtime=worker_runtime,
                packed_context_tokens=packed_context_tokens,
                authorized_remaining_generated_tokens=authorized_remaining_generated_tokens,
            )
            if response["type"] == "packed":
                packed_context_tokens = response["packed_context_tokens"]
            elif response["type"] == "authorized":
                authorized_remaining_generated_tokens = request[
                    "remaining_generated_tokens"
                ]
            response_connection.send(response)
            if response["type"] == "result":
                return
        except GenerationWorkerProtocolError:
            try:
                response_connection.send({"type": "protocol_invalid"})
            except Exception:
                pass
            return
        except Exception:
            try:
                response_connection.send({"type": "failed"})
            except Exception:
                pass
            return


def _cpu_worker_response(
    *,
    request: object,
    descriptor: GenerationWorkerLaunchDescriptor,
    worker_runtime: CpuGenerationWorkerRuntime | None,
    packed_context_tokens: int | None,
    authorized_remaining_generated_tokens: int | None,
) -> dict[str, object]:
    if worker_runtime is None or not isinstance(request, Mapping):
        raise GenerationWorkerProtocolError("generation worker protocol invalid")
    request_type = request.get("type")
    if request_type == "pack":
        return _cpu_pack_response(
            request, descriptor, worker_runtime, packed_context_tokens
        )
    if request_type == "authorize":
        return _cpu_authorize_response(
            request,
            descriptor,
            worker_runtime,
            packed_context_tokens,
            authorized_remaining_generated_tokens is not None,
        )
    if request_type == "generate":
        return _cpu_generate_response(
            request,
            descriptor,
            worker_runtime,
            authorized_remaining_generated_tokens,
        )
    raise GenerationWorkerProtocolError("generation worker protocol invalid")


def _cpu_pack_response(
    request: Mapping[str, object],
    descriptor: GenerationWorkerLaunchDescriptor,
    worker_runtime: CpuGenerationWorkerRuntime,
    packed_context_tokens: int | None,
) -> dict[str, object]:
    if (
        packed_context_tokens is not None
        or set(request) != {"type", "max_memory_bytes", "execution_device"}
        or request["max_memory_bytes"] != descriptor.budget.max_memory_bytes
        or request["execution_device"] != descriptor.execution_device
    ):
        raise GenerationWorkerProtocolError("generation worker protocol invalid")
    worker_runtime.install_bootstrap_limit(
        descriptor.budget.max_memory_bytes, descriptor.execution_device
    )
    packed = worker_runtime.pack()
    tokens = packed[0] if isinstance(packed, tuple) and len(packed) == 2 else packed
    entered_model = (
        packed[1] if isinstance(packed, tuple) and len(packed) == 2 else False
    )
    if not _nonnegative_int(tokens) or entered_model is not False:
        raise GenerationWorkerProtocolError("generation worker protocol invalid")
    return {"type": "packed", "packed_context_tokens": tokens}


def _cpu_authorize_response(
    request: Mapping[str, object],
    descriptor: GenerationWorkerLaunchDescriptor,
    worker_runtime: CpuGenerationWorkerRuntime,
    packed_context_tokens: int | None,
    authorized: bool,
) -> dict[str, object]:
    if (
        packed_context_tokens is None
        or authorized
        or set(request) != {"type", "receipt", "remaining_generated_tokens"}
        or not _positive_int(request["remaining_generated_tokens"])
    ):
        raise GenerationWorkerProtocolError("generation worker protocol invalid")
    receipt = _receipt_from_wire(request["receipt"])
    if not _receipt_matches_descriptor(receipt, descriptor, packed_context_tokens):
        raise GenerationWorkerProtocolError("generation worker protocol invalid")
    worker_runtime.authorize(receipt, request["remaining_generated_tokens"])
    return {"type": "authorized"}


def _cpu_generate_response(
    request: Mapping[str, object],
    descriptor: GenerationWorkerLaunchDescriptor,
    worker_runtime: CpuGenerationWorkerRuntime,
    authorized_remaining_generated_tokens: int | None,
) -> dict[str, object]:
    if authorized_remaining_generated_tokens is None or set(request) != {"type"}:
        raise GenerationWorkerProtocolError("generation worker protocol invalid")
    result = worker_runtime.generate()
    if (
        not isinstance(result, tuple)
        or len(result) not in (2, 3, 4, 5)
        or not isinstance(result[0], bytes)
        or not _nonnegative_int(result[1])
        or result[1] > authorized_remaining_generated_tokens
        or len(result[0]) > descriptor.budget.max_total_output_bytes
    ):
        raise GenerationWorkerProtocolError("generation worker protocol invalid")
    response = {"type": "result", "candidate": result[0], "generated_tokens": result[1]}
    if len(result) in (2, 3):
        if len(result) == 3:
            if not isinstance(result[2], bool):
                raise GenerationWorkerProtocolError(
                    "generation worker protocol invalid"
                )
            response["exhausted"] = result[2]
        return response
    if (
        not _nonnegative_int(result[2])
        or not _nonnegative_int(result[3])
        or result[2] != result[1]
        or result[3] != len(result[0])
    ):
        raise GenerationWorkerProtocolError("generation worker protocol invalid")
    response |= {
        "aggregate_generated_tokens": result[2],
        "aggregate_output_bytes": result[3],
    }
    if len(result) == 5:
        if not isinstance(result[4], bool):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        response["exhausted"] = result[4]
    return response


def _receipt_to_wire(receipt: object) -> dict[str, object]:
    if not isinstance(receipt, GenerationWorkerPackReceipt):
        raise GenerationWorkerProtocolError("generation worker protocol invalid")
    return {
        "invocation_id": receipt.invocation_id,
        "invocation_digest": receipt.invocation_digest,
        "converter_digest": receipt.converter_digest,
        "material_lock_digest": receipt.material_lock_digest,
        "execution_device": receipt.execution_device,
        "fragment_index": receipt.fragment_index,
        "packed_context_tokens": receipt.packed_context_tokens,
    }


def _receipt_from_wire(value: object) -> GenerationWorkerPackReceipt:
    fields = {
        "invocation_id",
        "invocation_digest",
        "converter_digest",
        "material_lock_digest",
        "execution_device",
        "fragment_index",
        "packed_context_tokens",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise GenerationWorkerProtocolError("generation worker protocol invalid")
    try:
        return GenerationWorkerPackReceipt(**value)
    except (TypeError, GenerationWorkerProtocolError) as error:
        raise GenerationWorkerProtocolError(
            "generation worker protocol invalid"
        ) from error


def _receipt_matches_descriptor(
    receipt: GenerationWorkerPackReceipt,
    descriptor: GenerationWorkerLaunchDescriptor,
    packed_context_tokens: int,
) -> bool:
    return (
        receipt.invocation_digest == descriptor.invocation_digest
        and receipt.converter_digest == descriptor.converter_asset_digest
        and receipt.material_lock_digest == descriptor.material_lock_digest
        and receipt.execution_device == descriptor.execution_device
        and receipt.fragment_index == descriptor.fragment_index
        and receipt.packed_context_tokens == packed_context_tokens
    )


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


def _nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _positive_int(value: object) -> bool:
    return _nonnegative_int(value) and value > 0


def _close(connection: object) -> None:
    close = getattr(connection, "close", None)
    if callable(close):
        close()
