"""Tests for the DAR authoring installation identity and local profiles."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest


from dynamic_agent_runner.workflow_host.profiles import (  # noqa: E402
    FASTMAIL_TRIAGE_LLAMA_CPP_ADAPTER_ID,
    InstallationIdentityProvider,
    LocalModelProfileControlPlane,
    LocalModelProfileError,
    create_fastmail_triage_llama_cpp_adapter,
    create_hosted_openai_adapter,
    create_local_adapter,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore  # noqa: E402
from dynamic_agent_runner.errors import ModelExecutionError  # noqa: E402


def test_installation_identity_is_stable_and_cannot_be_caller_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.getpass.getuser", lambda: "ada"
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.os.getuid", lambda: 501
    )

    provider = InstallationIdentityProvider()

    assert provider.principal == "local-os-user-v1:501:ada"
    assert InstallationIdentityProvider().principal == provider.principal
    with pytest.raises(TypeError):
        InstallationIdentityProvider("caller-selected")  # type: ignore[call-arg]


def test_human_control_plane_creates_immutable_local_model_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.getpass.getuser", lambda: "ada"
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.os.getuid", lambda: 501
    )
    control_plane = LocalModelProfileControlPlane(
        store=PrivateStateStore(tmp_path / "state"),
    )

    created = control_plane.create(
        model_id="local-model-v1",
        adapter_id="strict-local-adapter-v1",
        base_url="http://127.0.0.1:11434/v1",
        capabilities={"text_generation"},
    )
    loaded = control_plane.load(created.profile_id)

    assert loaded == created
    assert loaded.model_id == "local-model-v1"
    assert loaded.adapter_id == "strict-local-adapter-v1"
    assert loaded.base_url == "http://127.0.0.1:11434/v1"
    assert loaded.profile_requirement == "local-general-model"
    assert loaded.capabilities == frozenset({"text_generation"})
    assert len(loaded.profile_digest) == 64
    assert loaded.profile_id.startswith("v1.")


def test_human_control_plane_creates_immutable_hosted_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.getpass.getuser", lambda: "ada"
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.os.getuid", lambda: 501
    )
    control_plane = LocalModelProfileControlPlane(
        store=PrivateStateStore(tmp_path / "state"),
    )

    created = control_plane.create_hosted_openai(
        model_id="hosted-model-v1",
        base_url="https://models.example.test/v1",
        capabilities={"text_generation"},
    )

    loaded = control_plane.load(created.profile_id)

    assert loaded == created
    assert loaded.adapter_id == "hosted-openai-adapter-v1"
    assert loaded.profile_requirement == "general-language-model-v1"
    assert loaded.capabilities == frozenset({"text_generation"})
    assert len(loaded.profile_digest) == 64


def test_control_plane_creates_pinned_fastmail_llama_cpp_profile(
    tmp_path: Path,
) -> None:
    profile = LocalModelProfileControlPlane(
        store=PrivateStateStore(tmp_path / "state")
    ).create_fastmail_triage_llama_cpp()

    adapter = create_fastmail_triage_llama_cpp_adapter(profile)

    assert profile.adapter_id == FASTMAIL_TRIAGE_LLAMA_CPP_ADAPTER_ID
    assert profile.model_id == "Qwen/Qwen2.5-3B-Instruct-GGUF"
    assert profile.execution_model_id == "fastmail-triage-qwen2.5-3b"
    assert profile.base_url is None
    assert adapter.execution_profile_adapter_id == profile.adapter_id
    assert adapter.models == (profile.execution_model_id,)
    assert adapter.resolved_model_id(profile.execution_model_id) == profile.model_id


def test_control_plane_creates_the_pinned_floorplan_vision_profile(
    tmp_path: Path,
) -> None:
    control_plane = LocalModelProfileControlPlane(
        store=PrivateStateStore(tmp_path / "state")
    )

    profile = control_plane.create_floorplan_vision_llama_cpp()

    assert profile.model_id == "qwen25-vl-3b-floorplan-grpo"
    assert profile.execution_model_id == "qwen25-vl-3b-floorplan-grpo"
    assert profile.adapter_id == "floorplan-vision-llama-cpp-adapter-v1"
    assert profile.runner_id == "llama-cpp-v1"
    assert profile.capabilities == frozenset({"text_generation", "multimodal_input"})


def test_control_plane_creates_the_generic_qwen25_vl_floorplan_profile(
    tmp_path: Path,
) -> None:
    control_plane = LocalModelProfileControlPlane(
        store=PrivateStateStore(tmp_path / "state")
    )

    profile = control_plane.create_qwen25_vl_3b_floorplan_grpo_transformers_peft()

    assert profile.model_id == "qwen25-vl-3b-floorplan-grpo"
    assert (
        profile.adapter_id == "qwen25-vl-3b-floorplan-grpo-transformers-peft-adapter-v1"
    )
    assert profile.runner_id == "transformers-peft-v1"
    assert profile.capabilities == frozenset({"text_generation", "multimodal_input"})


def test_profile_digest_rejects_a_forged_hosted_endpoint(tmp_path: Path) -> None:
    store = PrivateStateStore(tmp_path / "state")
    control_plane = LocalModelProfileControlPlane(store=store)
    created = control_plane.create_hosted_openai(
        model_id="hosted-model-v1",
        base_url="https://models.example.test/v1",
        capabilities={"text_generation"},
    )
    forged_profile_id = store.issue(
        kind="local_model_profile",
        owner=InstallationIdentityProvider().principal,
        payload={
            "model_id": created.model_id,
            "adapter_id": created.adapter_id,
            "base_url": "https://other-models.example.test/v1",
            "profile_requirement": created.profile_requirement,
            "capabilities": sorted(created.capabilities),
            "profile_digest": created.profile_digest,
        },
        expires_at=datetime.max.replace(tzinfo=UTC),
        now=datetime.now(UTC),
    )

    with pytest.raises(LocalModelProfileError, match="invalid"):
        control_plane.load(forged_profile_id)


def test_hosted_adapter_never_discovers_ambient_openai_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = LocalModelProfileControlPlane(
        store=PrivateStateStore(tmp_path / "state")
    ).create_hosted_openai(
        model_id="hosted-model-v1",
        base_url="https://models.example.test/v1",
        capabilities={"text_generation"},
    )
    observed: dict[str, object] = {}
    sentinel = object()

    def fake_create(config: object, **kwargs: object) -> object:
        observed["config"] = config
        observed["kwargs"] = kwargs
        return sentinel

    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.create_openai_adapter_from_provider_config",
        fake_create,
    )

    assert create_hosted_openai_adapter(profile) is sentinel
    assert observed["config"].discover_default_auth is False  # type: ignore[union-attr]
    assert observed["kwargs"]["execution_profile_adapter_id"] == profile.adapter_id  # type: ignore[index]


def test_profile_rejects_empty_or_nonlocal_definition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.getpass.getuser", lambda: "ada"
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.os.getuid", lambda: 501
    )
    control_plane = LocalModelProfileControlPlane(
        store=PrivateStateStore(tmp_path / "state"),
    )

    with pytest.raises(LocalModelProfileError, match="model_id"):
        control_plane.create(
            model_id="",
            adapter_id="strict-local-adapter-v1",
            base_url="http://127.0.0.1:11434/v1",
            capabilities={"text_generation"},
        )
    with pytest.raises(LocalModelProfileError, match="local"):
        control_plane.create(
            model_id="hosted-model-v1",
            adapter_id="remote-adapter-v1",
            base_url="http://127.0.0.1:11434/v1",
            capabilities={"text_generation"},
        )


def test_profile_requires_loopback_endpoint_and_constructs_local_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.getpass.getuser", lambda: "ada"
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.os.getuid", lambda: 501
    )
    control_plane = LocalModelProfileControlPlane(
        store=PrivateStateStore(tmp_path / "state"),
    )

    with pytest.raises(LocalModelProfileError, match="loopback"):
        control_plane.create(
            model_id="local-model-v1",
            adapter_id="strict-local-adapter-v1",
            base_url="https://models.example.test/v1",
            capabilities={"text_generation"},
        )

    created = control_plane.create(
        model_id="local-model-v1",
        adapter_id="strict-local-adapter-v1",
        base_url="http://localhost:11434/v1",
        capabilities={"text_generation"},
    )
    observed: dict[str, object] = {}
    sentinel = object()

    def fake_create(config: object) -> object:
        observed["config"] = config
        return sentinel

    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.create_local_openai_adapter",
        fake_create,
    )

    assert create_local_adapter(created) is sentinel
    config = observed["config"]
    assert config.base_url == "http://localhost:11434/v1"  # type: ignore[union-attr]
    assert config.model_aliases == ("local-model",)  # type: ignore[union-attr]
    assert config.expected_model_id == "local-model-v1"  # type: ignore[union-attr]


def test_human_control_plane_creates_apple_profile_without_http_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.getpass.getuser", lambda: "ada"
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.os.getuid", lambda: 501
    )
    preflight_calls: list[object] = []
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.preflight_apple_foundation_models",
        lambda: preflight_calls.append(object()),
    )
    control_plane = LocalModelProfileControlPlane(
        store=PrivateStateStore(tmp_path / "state"),
    )

    created = control_plane.create_apple(model_id="apple-system-language-model")
    loaded = control_plane.load(created.profile_id)

    assert loaded == created
    assert loaded.adapter_id == "apple-foundation-models-adapter-v1"
    assert loaded.base_url is None
    assert loaded.capabilities == frozenset({"text_generation"})
    assert len(preflight_calls) == 1


def test_apple_profile_preflight_failure_does_not_issue_a_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.preflight_apple_foundation_models",
        lambda: (_ for _ in ()).throw(ModelExecutionError("unavailable")),
    )
    store = PrivateStateStore(tmp_path / "state")
    control_plane = LocalModelProfileControlPlane(store=store)
    monkeypatch.setattr(
        store, "issue", lambda **_: pytest.fail("preflight must precede persistence")
    )

    with pytest.raises(ModelExecutionError, match="unavailable"):
        control_plane.create_apple(model_id="apple-system-language-model")


def test_forged_apple_profile_with_http_data_is_rejected(tmp_path: Path) -> None:
    store = PrivateStateStore(tmp_path / "state")
    control_plane = LocalModelProfileControlPlane(store=store)
    profile_id = store.issue(
        kind="local_model_profile",
        owner=InstallationIdentityProvider().principal,
        payload={
            "model_id": "apple-system-language-model",
            "adapter_id": "apple-foundation-models-adapter-v1",
            "base_url": "http://127.0.0.1:11434/v1",
            "profile_requirement": "local-general-model",
            "capabilities": ["text_generation"],
        },
        expires_at=datetime.max.replace(tzinfo=UTC),
        now=datetime.now(UTC),
    )

    with pytest.raises(LocalModelProfileError, match="invalid"):
        control_plane.load(profile_id)


def test_legacy_profile_without_digest_fails_closed(tmp_path: Path) -> None:
    store = PrivateStateStore(tmp_path / "state")
    control_plane = LocalModelProfileControlPlane(store=store)
    profile_id = store.issue(
        kind="local_model_profile",
        owner=InstallationIdentityProvider().principal,
        payload={
            "model_id": "local-model-v1",
            "adapter_id": "strict-local-adapter-v1",
            "base_url": "http://127.0.0.1:11434/v1",
            "profile_requirement": "local-general-model",
            "capabilities": ["text_generation"],
        },
        expires_at=datetime.max.replace(tzinfo=UTC),
        now=datetime.now(UTC),
    )

    with pytest.raises(LocalModelProfileError, match="invalid"):
        control_plane.load(profile_id)
