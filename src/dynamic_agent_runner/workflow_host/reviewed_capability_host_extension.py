"""Complete host bindings for reviewed capability templates."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from dynamic_agent_runner.workflow_host.action_ledger import WorkflowActionLedger
from dynamic_agent_runner.workflow_host.approvals import WorkflowApprovalStore
from dynamic_agent_runner.workflow_host.capabilities import ReviewedCapabilityTemplate
from dynamic_agent_runner.workflow_host.reviewed_capability_execution import (
    ReviewedCapabilityApprovalBroker,
    ReviewedCapabilityCompletionError,
    ReviewedCapabilityDispatchRequest,
    ReviewedCapabilityExecutor,
    ReviewedCapabilityHostResult,
)
from dynamic_agent_runner.workflow_host.reviewed_capability_outputs import (
    ReviewedCapabilityCandidateOutputError,
    stage_reviewed_capability_candidates,
)
from dynamic_agent_runner.workflow_host.reviewed_capability_publication import (
    ReviewedCapabilityPublicationCoordinator,
    ReviewedCapabilityPublicationError,
)
from dynamic_agent_runner.workflow_host.reviewed_tool_packages import (
    ReviewedCapabilityTemplateControlPlane,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactOutputHandleService,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


class ReviewedCapabilityHostExtensionError(ValueError):
    """Raised when a reviewed template lacks its required host operations."""


@dataclass(frozen=True)
class _ReviewedCapabilityCompletion:
    template: ReviewedCapabilityTemplate
    artifacts: SealedArtifactOutputHandleService
    publication: ReviewedCapabilityPublicationCoordinator

    def complete(
        self,
        *,
        request: ReviewedCapabilityDispatchRequest,
        result: object,
        reservation_id: str,
        now: datetime,
        **_kwargs: object,
    ) -> dict[str, object]:
        if not isinstance(result, ReviewedCapabilityHostResult):
            raise ReviewedCapabilityCompletionError(recovery_required=False)
        if not isinstance(now, datetime):
            raise ReviewedCapabilityCompletionError(recovery_required=False)
        try:
            retention = {output.retention_seconds for output in self.template.outputs}
            if len(retention) != 1:
                raise ValueError
            staged = stage_reviewed_capability_candidates(
                artifacts=self.artifacts,
                template_digest=self.template.template_digest,
                outputs=self.template.outputs,
                candidates=result.candidates,
                contribution=result.contribution,
                count_ceiling=self.template.count_ceiling,
                receiver_id=request.principal,
                revision_digest=request.package_revision_digest,
                invocation_id=request.run_id,
                expires_at=now + timedelta(seconds=retention.pop()),
                now=now,
            )
        except (ReviewedCapabilityCandidateOutputError, ValueError) as error:
            raise ReviewedCapabilityCompletionError(recovery_required=False) from error
        try:
            return self.publication.complete(
                reservation_id=reservation_id,
                private=staged.private,
                generation_id=staged.contribution.generation_id,
                counts=staged.contribution.counts,
                now=now,
            ).to_mapping()
        except ReviewedCapabilityPublicationError as error:
            raise ReviewedCapabilityCompletionError(recovery_required=True) from error

    def recover(self, *, reservation_id: str, now: datetime) -> dict[str, object]:
        try:
            return self.publication.recover(
                reservation_id=reservation_id, now=now
            ).to_mapping()
        except ReviewedCapabilityPublicationError as error:
            raise ReviewedCapabilityCompletionError(recovery_required=True) from error


@dataclass(frozen=True)
class ReviewedCapabilityHostExtension:
    """One host-owned implementation binding eligible for template discovery."""

    template: ReviewedCapabilityTemplate
    host: object
    dependency_binding_digest: str
    nonce_factory: Callable[[], str]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.template, ReviewedCapabilityTemplate)
            or not isinstance(self.dependency_binding_digest, str)
            or len(self.dependency_binding_digest) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.dependency_binding_digest
            )
            or not callable(self.nonce_factory)
            or any(
                not callable(getattr(self.host, operation, None))
                for operation in (
                    "resolve",
                    "revalidate",
                    "dispatch",
                    "begin_pending_publication",
                    "query_current_outcome",
                    "acknowledge_visibility",
                    "compensate",
                    "assert_generation_current",
                    "unpublish_generation_atomically",
                )
            )
        ):
            raise ReviewedCapabilityHostExtensionError(
                "reviewed capability extension is unavailable"
            )

    def executor(
        self,
        *,
        ledger: WorkflowActionLedger,
        approvals: WorkflowApprovalStore,
        approval_broker: ReviewedCapabilityApprovalBroker,
        reviewed_templates: ReviewedCapabilityTemplateControlPlane,
        artifacts: SealedArtifactOutputHandleService,
        store: PrivateStateStore,
        owner: str,
    ) -> ReviewedCapabilityExecutor:
        """Bind this reviewed host extension to DAR's existing approval ledger."""

        try:
            completion = _ReviewedCapabilityCompletion(
                template=self.template,
                artifacts=artifacts,
                publication=ReviewedCapabilityPublicationCoordinator(
                    store=store,
                    owner=owner,
                    artifacts=artifacts,
                    host=self.host,  # type: ignore[arg-type]
                    failure_classification=self.template.failure_classifications[0],
                    failure_classifications=self.template.failure_classifications,
                    count_ceiling=self.template.count_ceiling,
                    generation_id_max_bytes=self.template.generation_id_max_bytes,
                ),
            )
            return ReviewedCapabilityExecutor(
                resolver=self.host,  # type: ignore[arg-type]
                host=self.host,  # type: ignore[arg-type]
                ledger=ledger,
                approvals=approvals,
                approval_broker=approval_broker,
                reviewed_templates=reviewed_templates,
                current_reviewed_template_provider=lambda _: self.template,
                extension_binding=self.template.extension_binding,
                dependency_binding_digest=self.dependency_binding_digest,
                nonce_factory=self.nonce_factory,
                completion=completion,
            )
        except Exception as error:  # noqa: BLE001 - host boundary stays redacted.
            raise ReviewedCapabilityHostExtensionError(
                "reviewed capability extension is unavailable"
            ) from error
