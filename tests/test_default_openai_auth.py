from __future__ import annotations

from dynamic_agent_runner.openai_client import (
    OpenAIProviderConfig,
    _resolve_default_openai_provider_config,
)


def test_explicit_api_key_prevents_ambient_auth_discovery(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-key")

    config = _resolve_default_openai_provider_config(
        OpenAIProviderConfig(api_key="caller-key")
    )

    assert config.api_key == "caller-key"


def test_explicit_base_url_prevents_endpoint_replacement() -> None:
    source = OpenAIProviderConfig(base_url="http://caller.example/v1")

    config = _resolve_default_openai_provider_config(source)

    assert config.base_url == "http://caller.example/v1"


def test_explicit_api_key_does_not_trigger_auth_discovery(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-key")

    config = _resolve_default_openai_provider_config(
        OpenAIProviderConfig(api_key="caller-key", base_url=None)
    )

    assert config.api_key == "caller-key"


def test_resolver_returns_new_config_without_mutating_caller_input(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-key")
    source = OpenAIProviderConfig(provider_name="default-openai")

    config = _resolve_default_openai_provider_config(source)

    assert config is not source
    assert source.api_key is None
    assert config.api_key == "ambient-key"
    assert config.provider_name == "default-openai"


def test_provider_config_repr_redacts_api_key() -> None:
    config = OpenAIProviderConfig(api_key="secret-test-key")

    assert "secret-test-key" not in repr(config)


def test_openai_api_key_environment_fills_missing_auth(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-key")

    config = _resolve_default_openai_provider_config(OpenAIProviderConfig())

    assert config.api_key == "ambient-key"


def test_openai_api_key_environment_ignores_empty_values(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "   ")

    config = _resolve_default_openai_provider_config(OpenAIProviderConfig())

    assert config.api_key is None


def test_openai_organization_and_project_environment_are_not_copied(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_ORGANIZATION", "org-test")
    monkeypatch.setenv("OPENAI_PROJECT", "project-test")

    config = _resolve_default_openai_provider_config(OpenAIProviderConfig())

    assert config.api_key is None
    assert not hasattr(config, "organization")
    assert not hasattr(config, "project")


def test_discovery_can_be_disabled(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-key")

    config = _resolve_default_openai_provider_config(
        OpenAIProviderConfig(discover_default_auth=False)
    )

    assert config.api_key is None
    assert config.discover_default_auth is False
