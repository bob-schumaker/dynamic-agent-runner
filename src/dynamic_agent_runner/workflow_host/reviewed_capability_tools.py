"""Model-facing bindings for host-reviewed sealed capability calls."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime

from dynamic_agent_runner import HostToolBinding

from dynamic_agent_runner.workflow_host.action_ledger import WorkflowActionLedger
from dynamic_agent_runner.workflow_host.action_ledger import ExternalAction
from dynamic_agent_runner.workflow_host.approvals import (
    WorkflowApproval,
    WorkflowApprovalStore,
)
from dynamic_agent_runner.workflow_host.authorized_tools import (
    LocalActionApprovalBroker,
    LocalApprovalDecision,
)
from dynamic_agent_runner.workflow_host.descriptor import DeclaredReviewedCapabilityTool
from dynamic_agent_runner.workflow_host.registration import WorkflowRegistration
from dynamic_agent_runner.workflow_host.reviewed_capability_execution import (
    ReviewedCapabilityDispatchError,
    ReviewedCapabilityDispatchRequest,
)
from dynamic_agent_runner.workflow_host.reviewed_capability_host_extension import (
    ReviewedCapabilityHostExtension,
    ReviewedCapabilityHostExtensionError,
)
from dynamic_agent_runner.workflow_host.reviewed_tool_packages import (
    ReviewedCapabilityTemplateControlPlane,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactOutputHandleService,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


class ReviewedCapabilityToolBindingError(ValueError):
    """Raised when a reviewed capability cannot safely bind to one workflow run."""


class _ReviewedCapabilityLocalApprovalAdapter:
    """Present one reviewed reservation through the normal local broker."""

    def __init__(
        self,
        *,
        declaration: DeclaredReviewedCapabilityTool,
        registration: WorkflowRegistration,
        run_id: str,
        broker: LocalActionApprovalBroker,
    ) -> None:
        self._declaration = declaration
        self._registration = registration
        self._run_id = run_id
        self._broker = broker

    def decide(
        self, *, approval: WorkflowApproval, reservation_digest: str
    ) -> LocalApprovalDecision:
        """Keep the reservation digest in DAR while presenting one safe action."""

        del reservation_digest
        action = ExternalAction(
            workflow_id=self._registration.workflow_id,
            registration_digest=self._registration.registration_digest,
            profile_id=self._registration.profile_id,
            snapshot_id=self._declaration.template_digest,
            connection_generation=0,
            trace_correlation=self._run_id,
            tool_id=self._declaration.tool_id,
            remote_tool_name=self._declaration.capability_id,
            side_effect=self._declaration.side_effect,
            normalized_arguments={},
            workspace_artifact_hashes={},
        )
        return self._broker.decide(action=action, approval=approval)


def create_reviewed_capability_tool_binding(
    *,
    declaration: DeclaredReviewedCapabilityTool,
    registration: WorkflowRegistration,
    run_id: str,
    principal: str,
    extension: ReviewedCapabilityHostExtension,
    ledger: WorkflowActionLedger,
    approvals: WorkflowApprovalStore,
    approval_broker: LocalActionApprovalBroker,
    reviewed_templates: ReviewedCapabilityTemplateControlPlane,
    artifacts: SealedArtifactOutputHandleService,
    store: PrivateStateStore,
    owner: str,
    now: Callable[[], datetime],
) -> HostToolBinding:
    """Bind the exact declaration to one extension without package authority."""

    if (
        not isinstance(declaration, DeclaredReviewedCapabilityTool)
        or not isinstance(registration, WorkflowRegistration)
        or not isinstance(run_id, str)
        or not run_id
        or not isinstance(principal, str)
        or not principal
        or not isinstance(extension, ReviewedCapabilityHostExtension)
        or declaration.capability_id != extension.template.capability_id
        or declaration.contract_version != extension.template.contract_version
        or declaration.template_digest != extension.template.template_digest
        or declaration.input_fields != ("job_handle",)
        or declaration.side_effect != "write"
        or not declaration.approval_required
        or not callable(now)
    ):
        raise ReviewedCapabilityToolBindingError("reviewed capability is unavailable")
    try:
        reviewed_approval_broker = _ReviewedCapabilityLocalApprovalAdapter(
            declaration=declaration,
            registration=registration,
            run_id=run_id,
            broker=approval_broker,
        )
        executor = extension.executor(
            ledger=ledger,
            approvals=approvals,
            approval_broker=reviewed_approval_broker,
            reviewed_templates=reviewed_templates,
            artifacts=artifacts,
            store=store,
            owner=owner,
        )
    except ReviewedCapabilityHostExtensionError as error:
        raise ReviewedCapabilityToolBindingError(
            "reviewed capability is unavailable"
        ) from error

    def handler(arguments: Mapping[str, object]) -> object:
        try:
            return executor.dispatch(
                ReviewedCapabilityDispatchRequest(
                    run_id=run_id,
                    package_registration_digest=registration.registration_digest,
                    package_revision_digest=registration.revision_digest,
                    declared_call_site_id=declaration.tool_id,
                    principal=principal,
                    arguments=arguments,
                    template_capability_id=declaration.capability_id,
                    template_contract_version=declaration.contract_version,
                    template_digest=declaration.template_digest,
                ),
                now=now(),
            )
        except ReviewedCapabilityDispatchError as error:
            raise ReviewedCapabilityToolBindingError(
                "reviewed capability is unavailable"
            ) from error

    return HostToolBinding(
        canonical_id=(
            f"reviewed_capability:{declaration.capability_id}:"
            f"{declaration.contract_version}"
        ),
        model_id=declaration.tool_id,
        handler=handler,
        label=declaration.tool_id,
        description="Run one approved host-created sealed capability job.",
        input_schema={
            "type": "object",
            "properties": {"job_handle": {"type": "string"}},
            "required": ["job_handle"],
            "additionalProperties": False,
        },
        side_effect="write",
        approval_required="human_approval",
    )
