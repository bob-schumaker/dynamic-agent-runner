from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from dynamic_agent_runner.workflow_host.workflow_authoring_registration import (
    AuthoringContractError,
    CanonicalWorkflowContract,
    DeclarativeWorkflowDefinition,
    ReadyAuthoredWorkflow,
    UnavailableAuthoredWorkflow,
    validate_definition,
)
from dynamic_agent_runner.workflow_host.host import LocalWorkflowHost


NOW = object()


def _contract() -> CanonicalWorkflowContract:
    return CanonicalWorkflowContract(
        workflow_name="floorplan-from-image",
        model_id="qwen25-vl-3b-floorplan-grpo",
        adapter_id="llama-cpp-vision-adapter-v1",
        input_kind="image_artifact",
        output_contract="svg",
        required_capabilities=("multimodal_input",),
    )


def _definition() -> DeclarativeWorkflowDefinition:
    return DeclarativeWorkflowDefinition(
        workflow_name="floorplan-from-image",
        model_id="qwen25-vl-3b-floorplan-grpo",
        adapter_id="llama-cpp-vision-adapter-v1",
        input_kind="image_artifact",
        output_contract="svg",
        required_capabilities=("multimodal_input",),
        package_artifacts={
            "workflow-descriptor.yaml": "format_version: 1\n",
            "agent-design.md": "Create an SVG floorplan.\n",
        },
    )


def test_definition_must_match_the_canonical_contract() -> None:
    definition = _definition()
    mismatched = replace(definition, output_contract="json")

    with pytest.raises(AuthoringContractError, match="does not match"):
        validate_definition(contract=_contract(), definition=mismatched)


def test_contract_preserves_configured_model_identity_without_normalizing_it() -> None:
    contract = replace(_contract(), model_id="Qwen/Qwen2.5-VL-3B")
    definition = replace(_definition(), model_id="Qwen/Qwen2.5-VL-3B")

    validate_definition(contract=contract, definition=definition)


def test_contract_rejects_an_absolute_model_path() -> None:
    with pytest.raises(AuthoringContractError, match="model is invalid"):
        replace(_contract(), model_id="/private/model.gguf")


@pytest.mark.parametrize(
    ("path", "content"),
    [
        ("/tmp/workflow-descriptor.yaml", "format_version: 1\n"),
        ("../agent-design.md", "Create an SVG floorplan.\n"),
        ("tool.py", "print('not allowed')\n"),
        ("unreviewed-tool.yaml", "format_version: 1\n"),
    ],
)
def test_definition_rejects_paths_and_executable_tool_assets(
    path: str, content: str
) -> None:
    with pytest.raises(AuthoringContractError, match="artifact"):
        DeclarativeWorkflowDefinition(
            workflow_name="floorplan-from-image",
            model_id="qwen25-vl-3b-floorplan-grpo",
            adapter_id="llama-cpp-vision-adapter-v1",
            input_kind="image_artifact",
            output_contract="svg",
            required_capabilities=("multimodal_input",),
            package_artifacts={path: content},
        )


def test_results_expose_only_user_facing_fields() -> None:
    ready = ReadyAuthoredWorkflow(
        workflow_name="floorplan-from-image",
        input_contract="one image",
        output_contract="svg",
        invocation="dar-package invoke floorplan-from-image",
    )
    unavailable = UnavailableAuthoredWorkflow(
        capability="multimodal_input",
        requirement="configure the requested local model with image input support",
    )

    assert ready.to_mapping() == {
        "status": "ready",
        "workflow_name": "floorplan-from-image",
        "input_contract": "one image",
        "output_contract": "svg",
        "invocation": "dar-package invoke floorplan-from-image",
    }
    assert unavailable.to_mapping() == {
        "status": "unavailable",
        "capability": "multimodal_input",
        "requirement": "configure the requested local model with image input support",
    }


@pytest.mark.parametrize(
    ("result_type", "kwargs"),
    [
        (
            ReadyAuthoredWorkflow,
            {
                "workflow_name": "floorplan-from-image",
                "input_contract": "one image",
                "output_contract": "svg",
                "invocation": "dar-package invoke /private/host/workflow",
            },
        ),
        (
            UnavailableAuthoredWorkflow,
            {
                "capability": "multimodal_input",
                "requirement": "supply material_set_id=opaque",
            },
        ),
    ],
)
def test_results_reject_internal_details(
    result_type: type[ReadyAuthoredWorkflow] | type[UnavailableAuthoredWorkflow],
    kwargs: dict[str, str],
) -> None:
    with pytest.raises(AuthoringContractError):
        result_type(**kwargs)


def test_host_redacts_a_mismatched_definition_before_authoring_persistence() -> None:
    host = object.__new__(LocalWorkflowHost)

    result = host.register_authored_workflow(
        contract=_contract(),
        definition=replace(_definition(), output_contract="json"),
        now=NOW,
    )

    assert result.to_mapping() == {
        "status": "unavailable",
        "capability": "authoring_contract",
        "requirement": "the workflow definition does not match the requested contract",
    }


def test_host_composes_a_valid_definition_into_a_redacted_saved_handoff() -> None:
    host = object.__new__(LocalWorkflowHost)
    calls: list[str] = []

    def issue_authoring_materials(*, materials: object, now: object) -> object:
        assert now is NOW
        assert materials
        calls.append("issue")
        return SimpleNamespace(material_set_id="internal-material-set")

    def create_authored_package(*, package_name: str, now: object) -> object:
        assert package_name == "floorplan-from-image"
        assert now is NOW
        calls.append("create")
        return SimpleNamespace(output_id="internal-output")

    def write_authored_package_file(**kwargs: object) -> object:
        assert kwargs["output_id"] == "internal-output"
        assert kwargs["now"] is NOW
        calls.append(f"write:{kwargs['relative_path']}")
        return object()

    def finalize_and_select_authored_output(**kwargs: object) -> tuple[object, str]:
        assert kwargs == {
            "output_id": "internal-output",
            "material_set_id": "internal-material-set",
            "now": NOW,
        }
        calls.append("finalize")
        return object(), "internal-source-handle"

    def register(**kwargs: object) -> object:
        assert kwargs == {
            "workflow_id": "floorplan-from-image",
            "package_source_handle": "internal-source-handle",
            "now": NOW,
        }
        calls.append("register")
        return SimpleNamespace(workflow_id="floorplan-from-image")

    host.issue_authoring_materials = issue_authoring_materials
    host.create_authored_package = create_authored_package
    host.write_authored_package_file = write_authored_package_file
    host.finalize_and_select_authored_output = finalize_and_select_authored_output
    host.register = register

    result = host.register_authored_workflow(
        contract=_contract(), definition=_definition(), now=NOW
    )

    assert result.to_mapping() == {
        "status": "ready",
        "workflow_name": "floorplan-from-image",
        "input_contract": "one image artifact",
        "output_contract": "svg",
        "invocation": "dar-package invoke --package-name floorplan-from-image --prompt-stdin",
    }
    assert calls == [
        "issue",
        "create",
        "write:workflow-descriptor.yaml",
        "write:agent-design.md",
        "finalize",
        "register",
    ]


def test_host_redacts_a_finalization_failure_without_registering() -> None:
    host = object.__new__(LocalWorkflowHost)
    registered = False

    host.issue_authoring_materials = lambda **_kwargs: SimpleNamespace(
        material_set_id="internal-material-set"
    )
    host.create_authored_package = lambda **_kwargs: SimpleNamespace(
        output_id="internal-output"
    )
    host.write_authored_package_file = lambda **_kwargs: object()

    def fail_finalization(**_kwargs: object) -> tuple[object, str]:
        raise RuntimeError("/private/host/validation failed")

    def register(**_kwargs: object) -> object:
        nonlocal registered
        registered = True
        return object()

    host.finalize_and_select_authored_output = fail_finalization
    host.register = register

    result = host.register_authored_workflow(
        contract=_contract(), definition=_definition(), now=NOW
    )

    assert result.to_mapping() == {
        "status": "unavailable",
        "capability": "authoring_registration",
        "requirement": "the authored workflow could not be registered",
    }
    assert not registered


@pytest.mark.parametrize("failure_stage", ["create", "register"])
def test_host_redacts_collisions_and_registration_failures(
    failure_stage: str,
) -> None:
    host = object.__new__(LocalWorkflowHost)
    registered = False

    host.issue_authoring_materials = lambda **_kwargs: SimpleNamespace(
        material_set_id="internal-material-set"
    )

    def create_authored_package(**_kwargs: object) -> object:
        if failure_stage == "create":
            raise RuntimeError("/private/packages/floorplan-from-image already exists")
        return SimpleNamespace(output_id="internal-output")

    def register(**_kwargs: object) -> object:
        nonlocal registered
        registered = True
        raise RuntimeError("profile_id=private-profile does not match")

    host.create_authored_package = create_authored_package
    host.write_authored_package_file = lambda **_kwargs: object()
    host.finalize_and_select_authored_output = lambda **_kwargs: (
        object(),
        "internal-source-handle",
    )
    host.register = register

    result = host.register_authored_workflow(
        contract=_contract(), definition=_definition(), now=NOW
    )

    assert result.to_mapping() == {
        "status": "unavailable",
        "capability": "authoring_registration",
        "requirement": "the authored workflow could not be registered",
    }
    assert registered is (failure_stage == "register")
