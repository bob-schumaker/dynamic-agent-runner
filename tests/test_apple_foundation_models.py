from __future__ import annotations

import asyncio
from dataclasses import dataclass
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


@dataclass
class FakeGeneratedJSON:
    value: str

    def to_json(self) -> str:
        return self.value


class FakeSession:
    def __init__(self, instructions: str | None, result: object = "answer") -> None:
        self.instructions = instructions
        self.result = result
        self.prompts: list[tuple[str, object]] = []

    async def respond(self, prompt: str, **kwargs: object) -> object:
        self.prompts.append((prompt, kwargs))
        return self.result


class CancelledSession(FakeSession):
    async def respond(self, prompt: str, **kwargs: object) -> object:
        raise asyncio.CancelledError


def test_text_request_preserves_instructions_and_ordered_history() -> None:
    sessions: list[FakeSession] = []

    def make_session(instructions: str | None) -> FakeSession:
        session = FakeSession(instructions)
        sessions.append(session)
        return session

    adapter = create_apple_foundation_model_async_adapter(
        AppleFoundationModelConfig(
            availability_checker=lambda: (True, None), session_factory=make_session
        )
    )
    request = build_openai_request(
        model="apple-system-language-model",
        messages=[
            {"role": "system", "content": "Be concise."},
            {"role": "developer", "content": "Use plain language."},
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Earlier"},
            {"role": "user", "content": "Now"},
        ],
    )

    asyncio.run(adapter.create_response(request))

    assert len(sessions) == 1
    assert sessions[0].instructions == "Be concise.\nUse plain language."
    assert sessions[0].prompts[0][0] == "user: First\nassistant: Earlier\nuser: Now"


def test_each_request_gets_a_fresh_session_and_maps_generation_options() -> None:
    sessions: list[FakeSession] = []

    def make_session(instructions: str | None) -> FakeSession:
        session = FakeSession(instructions)
        sessions.append(session)
        return session

    adapter = create_apple_foundation_model_async_adapter(
        AppleFoundationModelConfig(
            availability_checker=lambda: (True, None), session_factory=make_session
        )
    )
    request = build_openai_request(
        model="apple-system-language-model",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
        max_output_tokens=32,
    )

    asyncio.run(adapter.create_response(request))
    asyncio.run(adapter.create_response(request))

    assert len(sessions) == 2
    assert sessions[0] is not sessions[1]
    assert sessions[0].prompts[0][1] == {
        "options": {"temperature": 0.2, "max_output_tokens": 32}
    }


def test_structured_generation_uses_explicit_schema_and_normalizes_json() -> None:
    sessions: list[FakeSession] = []

    def make_session(instructions: str | None) -> FakeSession:
        session = FakeSession(instructions, FakeGeneratedJSON('{"ok": true}'))
        sessions.append(session)
        return session

    adapter = create_apple_foundation_model_async_adapter(
        AppleFoundationModelConfig(
            availability_checker=lambda: (True, None), session_factory=make_session
        )
    )
    request = build_openai_request(
        model="apple-system-language-model",
        messages=[{"role": "user", "content": "return json"}],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "result", "schema": {"type": "object"}},
        },
    )

    response = asyncio.run(adapter.create_response(request))

    assert response.content == '{"ok": true}'
    assert sessions[0].prompts[0][1]["json_schema"] == {"type": "object"}


def test_cancellation_propagates_without_provider_retry() -> None:
    adapter = create_apple_foundation_model_async_adapter(
        AppleFoundationModelConfig(
            availability_checker=lambda: (True, None),
            session_factory=lambda _instructions: CancelledSession(None),
        )
    )
    request = build_openai_request(
        model="apple-system-language-model",
        messages=[{"role": "user", "content": "cancel"}],
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(adapter.create_response(request))
