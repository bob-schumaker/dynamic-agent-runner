"""Tests for DAR authoring's closed no-tool workflow runner."""

from __future__ import annotations

import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dynamic_agent_runner.openai_client import (  # noqa: E402
    ModelResponse,
    OpenAIClientAdapter,
)

from dar_workflow_server.catalog import PackageCatalog  # noqa: E402
from dar_workflow_server.package_sources import PackageSourceSelectionPolicy  # noqa: E402
from dar_workflow_server.policy import compile_workflow_policy, resolve_capabilities  # noqa: E402
from dar_workflow_server.preparation import WorkflowInvocationPreparationService  # noqa: E402
from dar_workflow_server.profiles import LocalModelProfileControlPlane  # noqa: E402
from dar_workflow_server.registration import WorkflowRegistrationService  # noqa: E402
from dar_workflow_server.runner import (  # noqa: E402
    RunDarWorkflowError,
    RunDarWorkflowRequest,
    WorkflowRunner,
)
from dar_workflow_server.staging import PrivatePackageStager  # noqa: E402
from dar_workflow_server.state import PrivateStateStore  # noqa: E402


NOW = datetime(2026, 8, 23, tzinfo=UTC)
TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "templates"


class FakeResponses:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> ModelResponse:
        self.calls.append(kwargs)
        return ModelResponse(content=self.content)


class FakeClient:
    def __init__(self, content: str) -> None:
        self.responses = FakeResponses(content)


def _runner(tmp_path: Path, *, local: bool = True):
    source = tmp_path / "packages" / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    store = PrivateStateStore(tmp_path / "state")
    source_handle = PackageSourceSelectionPolicy(
        allowed_root=source.parent, store=store
    ).select_directory(source, now=NOW)
    catalog = PackageCatalog(tmp_path / "catalog")
    revision = catalog.import_staged(
        PrivatePackageStager(store=store, private_root=tmp_path / "staging").stage(
            source_handle, now=NOW
        )
    )
    policy = compile_workflow_policy(revision)
    profiles = LocalModelProfileControlPlane(store=store)
    profile = profiles.create(
        model_id="local-model-v1",
        adapter_id="strict-local-adapter-v1",
        base_url="http://127.0.0.1:11434/v1",
        capabilities={"text_generation"},
    )
    registrations = WorkflowRegistrationService(
        profiles=profiles,
        configured_profile_id=profile.profile_id,
        root=tmp_path / "registrations",
    )
    registration = registrations.register(
        workflow_id="document-helper",
        policy=policy,
        capability_resolution=resolve_capabilities(
            policy, available_capabilities={"local_model"}
        ),
    )
    preparation = WorkflowInvocationPreparationService(
        registrations=registrations, catalog=catalog, store=store
    )
    client = FakeClient("completed locally")
    adapter = OpenAIClientAdapter(
        client,
        models=["local-model", "local-model-v1"],
        is_local=local,
    )
    return (
        WorkflowRunner(
            registrations=registrations,
            catalog=catalog,
            preparation=preparation,
            model_adapter=adapter,
        ),
        preparation,
        registration,
        revision,
        client,
    )


def test_runner_executes_one_sealed_no_tool_workflow(tmp_path: Path) -> None:
    runner, preparation, _, _, client = _runner(tmp_path)
    prepared = preparation.prepare(
        workflow_id="document-helper", prompt="Answer me.", now=NOW
    )

    result = runner.run(
        RunDarWorkflowRequest.from_mapping(
            {
                "format_version": 1,
                "workflow_id": "document-helper",
                "prepared_input_id": prepared.prepared_input_id,
            }
        ),
        now=NOW,
    )

    assert result.status == "completed"
    assert result.output == {"message": "completed locally"}
    assert len(client.responses.calls) == 1
    assert runner.traces()[-1].workflow_id == "document-helper"
    assert "Answer me." not in repr(runner.traces()[-1])


def test_request_rejects_raw_prompt_and_unknown_fields() -> None:
    with pytest.raises(RunDarWorkflowError, match="exactly"):
        RunDarWorkflowRequest.from_mapping(
            {
                "format_version": 1,
                "workflow_id": "document-helper",
                "prepared_input_id": "v1.opaque.signature",
                "prompt": "raw input is forbidden",
            }
        )


def test_runner_rejects_hosted_adapter_before_consuming_input(tmp_path: Path) -> None:
    runner, preparation, registration, _, client = _runner(tmp_path, local=False)
    prepared = preparation.prepare(
        workflow_id="document-helper", prompt="Answer me.", now=NOW
    )
    request = RunDarWorkflowRequest.from_mapping(
        {
            "format_version": 1,
            "workflow_id": "document-helper",
            "prepared_input_id": prepared.prepared_input_id,
        }
    )

    with pytest.raises(RunDarWorkflowError, match="strict local"):
        runner.run(request, now=NOW)

    assert (
        preparation.load(
            prepared.prepared_input_id, registration=registration, now=NOW
        ).prompt
        == "Answer me."
    )
    assert client.responses.calls == []


def test_runner_dry_run_preflights_without_consuming_or_calling_model(
    tmp_path: Path,
) -> None:
    runner, preparation, registration, _, client = _runner(tmp_path)
    prepared = preparation.prepare(
        workflow_id="document-helper", prompt="Answer me.", now=NOW
    )
    request = RunDarWorkflowRequest.from_mapping(
        {
            "format_version": 1,
            "workflow_id": "document-helper",
            "prepared_input_id": prepared.prepared_input_id,
        }
    )

    result = runner.dry_run(request, now=NOW)

    assert result.status == "ready"
    assert result.workflow_id == "document-helper"
    assert (
        preparation.load(
            prepared.prepared_input_id, registration=registration, now=NOW
        ).prompt
        == "Answer me."
    )
    assert client.responses.calls == []


def test_runner_fails_dar_preflight_before_model_entry(tmp_path: Path) -> None:
    runner, preparation, _, revision, client = _runner(tmp_path)
    prepared = preparation.prepare(
        workflow_id="document-helper", prompt="Answer me.", now=NOW
    )
    runtime = revision.package_root / "agent-runtime.yaml"
    runtime.chmod(0o600)
    runtime.write_text("not: a DAR package", encoding="utf-8")
    request = RunDarWorkflowRequest.from_mapping(
        {
            "format_version": 1,
            "workflow_id": "document-helper",
            "prepared_input_id": prepared.prepared_input_id,
        }
    )

    with pytest.raises(RunDarWorkflowError, match="registered workflow run failed"):
        runner.run(request, now=NOW)

    assert client.responses.calls == []
