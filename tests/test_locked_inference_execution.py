"""Fake-only execution vectors for bounded locked inference callbacks."""

from __future__ import annotations

import json

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
