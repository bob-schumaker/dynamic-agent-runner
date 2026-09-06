"""Tests for sealed prepared inputs to registered DAR workflows."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


from dynamic_agent_runner.workflow_host.catalog import PackageCatalog  # noqa: E402
from dynamic_agent_runner.workflow_host.package_sources import (
    PackageSourceSelectionPolicy,
)  # noqa: E402
from dynamic_agent_runner.workflow_host.policy import (
    compile_workflow_policy,
    resolve_capabilities,
)  # noqa: E402
from dynamic_agent_runner.workflow_host.preparation import (  # noqa: E402
    PreparedWorkflowInputError,
    WorkflowInvocationPreparationService,
)
from dynamic_agent_runner.workflow_host.profiles import LocalModelProfileControlPlane  # noqa: E402
from dynamic_agent_runner.workflow_host.registration import WorkflowRegistrationService  # noqa: E402
from dynamic_agent_runner.workflow_host.staging import PrivatePackageStager  # noqa: E402
from dynamic_agent_runner.workflow_host.state import PrivateStateStore  # noqa: E402
from dynamic_agent_runner.workflow_host.workspace_ingress import (  # noqa: E402
    MaterializedWorkspaceInputArtifact,
)


NOW = datetime(2026, 8, 23, tzinfo=UTC)
TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "specs"
    / "agent-engineering-plugin-migration"
    / "legacy-dar-authoring"
    / "templates"
)


class _ArtifactVerifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def load(
        self,
        artifact_id: str,
        *,
        workflow_id: str,
        registration_digest: str,
        now: datetime,
    ) -> object:
        self.calls.append((artifact_id, workflow_id, registration_digest))
        if artifact_id != "v1.artifact":
            raise ValueError("invalid artifact")
        return object()


class _MaterializingArtifactVerifier(_ArtifactVerifier):
    def materialize(
        self,
        artifact_id: str,
        *,
        workflow_id: str,
        registration_digest: str,
        now: datetime,
    ) -> MaterializedWorkspaceInputArtifact:
        self.load(
            artifact_id,
            workflow_id=workflow_id,
            registration_digest=registration_digest,
            now=now,
        )
        return MaterializedWorkspaceInputArtifact(
            artifact_id, "sha256:" + "a" * 64, "body", "<p>Hello</p>"
        )


def _prepared_service(tmp_path: Path):
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
    capability_resolution = resolve_capabilities(
        policy, available_capabilities={"text_generation"}
    )
    registration = registrations.register(
        workflow_id="document-helper",
        policy=policy,
        capability_resolution=capability_resolution,
    )
    return (
        WorkflowInvocationPreparationService(
            registrations=registrations, catalog=catalog, store=store
        ),
        registrations,
        registration,
        policy,
        capability_resolution,
    )


def test_preparation_seals_prompt_and_bounded_additional_context(
    tmp_path: Path,
) -> None:
    service, _, registration, _, _ = _prepared_service(tmp_path)

    prepared = service.prepare(
        workflow_id="document-helper",
        prompt="Answer this request.",
        additional_context="Use the supplied background.",
        now=NOW,
    )
    loaded = service.load(
        prepared.prepared_input_id, registration=registration, now=NOW
    )

    assert prepared.workflow_id == "document-helper"
    assert prepared.registration_digest == registration.registration_digest
    assert not hasattr(prepared, "prompt")
    assert loaded.prompt == "Answer this request."
    assert loaded.additional_context == "Use the supplied background."


def test_preparation_seals_only_verified_opaque_workspace_artifact_ids(
    tmp_path: Path,
) -> None:
    _, registrations, registration, _, _ = _prepared_service(tmp_path)
    verifier = _ArtifactVerifier()
    service = WorkflowInvocationPreparationService(
        registrations=registrations,
        catalog=PackageCatalog(tmp_path / "catalog"),
        store=PrivateStateStore(tmp_path / "state"),
        artifact_verifier=verifier,
    )

    prepared = service.prepare(
        workflow_id="document-helper",
        prompt="Answer this request.",
        workspace_artifact_ids=("v1.artifact",),
        now=NOW,
    )
    loaded = service.load(
        prepared.prepared_input_id, registration=registration, now=NOW
    )

    assert loaded.workspace_artifact_ids == ("v1.artifact",)
    assert verifier.calls == [
        ("v1.artifact", "document-helper", registration.registration_digest)
    ]


def test_preparation_rejects_unverified_or_duplicate_workspace_artifact_ids(
    tmp_path: Path,
) -> None:
    service, _, _, _, _ = _prepared_service(tmp_path)

    with pytest.raises(PreparedWorkflowInputError, match="artifact"):
        service.prepare(
            workflow_id="document-helper",
            prompt="answer",
            workspace_artifact_ids=("v1.artifact",),
            now=NOW,
        )


def test_preparation_materializes_only_verified_private_artifacts(
    tmp_path: Path,
) -> None:
    _, registrations, registration, _, _ = _prepared_service(tmp_path)
    verifier = _MaterializingArtifactVerifier()
    service = WorkflowInvocationPreparationService(
        registrations=registrations,
        catalog=PackageCatalog(tmp_path / "catalog"),
        store=PrivateStateStore(tmp_path / "state"),
        artifact_verifier=verifier,
    )
    prepared = service.prepare(
        workflow_id="document-helper",
        prompt="Answer this request.",
        workspace_artifact_ids=("v1.artifact",),
        now=NOW,
    )
    sealed = service.load(
        prepared.prepared_input_id, registration=registration, now=NOW
    )

    artifacts = service.materialize_workspace_artifacts(
        sealed, registration=registration, now=NOW
    )

    assert artifacts == (
        MaterializedWorkspaceInputArtifact(
            "v1.artifact", "sha256:" + "a" * 64, "body", "<p>Hello</p>"
        ),
    )
    with pytest.raises(PreparedWorkflowInputError, match="artifact"):
        service.prepare(
            workflow_id="document-helper",
            prompt="answer",
            workspace_artifact_ids=("v1.artifact", "v1.artifact"),
            now=NOW,
        )


def test_preparation_rejects_raw_structured_input_and_oversized_context(
    tmp_path: Path,
) -> None:
    service, _, _, _, _ = _prepared_service(tmp_path)

    with pytest.raises(PreparedWorkflowInputError, match="structured"):
        service.prepare(
            workflow_id="document-helper",
            prompt="answer",
            structured_input={"recipient": "sally@example.com"},
            now=NOW,
        )
    with pytest.raises(PreparedWorkflowInputError, match="additional_context"):
        service.prepare(
            workflow_id="document-helper",
            prompt="answer",
            additional_context="x" * 8193,
            now=NOW,
        )


def test_prepared_input_rejects_changed_expired_or_cross_registration(
    tmp_path: Path,
) -> None:
    service, registrations, registration, policy, capability_resolution = (
        _prepared_service(tmp_path)
    )
    prepared = service.prepare(workflow_id="document-helper", prompt="answer", now=NOW)
    alternate = registrations.register(
        workflow_id="other-document-helper",
        policy=policy,
        capability_resolution=capability_resolution,
    )

    with pytest.raises(PreparedWorkflowInputError, match="prepared input"):
        service.load(
            f"{prepared.prepared_input_id}x", registration=registration, now=NOW
        )
    with pytest.raises(PreparedWorkflowInputError, match="registration"):
        service.load(prepared.prepared_input_id, registration=alternate, now=NOW)
    with pytest.raises(PreparedWorkflowInputError, match="expired"):
        service.load(
            prepared.prepared_input_id,
            registration=registration,
            now=NOW + timedelta(minutes=6),
        )
    with pytest.raises(TypeError):
        service.load(  # type: ignore[call-arg]
            prepared.prepared_input_id,
            registration=registration,
            prompt="unsealed replacement",
            now=NOW,
        )


def test_prepared_input_is_single_use_and_principal_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _, registration, _, _ = _prepared_service(tmp_path)
    prepared = service.prepare(workflow_id="document-helper", prompt="answer", now=NOW)

    assert (
        service.consume(
            prepared.prepared_input_id, registration=registration, now=NOW
        ).prompt
        == "answer"
    )
    with pytest.raises(PreparedWorkflowInputError, match="invalid"):
        service.load(prepared.prepared_input_id, registration=registration, now=NOW)

    another = service.prepare(workflow_id="document-helper", prompt="answer", now=NOW)
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.getpass.getuser",
        lambda: "another-user",
    )
    with pytest.raises(PreparedWorkflowInputError, match="invalid"):
        service.load(another.prepared_input_id, registration=registration, now=NOW)
