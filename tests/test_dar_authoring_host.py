"""Tests for the private host that composes DAR authoring runner services."""

from __future__ import annotations

import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dynamic_agent_runner.openai_client import ModelResponse, OpenAIClientAdapter  # noqa: E402

from dar_workflow_server.host import (  # noqa: E402
    LocalWorkflowHost,
    configure_local_host,
)


NOW = datetime(2026, 8, 23, tzinfo=UTC)
TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "templates"


class _Responses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> ModelResponse:
        self.calls.append(kwargs)
        return ModelResponse(content="completed locally")


class _Client:
    def __init__(self) -> None:
        self.responses = _Responses()


def test_host_composes_human_setup_with_sealed_dry_run(
    tmp_path: Path, monkeypatch
) -> None:
    package_root = tmp_path / "packages"
    source = package_root / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    client = _Client()
    monkeypatch.setattr(
        "dar_workflow_server.host.create_local_adapter",
        lambda profile: OpenAIClientAdapter(
            client, models=[profile.model_id], is_local=True
        ),
    )

    configured = configure_local_host(
        root=tmp_path / "state",
        package_root=package_root,
        model_id="local-model-v1",
        base_url="http://127.0.0.1:11434/v1",
    )
    host = LocalWorkflowHost.open(tmp_path / "state")
    source_handle = host.select_package(source, now=NOW)
    registration = host.register(
        workflow_id="document-helper", package_source_handle=source_handle, now=NOW
    )
    prepared = host.prepare(
        workflow_id=registration.workflow_id, prompt="Answer me.", now=NOW
    )

    result = host.dry_run(
        workflow_id=registration.workflow_id,
        prepared_input_id=prepared.prepared_input_id,
        now=NOW,
    )

    assert configured.profile_id == registration.profile_id
    assert result.status == "ready"
    assert client.responses.calls == []


def test_host_ingresses_a_file_only_under_the_registered_workspace_contract(
    tmp_path: Path, monkeypatch
) -> None:
    package_root = tmp_path / "packages"
    source = package_root / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    descriptor = source / "workflow-descriptor.yaml"
    descriptor.write_text(
        descriptor.read_text(encoding="utf-8").replace(
            "allowed_artifact_roles: []", "allowed_artifact_roles: [document]"
        ),
        encoding="utf-8",
    )
    input_root = tmp_path / "input"
    input_root.mkdir()
    document = input_root / "document.txt"
    document.write_text("document body", encoding="utf-8")
    monkeypatch.setattr(
        "dar_workflow_server.host.create_local_adapter",
        lambda profile: OpenAIClientAdapter(
            _Client(), models=[profile.model_id], is_local=True
        ),
    )

    configure_local_host(
        root=tmp_path / "state",
        package_root=package_root,
        workspace_input_root=input_root,
        model_id="local-model-v1",
        base_url="http://127.0.0.1:11434/v1",
    )
    host = LocalWorkflowHost.open(tmp_path / "state")
    source_handle = host.select_package(source, now=NOW)
    registration = host.register(
        workflow_id="document-helper", package_source_handle=source_handle, now=NOW
    )

    artifact = host.ingress_file(
        workflow_id=registration.workflow_id,
        path=document,
        role="document",
        media_type="text/plain",
        now=NOW,
    )

    assert artifact.artifact_id.startswith("v1.")
    assert artifact.byte_count == len(b"document body")
    with pytest.raises(ValueError, match="not configured"):
        configure_local_host(
            root=tmp_path / "no-ingress-state",
            package_root=package_root,
            model_id="local-model-v1",
            base_url="http://127.0.0.1:11434/v1",
        )
        LocalWorkflowHost.open(tmp_path / "no-ingress-state").ingress_file(
            workflow_id=registration.workflow_id,
            path=document,
            role="document",
            media_type="text/plain",
            now=NOW,
        )
