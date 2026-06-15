from __future__ import annotations

import json

import pytest

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.openai_client import (
    OpenAIProviderConfig,
    _resolve_default_openai_provider_config,
)


@pytest.fixture(autouse=True)
def isolate_ambient_auth(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))


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


def test_codex_home_uses_non_empty_environment_path(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    _write_codex_auth(
        codex_home, {"auth_mode": "api_key", "OPENAI_API_KEY": "codex-key"}
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    config = _resolve_default_openai_provider_config(OpenAIProviderConfig())

    assert config.api_key == "codex-key"


def test_codex_home_empty_environment_uses_default_home(
    monkeypatch,
    tmp_path,
) -> None:
    default_codex_home = tmp_path / ".codex"
    default_codex_home.mkdir()
    _write_codex_auth(
        default_codex_home,
        {"auth_mode": "api_key", "OPENAI_API_KEY": "default-codex-key"},
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", "  ")
    monkeypatch.setenv("HOME", str(tmp_path))

    config = _resolve_default_openai_provider_config(OpenAIProviderConfig())

    assert config.api_key == "default-codex-key"


def test_explicit_missing_codex_home_fails(
    monkeypatch,
    tmp_path,
) -> None:
    missing_home = tmp_path / "missing-codex-home"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(missing_home))

    with pytest.raises(ModelExecutionError, match="CODEX_HOME"):
        _resolve_default_openai_provider_config(OpenAIProviderConfig())


def test_codex_config_openai_base_url_fills_missing_base_url(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        'openai_base_url = "http://codex.example/v1"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    config = _resolve_default_openai_provider_config(OpenAIProviderConfig())

    assert config.base_url == "http://codex.example/v1"


def test_caller_base_url_wins_over_codex_config(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        'openai_base_url = "http://codex.example/v1"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    config = _resolve_default_openai_provider_config(
        OpenAIProviderConfig(base_url="http://caller.example/v1")
    )

    assert config.base_url == "http://caller.example/v1"


def test_malformed_codex_config_fails_without_secret_values(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        'openai_base_url = "secret-url\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    with pytest.raises(ModelExecutionError) as exc_info:
        _resolve_default_openai_provider_config(OpenAIProviderConfig())

    message = str(exc_info.value)
    assert "config.toml" in message
    assert "secret-url" not in message


def test_unrelated_malformed_codex_config_does_not_block_auth_discovery(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    _write_codex_auth(
        codex_home, {"auth_mode": "api_key", "OPENAI_API_KEY": "codex-key"}
    )
    (codex_home / "config.toml").write_text(
        """
[otel]
exporter = { otlp-http = {
  endpoint = "https://telemetry.example/path"
}}
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    config = _resolve_default_openai_provider_config(OpenAIProviderConfig())

    assert config.api_key == "codex-key"
    assert config.base_url is None


def test_openai_base_url_is_read_when_later_codex_config_is_not_tomllib_compatible(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        """
openai_base_url = "https://api.example/v1"

[otel]
exporter = { otlp-http = {
  endpoint = "https://telemetry.example/path"
}}
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    config = _resolve_default_openai_provider_config(OpenAIProviderConfig())

    assert config.base_url == "https://api.example/v1"


def test_project_local_codex_config_is_not_read(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    project_root = tmp_path / "project"
    (project_root / ".codex").mkdir(parents=True)
    (project_root / ".codex" / "config.toml").write_text(
        'openai_base_url = "http://project.example/v1"\n',
        encoding="utf-8",
    )
    (project_root / "config.toml").write_text(
        'openai_base_url = "http://cwd.example/v1"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.chdir(project_root)

    config = _resolve_default_openai_provider_config(OpenAIProviderConfig())

    assert config.base_url is None


def test_codex_auth_json_api_key_fills_missing_api_key(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    _write_codex_auth(
        codex_home, {"auth_mode": "api_key", "OPENAI_API_KEY": "codex-key"}
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    config = _resolve_default_openai_provider_config(OpenAIProviderConfig())

    assert config.api_key == "codex-key"


def test_only_chatgpt_codex_auth_selects_chatgpt_backend_provider(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    _write_codex_auth(
        codex_home,
        {"auth_mode": "chatgpt", "tokens": {"access_token": "secret-token"}},
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    config = _resolve_default_openai_provider_config(OpenAIProviderConfig())

    assert config.api_key is None
    assert config.provider_name == "chatgpt-codex"
    assert config.base_url == "https://chatgpt.com/backend-api/codex"
    assert "secret-token" not in repr(config)


def test_codex_auth_json_prefers_api_key_when_api_key_and_chatgpt_auth_exist(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    _write_codex_auth(
        codex_home,
        {
            "OPENAI_API_KEY": "codex-key",
            "tokens": {"access_token": "secret-token"},
        },
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    config = _resolve_default_openai_provider_config(OpenAIProviderConfig())

    assert config.api_key == "codex-key"
    assert config.provider_name is None


def test_codex_auth_json_can_prefer_chatgpt_when_api_key_and_chatgpt_auth_exist(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    _write_codex_auth(
        codex_home,
        {
            "OPENAI_API_KEY": "codex-key",
            "tokens": {"access_token": "secret-token"},
        },
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    config = _resolve_default_openai_provider_config(
        OpenAIProviderConfig(codex_auth_preference="chatgpt_first")
    )

    assert config.api_key is None
    assert config.provider_name == "chatgpt-codex"
    assert config.base_url == "https://chatgpt.com/backend-api/codex"


def test_codex_auth_mode_chatgpt_wins_over_api_key_field(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    _write_codex_auth(
        codex_home,
        {
            "auth_mode": "chatgpt",
            "OPENAI_API_KEY": "codex-key",
            "tokens": {"access_token": "secret-token"},
        },
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    config = _resolve_default_openai_provider_config(OpenAIProviderConfig())

    assert config.api_key is None
    assert config.provider_name == "chatgpt-codex"
    assert config.base_url == "https://chatgpt.com/backend-api/codex"


def test_codex_auth_mode_api_key_wins_over_chatgpt_first_preference(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    _write_codex_auth(
        codex_home,
        {
            "auth_mode": "api_key",
            "OPENAI_API_KEY": "codex-key",
            "tokens": {"access_token": "secret-token"},
        },
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    config = _resolve_default_openai_provider_config(
        OpenAIProviderConfig(codex_auth_preference="chatgpt_first")
    )

    assert config.api_key == "codex-key"
    assert config.provider_name is None


def test_codex_auth_mode_chatgpt_requires_token_without_secret_values(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    _write_codex_auth(
        codex_home,
        {
            "auth_mode": "chatgpt",
            "OPENAI_API_KEY": "secret-codex-key",
        },
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    with pytest.raises(ModelExecutionError) as exc_info:
        _resolve_default_openai_provider_config(OpenAIProviderConfig())

    message = str(exc_info.value)
    assert "ChatGPT auth" in message
    assert "secret-codex-key" not in message


def test_chatgpt_first_falls_back_to_api_key_when_chatgpt_auth_is_absent(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    _write_codex_auth(
        codex_home, {"auth_mode": "api_key", "OPENAI_API_KEY": "codex-key"}
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    config = _resolve_default_openai_provider_config(
        OpenAIProviderConfig(codex_auth_preference="chatgpt_first")
    )

    assert config.api_key == "codex-key"
    assert config.provider_name is None


def test_caller_api_key_wins_over_codex_auth(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    _write_codex_auth(
        codex_home, {"auth_mode": "api_key", "OPENAI_API_KEY": "codex-key"}
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    config = _resolve_default_openai_provider_config(
        OpenAIProviderConfig(api_key="caller-key")
    )

    assert config.api_key == "caller-key"


def test_absent_codex_auth_json_is_not_an_error(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    config = _resolve_default_openai_provider_config(OpenAIProviderConfig())

    assert config.api_key is None


def test_malformed_codex_auth_json_fails_without_secret_values(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text(
        '{"OPENAI_API_KEY": "secret-codex-key"',
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    with pytest.raises(ModelExecutionError) as exc_info:
        _resolve_default_openai_provider_config(OpenAIProviderConfig())

    message = str(exc_info.value)
    assert "auth.json" in message
    assert "secret-codex-key" not in message


@pytest.mark.parametrize(
    "auth_payload",
    [
        {"auth_mode": "personal_access_token", "personal_access_token": "secret-pat"},
        {"auth_mode": "agent_identity", "agent_identity": "secret-agent-jwt"},
    ],
)
def test_unsupported_codex_auth_modes_fail_without_secret_values(
    auth_payload,
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    _write_codex_auth(codex_home, auth_payload)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    with pytest.raises(ModelExecutionError) as exc_info:
        _resolve_default_openai_provider_config(OpenAIProviderConfig())

    message = str(exc_info.value)
    assert "unsupported Codex auth mode" in message
    assert "secret" not in message


def _write_codex_auth(codex_home, payload: dict[str, object]) -> None:
    (codex_home / "auth.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
