"""Tests for sealed prepared inputs to registered DAR workflows."""

from __future__ import annotations

import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dar_workflow_server.catalog import PackageCatalog  # noqa: E402
from dar_workflow_server.package_sources import PackageSourceSelectionPolicy  # noqa: E402
from dar_workflow_server.policy import compile_workflow_policy, resolve_capabilities  # noqa: E402
from dar_workflow_server.preparation import (  # noqa: E402
    PreparedWorkflowInputError,
    WorkflowInvocationPreparationService,
)
from dar_workflow_server.profiles import LocalModelProfileControlPlane  # noqa: E402
from dar_workflow_server.registration import WorkflowRegistrationService  # noqa: E402
from dar_workflow_server.staging import PrivatePackageStager  # noqa: E402
from dar_workflow_server.state import PrivateStateStore  # noqa: E402


NOW = datetime(2026, 8, 23, tzinfo=UTC)
TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "templates"


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
        policy, available_capabilities={"local_model"}
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
        "dar_workflow_server.profiles.getpass.getuser", lambda: "another-user"
    )
    with pytest.raises(PreparedWorkflowInputError, match="invalid"):
        service.load(another.prepared_input_id, registration=registration, now=NOW)
