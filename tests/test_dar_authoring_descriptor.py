"""Tests for the DAR authoring no-tool workflow descriptor boundary."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from dynamic_agent_runner.models import RuntimeNode


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dar_workflow_server.descriptor import (  # noqa: E402
    WorkflowDescriptor,
    WorkflowDescriptorError,
    validate_no_tool_runtime_nodes,
)


def _descriptor() -> dict[str, object]:
    return {
        "format_version": 1,
        "package_id": "document-helper",
        "purpose": "Answer questions about supplied documents.",
        "dar_runtime": {
            "distribution": "dynamic-agent-runner",
            "required_version": "0.1.15",
        },
        "model": {"profile_requirement": "local-general-model"},
        "skills": [],
        "tools": [],
        "workspace": {
            "accepted_input_types": ["text/plain"],
            "scratch_access": "none",
        },
        "input_contract": {
            "mode": "hybrid",
            "structured_input_schema": None,
            "additional_context_max_bytes": 8192,
            "field_precedence": "original_prompt",
        },
        "task_invocation": {
            "entrypoint": "answer_document_question",
            "allowed_tool_ids": [],
            "max_total_tool_calls": 0,
            "allowed_structured_input_fields": [],
            "allowed_artifact_roles": ["document"],
            "terminal_output_schema_ref": "document-answer-v1",
        },
        "output": {"schema_ref": "document-answer-v1"},
        "limits": {"max_steps": 8},
    }


def test_valid_no_tool_descriptor_compiles() -> None:
    descriptor = WorkflowDescriptor.from_mapping(_descriptor())

    assert descriptor.package_id == "document-helper"
    assert descriptor.task_invocation.max_total_tool_calls == 0
    assert descriptor.workspace.accepted_input_types == ("text/plain",)
    assert descriptor.workspace.scratch_access == "none"
    assert descriptor.limits.max_steps == 8
    validate_no_tool_runtime_nodes(
        descriptor, (RuntimeNode(id="answer", kind="llm_step"),)
    )


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda value: value.update({"tools": ["send_email"]}), "tools"),
        (
            lambda value: value["task_invocation"].update(  # type: ignore[index,union-attr]
                {"allowed_tool_ids": ["send_email"], "max_total_tool_calls": 1}
            ),
            "allowed_tool_ids",
        ),
        (
            lambda value: value["limits"].update({"max_steps": 0}),  # type: ignore[index,union-attr]
            "max_steps",
        ),
        (
            lambda value: value["task_invocation"].pop("terminal_output_schema_ref"),  # type: ignore[index,union-attr]
            "terminal_output_schema_ref",
        ),
    ],
)
def test_no_tool_descriptor_rejects_missing_or_unavailable_capabilities(
    mutation: object, match: str
) -> None:
    value = _descriptor()
    mutation(value)  # type: ignore[operator]

    with pytest.raises(WorkflowDescriptorError, match=match):
        WorkflowDescriptor.from_mapping(value)


def test_no_tool_descriptor_rejects_runtime_tool_console() -> None:
    descriptor = WorkflowDescriptor.from_mapping(_descriptor())
    nodes = (
        RuntimeNode(id="answer", kind="llm_step"),
        RuntimeNode(
            id="console",
            kind="llm_step",
            available_tools=("send_email",),
        ),
    )

    with pytest.raises(WorkflowDescriptorError, match="undeclared tool"):
        validate_no_tool_runtime_nodes(descriptor, nodes)


def test_read_only_mcp_descriptor_allows_only_its_declared_bounded_tool() -> None:
    value = _descriptor()
    value["tools"] = [
        {
            "id": "mail_list_unread",
            "kind": "mcp",
            "remote_tool_name": "list_unread",
            "side_effect": "read",
        }
    ]
    value["task_invocation"] = {
        **value["task_invocation"],  # type: ignore[index]
        "allowed_tool_ids": ["mail_list_unread"],
        "max_total_tool_calls": 3,
    }

    descriptor = WorkflowDescriptor.from_mapping(value)

    assert descriptor.task_invocation.max_total_tool_calls == 3
    assert descriptor.declared_tools[0].remote_tool_name == "list_unread"
    validate_no_tool_runtime_nodes(
        descriptor,
        (
            RuntimeNode(
                id="lookup",
                kind="llm_step",
                available_tools=("mail_list_unread",),
            ),
        ),
    )
    with pytest.raises(WorkflowDescriptorError, match="undeclared tool"):
        validate_no_tool_runtime_nodes(
            descriptor,
            (
                RuntimeNode(
                    id="console",
                    kind="llm_step",
                    available_tools=("mail_list_unread", "send_email"),
                ),
            ),
        )


def test_descriptor_accepts_a_side_effect_with_explicit_authority_sources() -> None:
    value = _descriptor()
    value["tools"] = [
        {
            "id": "mail_send",
            "kind": "mcp",
            "remote_tool_name": "send_email",
            "side_effect": "write",
            "approval_required": True,
        }
    ]
    value["task_invocation"] = {
        **value["task_invocation"],  # type: ignore[index]
        "allowed_tool_ids": ["mail_send"],
        "max_total_tool_calls": 1,
        "allowed_structured_input_fields": ["recipient"],
        "allowed_artifact_roles": ["email_body"],
        "argument_sources": {
            "mail_send": {
                "recipient": {
                    "sources": ["sealed_structured_field:recipient"],
                    "authority": True,
                },
                "body": {
                    "sources": ["artifact_role:email_body"],
                    "authority": False,
                },
            }
        },
    }

    descriptor = WorkflowDescriptor.from_mapping(value)

    assert descriptor.declared_tools[0].side_effect == "write"
    assert descriptor.declared_tools[0].approval_required is True
    assert (
        descriptor.task_invocation.argument_sources["mail_send"]["recipient"].authority
        is True
    )


@pytest.mark.parametrize(
    ("tool_update", "argument_sources", "match"),
    [
        ({"approval_required": False}, {}, "approval_required"),
        ({}, {}, "argument_sources"),
        (
            {},
            {
                "mail_send": {
                    "recipient": {
                        "sources": ["model_generated_transform"],
                        "authority": True,
                    }
                }
            },
            "authority",
        ),
    ],
)
def test_descriptor_rejects_side_effects_without_a_safe_source_contract(
    tool_update: dict[str, object],
    argument_sources: dict[str, object],
    match: str,
) -> None:
    value = _descriptor()
    value["tools"] = [
        {
            "id": "mail_send",
            "kind": "mcp",
            "remote_tool_name": "send_email",
            "side_effect": "write",
            "approval_required": True,
            **tool_update,
        }
    ]
    value["task_invocation"] = {
        **value["task_invocation"],  # type: ignore[index]
        "allowed_tool_ids": ["mail_send"],
        "max_total_tool_calls": 1,
        "argument_sources": argument_sources,
    }

    with pytest.raises(WorkflowDescriptorError, match=match):
        WorkflowDescriptor.from_mapping(value)
