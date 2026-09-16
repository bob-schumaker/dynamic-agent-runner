"""Approval-gated dispatch for one sealed reviewed host capability job."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from dynamic_agent_runner.workflow_host.action_ledger import (
    ActionLedgerError,
    ActionLedgerEvent,
    ReviewedCapabilityReservationRequest,
    WorkflowActionLedger,
    reviewed_capability_reservation_digest,
)
from dynamic_agent_runner.workflow_host.approvals import (
    WorkflowApproval,
    WorkflowApprovalError,
    WorkflowApprovalStore,
)
from dynamic_agent_runner.workflow_host.authorized_tools import LocalApprovalDecision
from dynamic_agent_runner.workflow_host.reviewed_capability_jobs import (
    ReviewedCapabilityJobError,
    ReviewedCapabilityJobResolver,
    SealedReviewedCapabilityJob,
    revalidate_sealed_reviewed_capability_job,
    resolve_sealed_reviewed_capability_job,
)


class ReviewedCapabilityDispatchError(ValueError):
    """Raised when a reviewed capability cannot safely dispatch."""


@dataclass(frozen=True)
class ReviewedCapabilityDispatchRequest:
    """The non-secret invocation identity supplied by DAR's workflow runtime."""

    run_id: str
    package_registration_digest: str
    package_revision_digest: str
    declared_call_site_id: str
    principal: str
    arguments: Mapping[str, object]
    template_capability_id: str
    template_contract_version: str
    template_digest: str


class ReviewedCapabilityApprovalBroker(Protocol):
    """Host-only human decision presenter for an exact reservation digest."""

    def decide(
        self, *, approval: WorkflowApproval, reservation_digest: str
    ) -> LocalApprovalDecision: ...


class ReviewedCapabilityDispatchHost(Protocol):
    """Host extension boundary after DAR completes admission and approval."""

    def dispatch(
        self, *, job: SealedReviewedCapabilityJob, reservation_id: str
    ) -> None: ...


class ReviewedCapabilityExecutor:
    """Resolve, approve, reserve, revalidate, and dispatch exactly one job."""

    def __init__(
        self,
        *,
        resolver: ReviewedCapabilityJobResolver,
        host: ReviewedCapabilityDispatchHost,
        ledger: WorkflowActionLedger,
        approvals: WorkflowApprovalStore,
        approval_broker: ReviewedCapabilityApprovalBroker,
        extension_binding: str,
        dependency_binding_digest: str,
        nonce_factory: Callable[[], str],
    ) -> None:
        if (
            not callable(getattr(resolver, "resolve", None))
            or not callable(getattr(resolver, "revalidate", None))
            or not callable(getattr(host, "dispatch", None))
            or not callable(getattr(approval_broker, "decide", None))
            or not isinstance(extension_binding, str)
            or not extension_binding
            or not isinstance(dependency_binding_digest, str)
            or len(dependency_binding_digest) != 64
            or not callable(nonce_factory)
        ):
            raise ReviewedCapabilityDispatchError("reviewed capability is unavailable")
        self._resolver = resolver
        self._host = host
        self._ledger = ledger
        self._approvals = approvals
        self._approval_broker = approval_broker
        self._extension_binding = extension_binding
        self._dependency_binding_digest = dependency_binding_digest
        self._nonce_factory = nonce_factory

    def dispatch(
        self, request: ReviewedCapabilityDispatchRequest, *, now: datetime
    ) -> ActionLedgerEvent:
        """Dispatch at most once, with all mutable host bindings rechecked."""

        try:
            job = resolve_sealed_reviewed_capability_job(
                arguments=request.arguments,
                resolver=self._resolver,
                principal=request.principal,
                template_capability_id=request.template_capability_id,
                template_contract_version=request.template_contract_version,
                template_digest=request.template_digest,
                extension_binding=self._extension_binding,
                dependency_binding_digest=self._dependency_binding_digest,
                now=now,
            )
            reservation_request = ReviewedCapabilityReservationRequest(
                run_id=request.run_id,
                package_registration_digest=request.package_registration_digest,
                package_revision_digest=request.package_revision_digest,
                declared_call_site_id=request.declared_call_site_id,
                template_capability_id=request.template_capability_id,
                template_contract_version=request.template_contract_version,
                template_digest=request.template_digest,
                job_issuer_id=job.issuer_id,
                job_opaque_id=job.opaque_id,
                job_revision=job.revision,
                job_digest=job.digest,
                principal=request.principal,
                approval_nonce=self._approval_nonce(),
            )
            reservation = self._approve_and_reserve(reservation_request, now=now)
        except (
            ActionLedgerError,
            ReviewedCapabilityJobError,
            WorkflowApprovalError,
        ) as error:
            raise ReviewedCapabilityDispatchError(
                "reviewed capability is unavailable"
            ) from error
        if reservation.replayed:
            return ActionLedgerEvent(
                reservation.action_id, reservation.action_digest, "replayed", True
            )
        try:
            revalidated = revalidate_sealed_reviewed_capability_job(
                job=job,
                resolver=self._resolver,
                dependency_binding_digest=self._dependency_binding_digest,
                now=now,
            )
            dispatched = self._ledger.claim_reviewed_capability_dispatch(
                reservation.action_id, now=now
            )
            self._host.dispatch(job=revalidated, reservation_id=reservation.action_id)
        except (ActionLedgerError, ReviewedCapabilityJobError) as error:
            self._abort(reservation.action_id, now=now)
            raise ReviewedCapabilityDispatchError(
                "reviewed capability is unavailable"
            ) from error
        except Exception as error:  # noqa: BLE001 - host extension boundary varies.
            self._abort(reservation.action_id, now=now)
            raise ReviewedCapabilityDispatchError(
                "reviewed capability is unavailable"
            ) from error
        return dispatched

    def _approval_nonce(self) -> str:
        nonce = self._nonce_factory()
        if not isinstance(nonce, str) or not nonce.startswith("v1."):
            raise ReviewedCapabilityDispatchError("reviewed capability is unavailable")
        return nonce

    def _approve_and_reserve(
        self, request: ReviewedCapabilityReservationRequest, *, now: datetime
    ) -> ActionLedgerEvent:
        digest = reviewed_capability_reservation_digest(request)
        approval = self._approvals.request(action_digest=digest, now=now)
        try:
            decision = self._approval_broker.decide(
                approval=approval, reservation_digest=digest
            )
        except Exception as error:  # noqa: BLE001 - host approval UI boundary varies.
            self._deny(approval, digest, now=now)
            raise WorkflowApprovalError("approval is unavailable") from error
        if decision is not LocalApprovalDecision.APPROVED:
            self._deny(approval, digest, now=now)
            raise WorkflowApprovalError("approval is unavailable")
        granted = self._approvals.grant(
            approval.approval_id, action_digest=digest, now=now
        )
        return self._ledger.reserve_approved_reviewed_capability(
            request, approval_id=granted.approval_id, now=now
        )

    def _deny(self, approval: WorkflowApproval, digest: str, *, now: datetime) -> None:
        try:
            self._approvals.deny(approval.approval_id, action_digest=digest, now=now)
        except WorkflowApprovalError:
            return

    def _abort(self, reservation_id: str, *, now: datetime) -> None:
        try:
            self._ledger.abort_reviewed_capability(reservation_id, now=now)
        except ActionLedgerError:
            return
