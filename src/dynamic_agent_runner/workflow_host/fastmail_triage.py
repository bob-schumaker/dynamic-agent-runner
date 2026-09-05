"""Host-owned bounded Fastmail inbox-triage capability binding."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from dynamic_agent_runner import HostToolBinding
from dynamic_agent_runner.workflow_host.mcp_binding import (
    MCPWorkflowCapabilityBindingControlPlane,
    MCPWorkflowCapabilityBindingError,
)
from dynamic_agent_runner.workflow_host.mcp_surfaces import (
    MCPSurfaceSnapshotControlPlane,
    MCPSurfaceSnapshotError,
)
from dynamic_agent_runner.workflow_host.mcp_tools import (
    MCPReadOnlyToolClient,
    MCPToolCallCounter,
)
from dynamic_agent_runner.workflow_host.policy import WorkflowPolicy


class FastmailTriageBindingError(ValueError):
    """Raised when the bounded Fastmail triage tool cannot be constructed."""


@dataclass(frozen=True)
class FastmailTriageQuery:
    """Host-selected constraints and remote arguments for one inbox search."""

    arguments: Mapping[str, object]
    unread: bool
    received_after: datetime
    max_results: int


FastmailTriageQueryBuilder = Callable[[datetime], FastmailTriageQuery]
FastmailTriageResultProjector = Callable[[Mapping[str, object]], Mapping[str, object]]


def default_fastmail_triage_query(now: datetime) -> FastmailTriageQuery:
    """Build the sole host-owned recent-unread search request."""

    return FastmailTriageQuery(
        arguments={
            "query": f"is:unread after:{(now - timedelta(hours=24)).date().isoformat()}",
            "limit": 5,
        },
        unread=True,
        received_after=now - timedelta(hours=24),
        max_results=5,
    )


def project_fastmail_triage_result(
    result: Mapping[str, object],
) -> Mapping[str, object]:
    """Expose a small attachment-free mail projection to the local model."""

    if result.get("isError") is True:
        raise FastmailTriageBindingError("Fastmail triage search failed")
    structured = result.get("structuredContent")
    if isinstance(structured, Mapping):
        values = structured.get("results", ())
    else:
        values = result.get("emails", result.get("items", ()))
    if not isinstance(values, Sequence) or isinstance(values, str | bytes):
        raise FastmailTriageBindingError("Fastmail triage result projection is invalid")
    items = []
    for value in values[:5]:
        if not isinstance(value, Mapping):
            raise FastmailTriageBindingError(
                "Fastmail triage result projection is invalid"
            )
        message_reference = value.get("id", value.get("message_reference"))
        if not isinstance(message_reference, str) or not message_reference:
            raise FastmailTriageBindingError(
                "Fastmail triage result projection is invalid"
            )
        item = {"message_reference": message_reference}
        for output_name, source_name in (
            ("subject", "subject"),
            ("sender", "from"),
            ("received_at", "receivedAt"),
            ("preview", "preview"),
        ):
            value_at_field = value.get(source_name)
            if isinstance(value_at_field, str) and value_at_field:
                item[output_name] = value_at_field
        items.append(item)
    return {"items": items}


def create_fastmail_triage_search_binding(
    *,
    policy: WorkflowPolicy,
    binding_id: str,
    binding_control: MCPWorkflowCapabilityBindingControlPlane,
    client: MCPReadOnlyToolClient,
    surfaces: MCPSurfaceSnapshotControlPlane,
    query_builder: FastmailTriageQueryBuilder,
    result_projector: FastmailTriageResultProjector,
    now: Callable[[], datetime],
) -> HostToolBinding:
    """Bind one zero-argument semantic read capability to a reviewed surface."""

    tool = _triage_declared_tool(policy)
    try:
        binding = binding_control.load(binding_id)
        if binding.policy_digest != policy.policy_digest:
            raise FastmailTriageBindingError("Fastmail capability binding is invalid")
        remote_name = binding.tool_id_to_remote_name.get(tool.tool_id)
        if remote_name != tool.remote_tool_name:
            raise FastmailTriageBindingError("Fastmail capability binding is invalid")
        surfaces.verify_reconnected_client_tools(binding.snapshot_id, client)
        surfaces.require_read_only_tool(binding.snapshot_id, remote_name)
    except (MCPWorkflowCapabilityBindingError, MCPSurfaceSnapshotError) as error:
        raise FastmailTriageBindingError(
            "Fastmail reviewed surface is unavailable"
        ) from error

    counter = MCPToolCallCounter(1)

    def handler(arguments: Mapping[str, Any]) -> Mapping[str, object]:
        if arguments:
            raise FastmailTriageBindingError("search_email does not accept arguments")
        try:
            current_binding = binding_control.load(binding_id)
            if (
                current_binding.policy_digest != policy.policy_digest
                or current_binding.snapshot_id != binding.snapshot_id
                or current_binding.tool_id_to_remote_name.get(tool.tool_id)
                != remote_name
            ):
                raise FastmailTriageBindingError(
                    "Fastmail capability binding is invalid"
                )
            surfaces.verify_reconnected_client_tools(binding.snapshot_id, client)
            surfaces.require_read_only_tool(binding.snapshot_id, remote_name)
        except (MCPWorkflowCapabilityBindingError, MCPSurfaceSnapshotError) as error:
            raise FastmailTriageBindingError(
                "Fastmail reviewed surface is unavailable"
            ) from error
        invocation_time = now()
        query = query_builder(invocation_time)
        _validate_query(query, invocation_time)
        counter.claim()
        result = client.call_tool(remote_name, dict(query.arguments))
        return _validate_projection(result_projector(result))

    return HostToolBinding(
        canonical_id=f"fastmail-triage:{binding_id}:search_email",
        model_id="search_email",
        handler=handler,
        label="search_email",
        description="Search up to five recent unread email messages.",
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        side_effect="read",
        approval_required="no",
    )


def _triage_declared_tool(policy: WorkflowPolicy):
    if (
        policy.task_invocation.max_total_tool_calls != 1
        or policy.task_invocation.allowed_tool_ids != ("search_email",)
        or len(policy.declared_tools) != 1
    ):
        raise FastmailTriageBindingError("Fastmail triage policy is invalid")
    tool = policy.declared_tools[0]
    if tool.tool_id != "search_email" or tool.side_effect != "read":
        raise FastmailTriageBindingError("Fastmail triage policy is invalid")
    return tool


def _validate_query(query: FastmailTriageQuery, invocation_time: datetime) -> None:
    if (
        not isinstance(query, FastmailTriageQuery)
        or query.unread is not True
        or query.max_results != 5
        or query.received_after != invocation_time - timedelta(hours=24)
        or not isinstance(query.arguments, Mapping)
    ):
        raise FastmailTriageBindingError("Fastmail triage query is invalid")


def _validate_projection(value: Mapping[str, object]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise FastmailTriageBindingError("Fastmail triage result projection is invalid")
    items = value.get("items")
    if (
        not isinstance(items, Sequence)
        or isinstance(items, str | bytes)
        or len(items) > 5
    ):
        raise FastmailTriageBindingError("Fastmail triage result projection is invalid")
    if any(not isinstance(item, Mapping) or "attachments" in item for item in items):
        raise FastmailTriageBindingError("Fastmail triage result projection is invalid")
    return dict(value)
