"""Host-owned side-effecting MCP handlers with provenance and audit controls."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from enum import StrEnum
import json
from threading import Lock
from typing import Protocol

from jsonschema import SchemaError, ValidationError
from jsonschema.validators import validator_for

from dynamic_agent_runner import HostToolBinding
from dynamic_agent_runner.registry import ToolResult

from dynamic_agent_runner.workflow_host.action_ledger import (
    ActionLedgerError,
    ActionLedgerEvent,
    ExternalAction,
    WorkflowActionLedger,
)
from dynamic_agent_runner.workflow_host.argument_provenance import (
    ArgumentProvenanceError,
    ArgumentSourcePolicy,
    ArgumentVerificationContext,
    verify_argument_provenance,
)
from dynamic_agent_runner.workflow_host.approvals import (
    WorkflowApproval,
    WorkflowApprovalError,
    WorkflowApprovalStore,
)
from dynamic_agent_runner.workflow_host.descriptor import DeclaredTool
from dynamic_agent_runner.workflow_host.mcp_binding import (
    MCPWorkflowCapabilityBinding,
    MCPWorkflowCapabilityBindingControlPlane,
    MCPWorkflowCapabilityBindingError,
)
from dynamic_agent_runner.workflow_host.mcp_surfaces import (
    CurrentMCPSurfaceClient,
    MCPDiscoveredTool,
    MCPSurfaceSnapshotControlPlane,
    MCPSurfaceSnapshotError,
)
from dynamic_agent_runner.workflow_host.policy import WorkflowPolicy
from dynamic_agent_runner.workflow_host.registration import WorkflowRegistration


class AuthorizedMCPToolClient(CurrentMCPSurfaceClient, Protocol):
    """A current MCP client that may execute a reviewed remote action."""

    def call_tool(
        self, name: str, arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        """Call one remote tool through its authenticated connection."""


class AuthorizedToolBindingError(ValueError):
    """Raised when a side-effecting MCP action is not safe to dispatch."""


class LocalApprovalDecision(StrEnum):
    """The only local-host decisions allowed for a reviewed action."""

    APPROVED = "approved"
    DENIED = "denied"
    CANCELLED = "cancelled"


class LocalActionApprovalBroker(Protocol):
    """Host-only presenter for one exact action; never exposed to the model."""

    def decide(
        self, *, action: ExternalAction, approval: WorkflowApproval
    ) -> LocalApprovalDecision:
        """Return the local human's final decision for this action."""


def create_authorized_mcp_tool_bindings(
    *,
    policy: WorkflowPolicy,
    registration: WorkflowRegistration,
    binding_id: str,
    binding_control: MCPWorkflowCapabilityBindingControlPlane,
    client: AuthorizedMCPToolClient,
    surfaces: MCPSurfaceSnapshotControlPlane,
    provenance: ArgumentVerificationContext,
    workspace_artifact_hashes: Mapping[str, str],
    trace_correlation: str,
    ledger: WorkflowActionLedger,
    approval_store: WorkflowApprovalStore | None = None,
    approval_broker: LocalActionApprovalBroker | None = None,
    now: datetime,
) -> tuple[HostToolBinding, ...]:
    """Create wrapper-private bindings from one immutable side-effect policy."""

    _require_registration(policy, registration, binding_id)
    if (approval_store is None) != (approval_broker is None):
        raise AuthorizedToolBindingError("local approval is unavailable")
    if not isinstance(trace_correlation, str) or not trace_correlation:
        raise AuthorizedToolBindingError("trace correlation is invalid")
    try:
        binding = binding_control.load(binding_id)
        _require_binding(policy, binding)
        _, current_tools = surfaces.verify_reconnected_client_tools(
            binding.snapshot_id, client
        )
        discovered = _tools_by_name(current_tools)
        _require_reviewed_tools(policy, binding, surfaces)
    except (MCPWorkflowCapabilityBindingError, MCPSurfaceSnapshotError) as error:
        raise AuthorizedToolBindingError(
            "MCP capability binding is unavailable"
        ) from error
    counter = _CallCounter(policy.task_invocation.max_total_tool_calls)
    return tuple(
        _binding(
            tool=tool,
            remote_schema=discovered[tool.remote_tool_name].input_schema,
            policy=policy,
            registration=registration,
            binding=binding,
            binding_control=binding_control,
            client=client,
            surfaces=surfaces,
            provenance=_provenance_for_tool(provenance, policy, tool),
            workspace_artifact_hashes=workspace_artifact_hashes,
            trace_correlation=trace_correlation,
            ledger=ledger,
            approval_store=approval_store,
            approval_broker=approval_broker,
            now=now,
            counter=counter,
        )
        for tool in policy.declared_tools
    )


def _binding(
    *,
    tool: DeclaredTool,
    remote_schema: Mapping[str, object],
    policy: WorkflowPolicy,
    registration: WorkflowRegistration,
    binding: MCPWorkflowCapabilityBinding,
    binding_control: MCPWorkflowCapabilityBindingControlPlane,
    client: AuthorizedMCPToolClient,
    surfaces: MCPSurfaceSnapshotControlPlane,
    provenance: ArgumentVerificationContext,
    workspace_artifact_hashes: Mapping[str, str],
    trace_correlation: str,
    ledger: WorkflowActionLedger,
    approval_store: WorkflowApprovalStore | None,
    approval_broker: LocalActionApprovalBroker | None,
    now: datetime,
    counter: _CallCounter,
) -> HostToolBinding:
    _validate_schema(remote_schema)

    def handler(arguments: Mapping[str, object]) -> Mapping[str, object] | ToolResult:
        envelope = _envelope_argument(arguments)
        uses_artifact = _envelope_uses_artifact(envelope)
        try:
            normalized = verify_argument_provenance(envelope, provenance)
            _validate_arguments(remote_schema, normalized)
            current = binding_control.load(binding.binding_id)
            _require_binding(policy, current)
            surfaces.verify_reconnected_client_tools(current.snapshot_id, client)
            surfaces.require_approved_tool(
                current.snapshot_id, tool.remote_tool_name, tool.side_effect
            )
            counter.claim()
            action = ExternalAction(
                workflow_id=registration.workflow_id,
                registration_digest=registration.registration_digest,
                profile_id=registration.profile_id,
                snapshot_id=current.snapshot_id,
                connection_generation=client.current_generation,
                trace_correlation=trace_correlation,
                tool_id=tool.tool_id,
                remote_tool_name=tool.remote_tool_name,
                side_effect=tool.side_effect,
                normalized_arguments=normalized,
                workspace_artifact_hashes=workspace_artifact_hashes,
            )
            intent = ledger.record_intent(action, now=now)
            _require_local_approval(
                action=action,
                intent=intent,
                approval_store=approval_store,
                approval_broker=approval_broker,
                ledger=ledger,
                now=now,
            )
            dispatched = ledger.claim_dispatch(intent.action_id, now=now)
            try:
                result = client.call_tool(tool.remote_tool_name, normalized)
                if not isinstance(result, Mapping):
                    raise AuthorizedToolBindingError(
                        "external action result is invalid"
                    )
            except Exception as error:  # noqa: BLE001 - transport implementations vary.
                _record_unknown_outcome(ledger, dispatched.action_id, now)
                if isinstance(error, AuthorizedToolBindingError):
                    raise
                raise AuthorizedToolBindingError(
                    "external action outcome is unknown"
                ) from error
            try:
                ledger.record_terminal(dispatched.action_id, "completed", now=now)
            except ActionLedgerError as error:
                _record_unknown_outcome(ledger, dispatched.action_id, now)
                raise AuthorizedToolBindingError(
                    "external action outcome is unknown"
                ) from error
            if uses_artifact:
                return ToolResult(
                    tool_id=tool.tool_id,
                    success=True,
                    output={"status": "artifact_result_redacted"},
                )
            return dict(result)
        except (
            ArgumentProvenanceError,
            MCPWorkflowCapabilityBindingError,
            MCPSurfaceSnapshotError,
            ActionLedgerError,
        ) as error:
            raise AuthorizedToolBindingError(
                "external action is unavailable"
            ) from error

    return HostToolBinding(
        canonical_id=f"authorized-mcp:{binding.binding_id}:{tool.tool_id}",
        model_id=tool.tool_id,
        handler=handler,
        label=tool.tool_id,
        description="Call the workflow's reviewed MCP tool.",
        input_schema={
            "type": "object",
            "properties": {"provenance_envelope": {"type": "string"}},
            "required": ["provenance_envelope"],
            "additionalProperties": False,
        },
        side_effect=tool.side_effect,
        approval_required="no",
    )


def _require_local_approval(
    *,
    action: ExternalAction,
    intent: ActionLedgerEvent,
    approval_store: WorkflowApprovalStore | None,
    approval_broker: LocalActionApprovalBroker | None,
    ledger: WorkflowActionLedger,
    now: datetime,
) -> None:
    if approval_store is None or approval_broker is None:
        return
    try:
        approval = approval_store.request(action_digest=intent.action_digest, now=now)
        decision = approval_broker.decide(action=action, approval=approval)
        if decision is LocalApprovalDecision.APPROVED:
            granted = approval_store.grant(
                approval.approval_id, action_digest=intent.action_digest, now=now
            )
            approval_store.consume(
                granted.approval_id, action_digest=intent.action_digest, now=now
            )
            return
        if decision is LocalApprovalDecision.DENIED:
            approval_store.deny(
                approval.approval_id, action_digest=intent.action_digest, now=now
            )
            _record_non_dispatch_terminal(ledger, intent.action_id, "denied", now)
            raise AuthorizedToolBindingError("external action was denied")
        if decision is LocalApprovalDecision.CANCELLED:
            approval_store.deny(
                approval.approval_id, action_digest=intent.action_digest, now=now
            )
            _record_non_dispatch_terminal(ledger, intent.action_id, "cancelled", now)
            raise AuthorizedToolBindingError("external action was cancelled")
        approval_store.deny(
            approval.approval_id, action_digest=intent.action_digest, now=now
        )
        _record_non_dispatch_terminal(ledger, intent.action_id, "failed", now)
    except AuthorizedToolBindingError:
        raise
    except (WorkflowApprovalError, ActionLedgerError) as error:
        _try_record_non_dispatch_terminal(ledger, intent.action_id, "failed", now)
        raise AuthorizedToolBindingError("local approval is unavailable") from error
    except Exception as error:  # noqa: BLE001 - local UI adapters vary.
        _try_record_non_dispatch_terminal(ledger, intent.action_id, "failed", now)
        raise AuthorizedToolBindingError("local approval is unavailable") from error
    raise AuthorizedToolBindingError("local approval decision is invalid")


def _record_non_dispatch_terminal(
    ledger: WorkflowActionLedger, action_id: str, status: str, now: datetime
) -> None:
    ledger.record_terminal(action_id, status, now=now)


def _try_record_non_dispatch_terminal(
    ledger: WorkflowActionLedger, action_id: str, status: str, now: datetime
) -> None:
    try:
        ledger.record_terminal(action_id, status, now=now)
    except ActionLedgerError:
        return


def _require_registration(
    policy: WorkflowPolicy, registration: WorkflowRegistration, binding_id: str
) -> None:
    if (
        registration.package_id != policy.package_id
        or registration.revision_digest != policy.revision_digest
        or registration.policy_digest != policy.policy_digest
        or registration.mcp_binding_id != binding_id
    ):
        raise AuthorizedToolBindingError("registration does not match policy")
    if "mcp_side_effects" not in policy.required_capabilities or not any(
        tool.side_effect != "read" for tool in policy.declared_tools
    ):
        raise AuthorizedToolBindingError("policy does not declare side effects")


def _require_binding(
    policy: WorkflowPolicy, binding: MCPWorkflowCapabilityBinding
) -> None:
    expected = {tool.tool_id: tool.remote_tool_name for tool in policy.declared_tools}
    if (
        binding.policy_digest != policy.policy_digest
        or dict(binding.tool_id_to_remote_name) != expected
    ):
        raise AuthorizedToolBindingError("MCP capability binding does not match policy")


def _require_reviewed_tools(
    policy: WorkflowPolicy,
    binding: MCPWorkflowCapabilityBinding,
    surfaces: MCPSurfaceSnapshotControlPlane,
) -> None:
    for tool in policy.declared_tools:
        surfaces.require_approved_tool(
            binding.snapshot_id, tool.remote_tool_name, tool.side_effect
        )


def _tools_by_name(
    tools: tuple[MCPDiscoveredTool, ...],
) -> dict[str, MCPDiscoveredTool]:
    result = {tool.name: tool for tool in tools}
    if len(result) != len(tools):
        raise AuthorizedToolBindingError("MCP tool surface is invalid")
    return result


def _provenance_for_tool(
    provenance: ArgumentVerificationContext,
    policy: WorkflowPolicy,
    tool: DeclaredTool,
) -> ArgumentVerificationContext:
    rules = policy.task_invocation.argument_sources.get(tool.tool_id)
    if not rules:
        raise AuthorizedToolBindingError("tool argument provenance is unavailable")
    policies = {
        name: _argument_policy(rule.sources, rule.authority)
        for name, rule in rules.items()
    }
    return replace(provenance, argument_policies=policies)


def _argument_policy(sources: tuple[str, ...], authority: bool) -> ArgumentSourcePolicy:
    kinds: set[str] = set()
    references: dict[str, set[str]] = {}
    for source in sources:
        if source == "cited_original_prompt_span":
            kinds.add("prompt_span")
        elif source == "model_generated_transform":
            kinds.add("compose_content_v1")
        else:
            prefix, reference = source.split(":", 1)
            kind = {
                "sealed_structured_field": "sealed_field",
                "artifact_role": "artifact",
                "package_constant": "constant",
            }.get(prefix)
            if kind is None:
                raise AuthorizedToolBindingError("tool argument provenance is invalid")
            kinds.add(kind)
            references.setdefault(kind, set()).add(reference)
    return ArgumentSourcePolicy(
        frozenset(kinds),
        authority,
        {kind: frozenset(values) for kind, values in references.items()},
    )


def _envelope_argument(arguments: Mapping[str, object]) -> str:
    if not isinstance(arguments, Mapping) or set(arguments) != {"provenance_envelope"}:
        raise AuthorizedToolBindingError("model tool arguments are invalid")
    envelope = arguments["provenance_envelope"]
    if not isinstance(envelope, str):
        raise AuthorizedToolBindingError("model tool arguments are invalid")
    return envelope


def _envelope_uses_artifact(envelope: str) -> bool:
    """Return whether one canonical provenance envelope contains an artifact."""

    try:
        parsed = json.loads(envelope)
        sources = parsed.get("sources") if isinstance(parsed, Mapping) else None
    except (TypeError, json.JSONDecodeError):
        return False
    return isinstance(sources, Mapping) and any(
        _source_uses_artifact(source) for source in sources.values()
    )


def _source_uses_artifact(source: object) -> bool:
    if not isinstance(source, Mapping):
        return False
    if source.get("kind") == "artifact":
        return True
    inputs = source.get("inputs")
    return isinstance(inputs, list) and any(
        _source_uses_artifact(item) for item in inputs
    )


def _validate_schema(schema: Mapping[str, object]) -> None:
    try:
        validator_for(schema).check_schema(schema)
    except SchemaError as error:
        raise AuthorizedToolBindingError(
            "reviewed MCP input schema is invalid"
        ) from error


def _validate_arguments(
    schema: Mapping[str, object], arguments: Mapping[str, object]
) -> None:
    try:
        validator = validator_for(schema)(schema)
        validator.validate(dict(arguments))
    except (SchemaError, ValidationError) as error:
        raise AuthorizedToolBindingError(
            "model tool arguments do not match MCP schema"
        ) from error


def _record_unknown_outcome(
    ledger: WorkflowActionLedger, action_id: str, now: datetime
) -> None:
    try:
        ledger.record_terminal(action_id, "outcome_unknown", now=now)
    except ActionLedgerError:
        return


class _CallCounter:
    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._count = 0
        self._lock = Lock()

    def claim(self) -> None:
        with self._lock:
            if self._count >= self._limit:
                raise AuthorizedToolBindingError(
                    "workflow tool-call limit is exhausted"
                )
            self._count += 1
