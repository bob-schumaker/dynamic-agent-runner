"""Tests for strict-local DAR workflow registration."""

from __future__ import annotations

from pathlib import Path
from dataclasses import replace
import json

import pytest


from dynamic_agent_runner.workflow_host.descriptor import (  # noqa: E402
    DeclaredInputConverter,
    InputContract,
    TaskInvocation,
    WorkflowLimits,
)
from dynamic_agent_runner.workflow_host.policy import (  # noqa: E402
    CapabilityResolution,
    WorkflowPolicy,
)
from dynamic_agent_runner.workflow_host.profiles import (  # noqa: E402
    LocalModelProfileControlPlane,
)
from dynamic_agent_runner.workflow_host.registration import (  # noqa: E402
    WorkflowRegistrationError,
    WorkflowRegistrationService,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore  # noqa: E402


def _policy(
    *,
    digest: str = "a" * 64,
    profile_requirement: str = "local-general-model",
    input_converter: bool = False,
) -> WorkflowPolicy:
    return WorkflowPolicy(
        package_id="document-helper",
        revision_digest="b" * 64,
        descriptor_digest="c" * 64,
        policy_digest=digest,
        model_profile_requirement=profile_requirement,
        input_contract=InputContract(
            mode="hybrid",
            additional_context_max_bytes=8192,
            field_precedence="original_prompt",
        ),
        task_invocation=TaskInvocation(
            entrypoint="answer",
            max_total_tool_calls=0,
            allowed_structured_input_fields=(),
            allowed_artifact_roles=(),
            terminal_output_schema_ref="answer-v1",
        ),
        limits=WorkflowLimits(max_steps=1),
        required_capabilities=frozenset({"local_model"}),
        input_converter=(
            DeclaredInputConverter(
                converter_id="qwen-floorplan-input-v1",
                converter_contract_version="v1",
                compatible_runner_contract_id="transformers-generate-v1",
                entrypoint="converters/qwen_floorplan.py",
                asset_digest="a" * 64,
                max_input_bytes=8 * 1024 * 1024,
                max_output_bytes=1024,
                timeout_seconds=30,
            )
            if input_converter
            else None
        ),
    )


def _service(
    tmp_path: Path,
    *,
    profile_requirement: str = "local-general-model",
    model_recipe_digest_provider=None,
):
    store = PrivateStateStore(tmp_path / "state")
    profiles = LocalModelProfileControlPlane(store=store)
    profile = profiles.create(
        model_id="local-model-v1",
        adapter_id="strict-local-adapter-v1",
        base_url="http://127.0.0.1:11434/v1",
        capabilities={"text_generation"},
        profile_requirement=profile_requirement,
    )
    return WorkflowRegistrationService(
        profiles=profiles,
        configured_profile_id=profile.profile_id,
        root=tmp_path / "registrations",
        model_recipe_digest_provider=model_recipe_digest_provider,
    )


def test_registration_binds_eligible_policy_to_configured_local_profile(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    registration = service.register(
        workflow_id="document-helper",
        policy=_policy(),
        capability_resolution=CapabilityResolution("eligible", ()),
    )

    assert registration.workflow_id == "document-helper"
    assert registration.model_id == "local-model-v1"
    assert registration.profile_id.startswith("v1.")
    assert len(registration.profile_digest) == 64
    assert len(registration.registration_digest) == 64
    assert (
        registration.capability_requirements_digest
        == _policy().capability_requirements_digest
    )
    assert service.resolve("document-helper") == registration
    record = json.loads((tmp_path / "registrations" / "registrations.json").read_text())
    assert (
        record["registrations"]["document-helper"]["capability_requirements_digest"]
        == registration.capability_requirements_digest
    )


def test_registration_persists_private_selected_capability_provider_ids(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    policy = replace(
        _policy(), selected_capability_provider_ids=("private-provider-a",)
    )

    registration = service.register(
        workflow_id="document-helper",
        policy=policy,
        capability_resolution=CapabilityResolution("eligible", ()),
    )

    assert registration.selected_capability_provider_ids == ("private-provider-a",)
    record = json.loads((tmp_path / "registrations" / "registrations.json").read_text())
    assert record["registrations"]["document-helper"][
        "selected_capability_provider_ids"
    ] == ["private-provider-a"]
    assert service.resolve("document-helper") == registration


def test_registration_persists_the_model_materials_digest(tmp_path: Path) -> None:
    service = _service(tmp_path)
    policy = replace(_policy(), model_materials_digest="d" * 64)

    registration = service.register(
        workflow_id="document-helper",
        policy=policy,
        capability_resolution=CapabilityResolution("eligible", ()),
    )

    assert registration.model_materials_digest == "d" * 64
    record = json.loads((tmp_path / "registrations" / "registrations.json").read_text())
    assert (
        record["registrations"]["document-helper"]["model_materials_digest"] == "d" * 64
    )
    assert service.resolve("document-helper") == registration

    changed = service.register(
        workflow_id="changed-model-materials",
        policy=replace(_policy(), model_materials_digest="e" * 64),
        capability_resolution=CapabilityResolution("eligible", ()),
    )

    assert changed.registration_digest != registration.registration_digest


def test_registration_persists_the_model_material_sets_digest(tmp_path: Path) -> None:
    service = _service(tmp_path)
    policy = replace(_policy(), model_material_sets_digest="d" * 64)

    registration = service.register(
        workflow_id="document-helper",
        policy=policy,
        capability_resolution=CapabilityResolution("eligible", ()),
    )

    assert registration.model_material_sets_digest == "d" * 64
    record = json.loads((tmp_path / "registrations" / "registrations.json").read_text())
    assert (
        record["registrations"]["document-helper"]["model_material_sets_digest"]
        == "d" * 64
    )
    assert service.resolve("document-helper") == registration

    changed = service.register(
        workflow_id="changed-model-material-sets",
        policy=replace(_policy(), model_material_sets_digest="e" * 64),
        capability_resolution=CapabilityResolution("eligible", ()),
    )

    assert changed.registration_digest != registration.registration_digest


def test_registration_binds_the_model_execution_binding_digest(tmp_path: Path) -> None:
    service = _service(tmp_path)
    registration = service.register(
        workflow_id="document-helper",
        policy=replace(_policy(), model_execution_binding_digest="e" * 64),
        capability_resolution=CapabilityResolution("eligible", ()),
    )

    assert registration.model_execution_binding_digest == "e" * 64
    record = json.loads((tmp_path / "registrations" / "registrations.json").read_text())
    assert (
        record["registrations"]["document-helper"]["model_execution_binding_digest"]
        == "e" * 64
    )


def test_legacy_registration_without_capability_digest_remains_readable(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    registration = service.register(
        workflow_id="document-helper",
        policy=_policy(),
        capability_resolution=CapabilityResolution("eligible", ()),
    )
    path = tmp_path / "registrations" / "registrations.json"
    record = json.loads(path.read_text())
    del record["registrations"]["document-helper"]["capability_requirements_digest"]
    path.write_text(json.dumps(record), encoding="utf-8")

    loaded = service.resolve("document-helper")

    assert loaded.workflow_id == registration.workflow_id
    assert loaded.capability_requirements_digest is None


def test_registration_binds_converter_to_the_host_recipe_digest(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, model_recipe_digest_provider=lambda _profile: "d" * 64)

    registration = service.register(
        workflow_id="document-helper",
        policy=_policy(input_converter=True),
        capability_resolution=CapabilityResolution("eligible", ()),
    )

    assert registration.model_recipe_digest == "d" * 64
    assert service.resolve("document-helper") == registration


def test_registration_rejects_converter_without_a_host_recipe(tmp_path: Path) -> None:
    with pytest.raises(WorkflowRegistrationError, match="model recipe"):
        _service(tmp_path).register(
            workflow_id="document-helper",
            policy=_policy(input_converter=True),
            capability_resolution=CapabilityResolution("eligible", ()),
        )


def test_converter_registration_cannot_be_replaced_or_shared_by_alias(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, model_recipe_digest_provider=lambda _profile: "d" * 64)
    policy = _policy(input_converter=True)
    first = service.register(
        workflow_id="floorplan-a",
        policy=policy,
        capability_resolution=CapabilityResolution("eligible", ()),
    )

    assert (
        service.register(
            workflow_id="floorplan-b",
            policy=policy,
            capability_resolution=CapabilityResolution("eligible", ()),
        ).registration_digest
        != first.registration_digest
    )

    with pytest.raises(WorkflowRegistrationError, match="alias collision"):
        service.register(
            workflow_id="floorplan-a",
            policy=replace(
                policy,
                policy_digest="e" * 64,
                input_converter=replace(policy.input_converter, asset_digest="b" * 64),
            ),
            capability_resolution=CapabilityResolution("eligible", ()),
        )


def test_registration_rejects_unavailable_or_mismatched_profile(tmp_path: Path) -> None:
    with pytest.raises(WorkflowRegistrationError, match="unavailable"):
        _service(tmp_path / "unavailable").register(
            workflow_id="document-helper",
            policy=_policy(),
            capability_resolution=CapabilityResolution(
                "capability_unavailable", ("local_model",)
            ),
        )


def test_registration_binds_a_matching_hosted_execution_profile(tmp_path: Path) -> None:
    store = PrivateStateStore(tmp_path / "state")
    profiles = LocalModelProfileControlPlane(store=store)
    profile = profiles.create_hosted_openai(
        model_id="hosted-model-v1",
        base_url="https://models.example.test/v1",
        capabilities={"text_generation"},
    )
    service = WorkflowRegistrationService(
        profiles=profiles,
        configured_profile_id=profile.profile_id,
        root=tmp_path / "registrations",
    )

    registration = service.register(
        workflow_id="document-helper",
        policy=_policy(profile_requirement="general-language-model-v1"),
        capability_resolution=CapabilityResolution("eligible", ()),
    )

    assert registration.profile_id == profile.profile_id
    assert registration.profile_digest == profile.profile_digest


def test_registration_rejects_mismatched_profile_requirement(tmp_path: Path) -> None:
    with pytest.raises(WorkflowRegistrationError, match="profile requirement"):
        _service(tmp_path / "mismatched").register(
            workflow_id="document-helper",
            policy=_policy(profile_requirement="general-language-model-v1"),
            capability_resolution=CapabilityResolution("eligible", ()),
        )


def test_registration_rejects_alias_collision_and_caller_selected_profile(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    service.register(
        workflow_id="document-helper",
        policy=_policy(),
        capability_resolution=CapabilityResolution("eligible", ()),
    )

    with pytest.raises(WorkflowRegistrationError, match="alias collision"):
        service.register(
            workflow_id="document-helper",
            policy=_policy(digest="d" * 64),
            capability_resolution=CapabilityResolution("eligible", ()),
        )
    with pytest.raises(TypeError):
        service.register(  # type: ignore[call-arg]
            workflow_id="another-workflow",
            policy=_policy(),
            capability_resolution=CapabilityResolution("eligible", ()),
            profile_id="caller-selected",
        )
