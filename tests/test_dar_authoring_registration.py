"""Tests for strict-local DAR workflow registration."""

from __future__ import annotations

from pathlib import Path
from dataclasses import replace
import json

import pytest


from dynamic_agent_runner.workflow_host.descriptor import (  # noqa: E402
    DeclaredInputConverter,
    DeclaredReviewedCapabilityTool,
    InputContract,
    TaskInvocation,
    WorkflowLimits,
)
from dynamic_agent_runner.workflow_host.capabilities import (  # noqa: E402
    ReviewedCapabilityTemplate,
    ReviewedCapabilityTemplateOutput,
    reviewed_capability_template_digest,
)
from dynamic_agent_runner.workflow_host.reviewed_tool_packages import (  # noqa: E402
    ReviewedCapabilityTemplateControlPlane,
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
    package_id: str = "document-helper",
    revision_digest: str = "b" * 64,
    profile_requirement: str = "local-general-model",
    input_converter: bool = False,
    reviewed_capability: bool = False,
) -> WorkflowPolicy:
    return WorkflowPolicy(
        package_id=package_id,
        revision_digest=revision_digest,
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
            max_total_tool_calls=1 if reviewed_capability else 0,
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
        declared_reviewed_capability_tools=(
            (
                DeclaredReviewedCapabilityTool(
                    tool_id="build_vector_index",
                    capability_id="vector_index.build.v1",
                    contract_version="1",
                    template_digest=_template().template_digest,
                    input_fields=("job_handle",),
                    side_effect="write",
                    approval_required=True,
                ),
            )
            if reviewed_capability
            else ()
        ),
    )


def _template() -> ReviewedCapabilityTemplate:
    outputs = (
        ReviewedCapabilityTemplateOutput(
            "index_generation", "application/octet-stream", 1024, 60
        ),
        ReviewedCapabilityTemplateOutput(
            "index_manifest", "application/json", 1024, 60
        ),
        ReviewedCapabilityTemplateOutput(
            "coverage_report", "application/json", 1024, 60
        ),
    )
    recovery_operations = (
        "acknowledge_visibility",
        "begin_pending_publication",
        "compensate",
        "query_current_outcome",
    )
    return ReviewedCapabilityTemplate(
        capability_id="vector_index.build.v1",
        contract_version="1",
        template_digest=reviewed_capability_template_digest(
            capability_id="vector_index.build.v1",
            contract_version="1",
            input_fields=("job_handle",),
            required_dependency="embedding.execute.v1",
            outputs=outputs,
            max_receipt_bytes=1024,
            approval_class="human_write",
            extension_binding="host-vector-index-v1",
            recovery_operations=recovery_operations,
            success_receipt_schema_digest="d" * 64,
            generation_id_max_bytes=128,
            artifact_handle_max_bytes=128,
            count_ceiling=1024,
            failure_classifications=("host_failure", "publication_failed"),
            enabled=True,
        ),
        input_fields=("job_handle",),
        required_dependency="embedding.execute.v1",
        outputs=outputs,
        max_receipt_bytes=1024,
        approval_class="human_write",
        extension_binding="host-vector-index-v1",
        recovery_operations=recovery_operations,
        success_receipt_schema_digest="d" * 64,
        generation_id_max_bytes=128,
        artifact_handle_max_bytes=128,
        count_ceiling=1024,
        failure_classifications=("host_failure", "publication_failed"),
        enabled=True,
    )


def _service(
    tmp_path: Path,
    *,
    profile_requirement: str = "local-general-model",
    model_recipe_digest_provider=None,
    reviewed_templates: ReviewedCapabilityTemplateControlPlane | None = None,
    current_reviewed_template_provider=None,
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
        reviewed_templates=reviewed_templates,
        current_reviewed_template_provider=current_reviewed_template_provider,
        owner="test-owner",
    )


def test_registration_rejects_a_reviewed_declaration_without_host_template(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)

    with pytest.raises(WorkflowRegistrationError, match="reviewed template"):
        service.register(
            workflow_id="document-helper",
            policy=_policy(reviewed_capability=True),
            capability_resolution=CapabilityResolution("eligible", ()),
        )


def test_registration_binds_a_declared_reviewed_template_to_host_state(
    tmp_path: Path,
) -> None:
    template = _template()
    templates = ReviewedCapabilityTemplateControlPlane(
        store=PrivateStateStore(tmp_path / "template-state"), owner="test-owner"
    )
    templates.create(template=template)
    service = _service(
        tmp_path,
        reviewed_templates=templates,
        current_reviewed_template_provider=lambda _capability_id: template,
    )

    registration = service.register(
        workflow_id="document-helper",
        policy=_policy(reviewed_capability=True),
        capability_resolution=CapabilityResolution("eligible", ()),
    )

    assert registration.policy_digest == _policy(reviewed_capability=True).policy_digest
    assert registration.reviewed_capability_id == "vector_index.build.v1"
    assert registration.reviewed_capability_contract_version == "1"
    assert registration.reviewed_capability_template_digest == template.template_digest
    record = json.loads((tmp_path / "registrations" / "registrations.json").read_text())
    assert record["registrations"]["document-helper"]["reviewed_capability_id"] == (
        "vector_index.build.v1"
    )
    assert (
        record["registrations"]["document-helper"][
            "reviewed_capability_template_digest"
        ]
        == template.template_digest
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
    assert registration.owner == "test-owner"
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
    assert record["registrations"]["document-helper"]["owner"] == "test-owner"


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
    del record["registrations"]["document-helper"]["owner"]
    path.write_text(json.dumps(record), encoding="utf-8")

    loaded = service.resolve("document-helper")

    assert loaded.workflow_id == registration.workflow_id
    assert loaded.capability_requirements_digest is None
    assert loaded.owner is None


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


def test_registration_refresh_requires_the_existing_package_and_revision(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    first = service.register(
        workflow_id="document-helper",
        policy=_policy(),
        capability_resolution=CapabilityResolution("eligible", ()),
    )
    refreshed_policy = _policy(digest="d" * 64)

    refreshed = service.refresh(
        workflow_id="document-helper",
        policy=refreshed_policy,
        capability_resolution=CapabilityResolution("eligible", ()),
    )

    assert refreshed.workflow_id == first.workflow_id
    assert refreshed.package_id == first.package_id
    assert refreshed.revision_digest == first.revision_digest
    assert refreshed.policy_digest == refreshed_policy.policy_digest
    assert service.resolve("document-helper") == refreshed


def test_registration_refresh_claims_only_a_legacy_ownerless_record(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    registration = service.register(
        workflow_id="document-helper",
        policy=_policy(),
        capability_resolution=CapabilityResolution("eligible", ()),
    )
    path = tmp_path / "registrations" / "registrations.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    del records["registrations"]["document-helper"]["owner"]
    path.write_text(json.dumps(records), encoding="utf-8")

    refreshed = service.refresh(
        workflow_id="document-helper",
        policy=_policy(digest="d" * 64),
        capability_resolution=CapabilityResolution("eligible", ()),
    )

    assert refreshed.owner == "test-owner"
    assert refreshed.package_id == registration.package_id
    assert refreshed.revision_digest == registration.revision_digest

    other_owner = WorkflowRegistrationService(
        profiles=service._profiles,
        configured_profile_id=service._configured_profile_id,
        root=tmp_path / "registrations",
        owner="other-owner",
    )
    with pytest.raises(WorkflowRegistrationError, match="owner"):
        other_owner.refresh(
            workflow_id="document-helper",
            policy=_policy(digest="e" * 64),
            capability_resolution=CapabilityResolution("eligible", ()),
        )
    assert service.resolve("document-helper") == refreshed
    with pytest.raises(WorkflowRegistrationError, match="alias collision"):
        service.register(
            workflow_id="document-helper",
            policy=_policy(digest="e" * 64),
            capability_resolution=CapabilityResolution("eligible", ()),
        )
    with pytest.raises(WorkflowRegistrationError, match="immutable identity"):
        service.refresh(
            workflow_id="document-helper",
            policy=_policy(package_id="other-package", digest="e" * 64),
            capability_resolution=CapabilityResolution("eligible", ()),
        )
    with pytest.raises(WorkflowRegistrationError, match="immutable identity"):
        service.refresh(
            workflow_id="document-helper",
            policy=_policy(revision_digest="c" * 64, digest="e" * 64),
            capability_resolution=CapabilityResolution("eligible", ()),
        )
    with pytest.raises(WorkflowRegistrationError, match="profile requirement"):
        service.refresh(
            workflow_id="document-helper",
            policy=_policy(
                digest="e" * 64,
                profile_requirement="general-language-model-v1",
            ),
            capability_resolution=CapabilityResolution("eligible", ()),
        )
    with pytest.raises(WorkflowRegistrationError, match="unavailable"):
        service.refresh(
            workflow_id="document-helper",
            policy=_policy(digest="e" * 64),
            capability_resolution=CapabilityResolution(
                "capability_unavailable", ("local_model",)
            ),
        )
    other_owner = WorkflowRegistrationService(
        profiles=service._profiles,
        configured_profile_id=service._configured_profile_id,
        root=tmp_path / "registrations",
        owner="other-owner",
    )
    with pytest.raises(WorkflowRegistrationError, match="owner"):
        other_owner.refresh(
            workflow_id="document-helper",
            policy=_policy(digest="e" * 64),
            capability_resolution=CapabilityResolution("eligible", ()),
        )
    assert service.resolve("document-helper") == refreshed
