from __future__ import annotations

from dataclasses import replace

import pytest

from dynamic_agent_runner.workflow_host.workflow_authoring_registration import (
    AuthoringContractError,
    CanonicalWorkflowContract,
    DeclarativeWorkflowDefinition,
    ReadyAuthoredWorkflow,
    UnavailableAuthoredWorkflow,
    validate_definition,
)


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
