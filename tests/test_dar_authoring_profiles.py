"""Tests for the DAR authoring installation identity and local profiles."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dar_workflow_server.profiles import (  # noqa: E402
    InstallationIdentityProvider,
    LocalModelProfileControlPlane,
    LocalModelProfileError,
    create_local_adapter,
)
from dar_workflow_server.state import PrivateStateStore  # noqa: E402


def test_installation_identity_is_stable_and_cannot_be_caller_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("dar_workflow_server.profiles.getpass.getuser", lambda: "ada")
    monkeypatch.setattr("dar_workflow_server.profiles.os.getuid", lambda: 501)

    provider = InstallationIdentityProvider()

    assert provider.principal == "local-os-user-v1:501:ada"
    assert InstallationIdentityProvider().principal == provider.principal
    with pytest.raises(TypeError):
        InstallationIdentityProvider("caller-selected")  # type: ignore[call-arg]


def test_human_control_plane_creates_immutable_local_model_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("dar_workflow_server.profiles.getpass.getuser", lambda: "ada")
    monkeypatch.setattr("dar_workflow_server.profiles.os.getuid", lambda: 501)
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
    assert loaded.profile_id.startswith("v1.")


def test_profile_rejects_empty_or_nonlocal_definition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("dar_workflow_server.profiles.getpass.getuser", lambda: "ada")
    monkeypatch.setattr("dar_workflow_server.profiles.os.getuid", lambda: 501)
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
    monkeypatch.setattr("dar_workflow_server.profiles.getpass.getuser", lambda: "ada")
    monkeypatch.setattr("dar_workflow_server.profiles.os.getuid", lambda: 501)
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
        "dar_workflow_server.profiles.create_local_openai_adapter", fake_create
    )

    assert create_local_adapter(created) is sentinel
    config = observed["config"]
    assert config.base_url == "http://localhost:11434/v1"  # type: ignore[union-attr]
    assert config.model_aliases == ("local-model-v1",)  # type: ignore[union-attr]
    assert config.expected_model_id == "local-model-v1"  # type: ignore[union-attr]
