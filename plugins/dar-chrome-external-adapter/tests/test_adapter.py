from __future__ import annotations

import asyncio
from pathlib import Path

from dar_chrome_external_adapter import ChromeBuiltInAIAdapter, create_adapter
from dynamic_agent_runner.external_adapter import (
    DARExternalRequestContext,
    ExternalAdapterError,
    ExternalModelAdapterHealth,
)
from dynamic_agent_runner.openai_client import OpenAIModelRequest
from dynamic_agent_runner.workflow_host.external_adapter_registry import (
    ExternalAdapterRegistry,
)


class FakeBridge:
    extension_id = "trusted-extension"
    origin = "chrome-extension://trusted-extension"

    def __init__(self, value: str = "chrome response") -> None:
        self.value = value
        self.calls: list[object] = []

    def health(self) -> ExternalModelAdapterHealth:
        return ExternalModelAdapterHealth(status="ready")

    def generate(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        return self.value


def test_descriptor_is_text_only_and_tool_free() -> None:
    adapter = create_adapter(
        FakeBridge(),
        trusted_extension_id="trusted-extension",
        trusted_origin="chrome-extension://trusted-extension",
    )
    descriptor = adapter.describe()
    assert descriptor.model_alias == "gemini-nano"
    assert descriptor.input_modalities == frozenset({"text"})
    assert "tool_calling" not in descriptor.capabilities


def test_unavailable_default_adapter_is_fail_closed() -> None:
    assert create_adapter().health().status == "unavailable"


def test_bridge_identity_and_context_are_required() -> None:
    bridge = FakeBridge()
    adapter = ChromeBuiltInAIAdapter(
        bridge, trusted_extension_id="other-extension", trusted_origin=bridge.origin
    )
    with_context = OpenAIModelRequest(
        model="gemini-nano",
        messages=({"role": "user", "content": "hello"},),
        adapter_context=DARExternalRequestContext("id", None, _Cancellation()),
    )
    try:
        asyncio.run(adapter.create_response(with_context))
    except ExternalAdapterError:
        pass
    else:
        raise AssertionError("untrusted extension was accepted")


def test_install_reload_and_facade_fake_bridge(tmp_path: Path) -> None:
    plugin_root = Path(__file__).parents[1]
    registry = ExternalAdapterRegistry(tmp_path / "state")
    registry.install(plugin_root)
    reloaded = ExternalAdapterRegistry(tmp_path / "state")
    facade = reloaded.select("dar.chrome.external")
    facade._adapter.bridge = FakeBridge()  # type: ignore[attr-defined]
    facade._adapter.trusted_extension_id = "trusted-extension"  # type: ignore[attr-defined]
    facade._adapter.trusted_origin = "chrome-extension://trusted-extension"  # type: ignore[attr-defined]
    request = OpenAIModelRequest(
        model="gemini-nano",
        messages=({"role": "user", "content": "hello"},),
        adapter_context=DARExternalRequestContext("id", None, _Cancellation()),
    )
    result = asyncio.run(facade.create_response_async(request))
    assert result.content == "chrome response"


class _Cancellation:
    cancelled = False

    def raise_if_cancelled(self) -> None:
        return None
