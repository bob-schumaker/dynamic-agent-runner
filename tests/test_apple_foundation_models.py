from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.openai_client import build_openai_request
from dynamic_agent_runner.apple_foundation_models import (
    AppleFoundationModelConfig,
    create_apple_foundation_model_async_adapter,
)


@pytest.fixture(autouse=True)
def eligible_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "dynamic_agent_runner.apple_foundation_models.sys.platform", "darwin"
    )


def test_apple_config_and_factory_are_importable_without_sdk() -> None:
    config = AppleFoundationModelConfig()
    adapter = create_apple_foundation_model_async_adapter(config)

    assert config.model_aliases == ("apple-system-language-model",)
    assert adapter.models == ("apple-system-language-model",)
    assert adapter.is_local is True


def test_factory_accepts_injected_availability_and_session_seams() -> None:
    config = AppleFoundationModelConfig(
        availability_checker=lambda: (True, None),
        session_factory=lambda _instructions: object(),
    )

    adapter = create_apple_foundation_model_async_adapter(config)

    assert adapter.is_local is True


def test_non_darwin_generation_fails_before_sdk_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "dynamic_agent_runner.apple_foundation_models.sys.platform", "linux"
    )
    adapter = create_apple_foundation_model_async_adapter()
    request = build_openai_request(
        model="apple-system-language-model",
        messages=[{"role": "user", "content": "hello"}],
    )

    with pytest.raises(ModelExecutionError, match="macOS"):
        asyncio.run(adapter.create_response(request))


def test_unavailable_system_model_reports_actionable_reason() -> None:
    adapter = create_apple_foundation_model_async_adapter(
        AppleFoundationModelConfig(
            availability_checker=lambda: (False, "Apple Intelligence is disabled")
        )
    )
    request = build_openai_request(
        model="apple-system-language-model",
        messages=[{"role": "user", "content": "hello"}],
    )

    with pytest.raises(ModelExecutionError, match="Apple Intelligence is disabled"):
        asyncio.run(adapter.create_response(request))


@pytest.mark.parametrize(
    "request_kwargs",
    [
        {"tools": [{"type": "function", "name": "lookup"}]},
        {"response_format": {"type": "json_object"}},
        {"extra": {"stream": True}},
        {"extra": {"top_p": 0.5}},
    ],
)
def test_unsupported_request_features_fail_before_session_creation(
    request_kwargs: dict[str, object],
) -> None:
    calls: list[str] = []
    adapter = create_apple_foundation_model_async_adapter(
        AppleFoundationModelConfig(
            availability_checker=lambda: (True, None),
            session_factory=lambda _instructions: calls.append("session") or object(),
        )
    )
    request = build_openai_request(
        model="apple-system-language-model",
        messages=[{"role": "user", "content": "hello"}],
        **request_kwargs,
    )

    with pytest.raises(ModelExecutionError):
        asyncio.run(adapter.create_response(request))
    assert calls == []


def test_public_import_does_not_require_apple_sdk() -> None:
    assert Path("src/dynamic_agent_runner/apple_foundation_models.py").exists()
