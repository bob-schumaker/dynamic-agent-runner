"""Optional, fail-closed Chrome Built-in AI external adapter."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import inspect
from threading import Lock
from typing import Any, Protocol

from dynamic_agent_runner.external_adapter import (
    DARExternalRequestContext,
    ExternalAdapterError,
    ExternalAdapterUnavailableError,
    ExternalModelAdapterDescriptor,
    ExternalModelAdapterHealth,
    canonical_descriptor_digest,
)
from dynamic_agent_runner.openai_client import ModelResponse, OpenAIModelRequest


class ChromeBuiltInAIBridge(Protocol):
    """Authenticated bridge supplied by the browser-hosting client."""

    extension_id: str
    origin: str

    def health(self) -> ExternalModelAdapterHealth: ...

    def generate(
        self,
        *,
        prompt: str,
        response_format: Mapping[str, Any] | None,
        context: DARExternalRequestContext,
    ) -> str | Mapping[str, Any] | ModelResponse: ...


class _UnavailableBridge:
    extension_id = ""
    origin = ""

    def health(self) -> ExternalModelAdapterHealth:
        return ExternalModelAdapterHealth(
            status="unavailable", error_code="bridge_unavailable"
        )

    def generate(self, **_: Any) -> str:
        raise ExternalAdapterUnavailableError(
            "Chrome Built-in AI bridge is unavailable"
        )


def _descriptor() -> ExternalModelAdapterDescriptor:
    values: dict[str, Any] = {
        "adapter_id": "dar.chrome.external",
        "provider_id": "chrome-built-in-ai",
        "protocol_id": "dar.external-model.v1",
        "protocol_version": "1.0",
        "model_alias": "gemini-nano",
        "canonical_model_id": "chrome://built-in-ai/gemini-nano",
        "execution_location": "local",
        "execution_modes": frozenset({"async"}),
        "input_modalities": frozenset({"text"}),
        "output_modalities": frozenset({"text"}),
        "response_formats": frozenset({"text", "json_schema"}),
        "capabilities": frozenset({"text_generation", "structured_output"}),
        "limits": {"max_context_tokens": 8192, "max_output_tokens": 2048},
        "contract_digest": "0" * 64,
    }
    provisional = object.__new__(ExternalModelAdapterDescriptor)
    for key, value in values.items():
        object.__setattr__(provisional, key, value)
    values["contract_digest"] = canonical_descriptor_digest(provisional)
    return ExternalModelAdapterDescriptor(**values)


@dataclass
class ChromeBuiltInAIAdapter:
    bridge: ChromeBuiltInAIBridge
    trusted_extension_id: str | None = None
    trusted_origin: str | None = None
    _used_correlations: set[str] = field(default_factory=set, init=False, repr=False)
    _correlation_lock: Lock = field(default_factory=Lock, init=False, repr=False)

    adapter_id = "dar.chrome.external"
    protocol_id = "dar.external-model.v1"
    protocol_version = "1.0"

    def describe(self) -> ExternalModelAdapterDescriptor:
        return _descriptor()

    def health(self) -> ExternalModelAdapterHealth:
        try:
            health = self.bridge.health()
        except Exception as error:  # noqa: BLE001 - browser boundary is redacted.
            raise ExternalAdapterUnavailableError(
                "Chrome Built-in AI health failed"
            ) from error
        if not isinstance(health, ExternalModelAdapterHealth):
            raise ExternalAdapterError("Chrome Built-in AI health is invalid")
        return health

    async def create_response(  # noqa: C901 - browser admission is one boundary.
        self, request: OpenAIModelRequest
    ) -> ModelResponse:
        context = request.adapter_context
        if not isinstance(context, DARExternalRequestContext):
            raise ExternalAdapterError("Chrome request is missing DAR context")
        extension_id = getattr(self.bridge, "extension_id", "")
        origin = getattr(self.bridge, "origin", "")
        if not self.trusted_extension_id or not self.trusted_origin:
            raise ExternalAdapterError("Chrome bridge trust is not configured")
        if extension_id != self.trusted_extension_id:
            raise ExternalAdapterError("Chrome extension identity is not trusted")
        if origin != self.trusted_origin:
            raise ExternalAdapterError("Chrome origin identity is not trusted")
        with self._correlation_lock:
            if context.correlation_id in self._used_correlations:
                raise ExternalAdapterError("Chrome request was replayed")
            self._used_correlations.add(context.correlation_id)
        context.cancellation.raise_if_cancelled()
        prompt = "\n\n".join(
            str(message.get("content", "")) for message in request.messages
        )
        if len(prompt.encode("utf-8")) > 256 * 1024:
            raise ExternalAdapterError("Chrome request exceeds the text limit")
        result = self.bridge.generate(
            prompt=prompt,
            response_format=request.response_format,
            context=context,
        )
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, ModelResponse):
            return result
        if isinstance(result, Mapping):
            content = result.get("content")
            if not isinstance(content, str):
                raise ExternalAdapterError("Chrome response is malformed")
            return ModelResponse(content=content, metadata={"provider": "chrome"})
        if not isinstance(result, str):
            raise ExternalAdapterError("Chrome response is malformed")
        return ModelResponse(content=result, metadata={"provider": "chrome"})


def create_adapter(
    bridge: ChromeBuiltInAIBridge | None = None,
    *,
    trusted_extension_id: str | None = None,
    trusted_origin: str | None = None,
) -> ChromeBuiltInAIAdapter:
    """Create an adapter; without a host bridge it remains unavailable."""

    return ChromeBuiltInAIAdapter(
        bridge or _UnavailableBridge(),
        trusted_extension_id=trusted_extension_id,
        trusted_origin=trusted_origin,
    )


__all__ = ["ChromeBuiltInAIBridge", "ChromeBuiltInAIAdapter", "create_adapter"]
