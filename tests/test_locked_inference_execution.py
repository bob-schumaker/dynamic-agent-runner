"""Fake-only execution vectors for bounded locked inference callbacks."""

from __future__ import annotations

import json
import time
from threading import Event, Thread

import pytest

from dynamic_agent_runner.workflow_host.locked_inference_execution import (
    LockedInferenceExecutionError,
    LockedInferenceExecutionService,
    LockedInferenceHostLimits,
    LockedInferenceProvider,
)


_SCHEMA = json.dumps(
    {
        "type": "object",
        "properties": {"value": {"type": "string", "max_string_bytes": 16}},
        "required": ["value"],
        "max_depth": 2,
        "max_items": 1,
    },
    sort_keys=True,
    separators=(",", ":"),
).encode()


class _Provider(LockedInferenceProvider):
    def __init__(self, response: bytes = b'{"value":"ok"}') -> None:
        self.calls: list[tuple[bytes, bytes]] = []
        self.response = response

    def generate(
        self, *, binding: object, instruction_bytes: bytes, request_bytes: bytes
    ) -> bytes:
        del binding
        self.calls.append((instruction_bytes, request_bytes))
        return self.response


def _service(provider: _Provider) -> LockedInferenceExecutionService:
    return LockedInferenceExecutionService(
        providers={"suggest": provider},
        bindings={"suggest": object()},
        instructions={"suggest": b"sealed instruction"},
        request_schemas={"suggest": _SCHEMA},
        response_schemas={"suggest": _SCHEMA},
        package_limits={
            "suggest": LockedInferenceHostLimits(2, 64, 64, 1000, 1),
        },
        host_limits=LockedInferenceHostLimits(2, 32, 32, 1000, 1),
        revalidate=lambda _role: True,
    )


def test_callback_uses_sealed_instruction_validates_canonical_values_and_limits() -> (
    None
):
    provider = _Provider()
    service = _service(provider)

    response = service.generate("suggest", b'{"value":"request"}')

    assert response == b'{"value":"ok"}'
    assert provider.calls == [(b"sealed instruction", b'{"value":"request"}')]


@pytest.mark.parametrize(
    "request_bytes",
    (b'{"value":"request" }', b'{"unknown":"request"}', b'{"value":1}'),
)
def test_callback_rejects_noncanonical_or_schema_invalid_requests_before_provider(
    request_bytes: bytes,
) -> None:
    provider = _Provider()

    with pytest.raises(LockedInferenceExecutionError, match="request"):
        _service(provider).generate("suggest", request_bytes)

    assert provider.calls == []


def test_callback_rejects_response_and_exhausted_quota_without_leaking_provider() -> (
    None
):
    provider = _Provider(b'{"value":1}')
    service = _service(provider)

    with pytest.raises(LockedInferenceExecutionError, match="response"):
        service.generate("suggest", b'{"value":"request"}')
    assert len(provider.calls) == 1

    provider.response = b'{"value":"ok"}'
    assert service.generate("suggest", b'{"value":"request"}') == b'{"value":"ok"}'
    with pytest.raises(LockedInferenceExecutionError, match="quota"):
        service.generate("suggest", b'{"value":"request"}')


def test_callback_revalidates_before_provider_and_has_no_role_fallback() -> None:
    provider = _Provider()
    service = _service(provider)
    service = LockedInferenceExecutionService(
        providers={"suggest": provider},
        bindings={"suggest": object()},
        instructions={"suggest": b"sealed instruction"},
        request_schemas={"suggest": _SCHEMA},
        response_schemas={"suggest": _SCHEMA},
        package_limits={"suggest": LockedInferenceHostLimits(1, 64, 64, 1000, 1)},
        host_limits=LockedInferenceHostLimits(1, 32, 32, 1000, 1),
        revalidate=lambda _role: False,
    )

    with pytest.raises(LockedInferenceExecutionError, match="unavailable"):
        service.generate("suggest", b'{"value":"request"}')
    with pytest.raises(LockedInferenceExecutionError, match="role"):
        service.generate("missing", b'{"value":"request"}')
    assert provider.calls == []


def test_callback_times_out_and_discards_late_provider_result() -> None:
    class SlowProvider(_Provider):
        def generate(self, **kwargs: object) -> bytes:
            time.sleep(0.02)
            return super().generate(**kwargs)  # type: ignore[arg-type]

    provider = SlowProvider()
    service = _service(provider)
    service._limits["suggest"] = LockedInferenceHostLimits(2, 32, 32, 1, 1)

    with pytest.raises(LockedInferenceExecutionError, match="timeout"):
        service.generate("suggest", b'{"value":"request"}')
    time.sleep(0.03)
    assert provider.calls == [(b"sealed instruction", b'{"value":"request"}')]


def test_roles_are_isolated_without_provider_fallback() -> None:
    suggest = _Provider(b'{"value":"suggest"}')
    classify = _Provider(b'{"value":"classify"}')
    service = LockedInferenceExecutionService(
        providers={"classify": classify, "suggest": suggest},
        bindings={"classify": object(), "suggest": object()},
        instructions={
            "classify": b"classify instruction",
            "suggest": b"suggest instruction",
        },
        request_schemas={"classify": _SCHEMA, "suggest": _SCHEMA},
        response_schemas={"classify": _SCHEMA, "suggest": _SCHEMA},
        package_limits={
            "classify": LockedInferenceHostLimits(1, 64, 64, 1000, 1),
            "suggest": LockedInferenceHostLimits(1, 64, 64, 1000, 1),
        },
        host_limits=LockedInferenceHostLimits(1, 32, 32, 1000, 1),
        revalidate=lambda _role: True,
    )

    assert service.generate("suggest", b'{"value":"request"}') == b'{"value":"suggest"}'
    assert (
        service.generate("classify", b'{"value":"request"}') == b'{"value":"classify"}'
    )
    assert suggest.calls == [(b"suggest instruction", b'{"value":"request"}')]
    assert classify.calls == [(b"classify instruction", b'{"value":"request"}')]


def test_concurrent_callback_attempt_is_rejected_before_a_second_provider_entry() -> (
    None
):
    entered = Event()
    release = Event()

    class BlockingProvider(_Provider):
        def generate(self, **kwargs: object) -> bytes:
            entered.set()
            release.wait(1)
            return super().generate(**kwargs)  # type: ignore[arg-type]

    provider = BlockingProvider()
    service = LockedInferenceExecutionService(
        providers={"suggest": provider},
        bindings={"suggest": object()},
        instructions={"suggest": b"sealed instruction"},
        request_schemas={"suggest": _SCHEMA},
        response_schemas={"suggest": _SCHEMA},
        package_limits={"suggest": LockedInferenceHostLimits(2, 64, 64, 1000, 1)},
        host_limits=LockedInferenceHostLimits(2, 32, 32, 1000, 1),
        revalidate=lambda _role: True,
    )
    result: list[bytes] = []
    worker = Thread(
        target=lambda: result.append(
            service.generate("suggest", b'{"value":"request"}')
        )
    )
    worker.start()
    assert entered.wait(1)

    with pytest.raises(LockedInferenceExecutionError, match="quota"):
        service.generate("suggest", b'{"value":"request"}')

    release.set()
    worker.join(1)
    assert result == [b'{"value":"ok"}']
    assert len(provider.calls) == 1


def test_effective_host_ceiling_and_provider_failure_are_redacted() -> None:
    schema = json.dumps(
        {
            "type": "object",
            "properties": {"value": {"type": "string", "max_string_bytes": 64}},
            "required": ["value"],
            "max_depth": 2,
            "max_items": 1,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    provider = _Provider()
    service = LockedInferenceExecutionService(
        providers={"suggest": provider},
        bindings={"suggest": object()},
        instructions={"suggest": b"sealed instruction"},
        request_schemas={"suggest": schema},
        response_schemas={"suggest": schema},
        package_limits={"suggest": LockedInferenceHostLimits(1, 64, 64, 1000, 1)},
        host_limits=LockedInferenceHostLimits(1, 32, 32, 1000, 1),
        revalidate=lambda _role: True,
    )

    with pytest.raises(LockedInferenceExecutionError, match="exceeds"):
        service.generate(
            "suggest", b'{"value":"this string exceeds the host input ceiling"}'
        )
    assert provider.calls == []

    class FailingProvider(_Provider):
        def generate(self, **_kwargs: object) -> bytes:
            raise RuntimeError("private provider failure")

    with pytest.raises(LockedInferenceExecutionError, match="provider failed") as error:
        _service(FailingProvider()).generate("suggest", b'{"value":"request"}')
    assert "private" not in str(error.value)
