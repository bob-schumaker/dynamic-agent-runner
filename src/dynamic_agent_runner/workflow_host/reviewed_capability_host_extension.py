"""Complete host bindings for reviewed capability templates."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from dynamic_agent_runner.workflow_host.action_ledger import WorkflowActionLedger
from dynamic_agent_runner.workflow_host.approvals import WorkflowApprovalStore
from dynamic_agent_runner.workflow_host.capabilities import ReviewedCapabilityTemplate
from dynamic_agent_runner.workflow_host.reviewed_capability_execution import (
    ReviewedCapabilityApprovalBroker,
    ReviewedCapabilityExecutor,
)
from dynamic_agent_runner.workflow_host.reviewed_tool_packages import (
    ReviewedCapabilityTemplateControlPlane,
)


class ReviewedCapabilityHostExtensionError(ValueError):
    """Raised when a reviewed template lacks its required host operations."""


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
    ) -> ReviewedCapabilityExecutor:
        """Bind this reviewed host extension to DAR's existing approval ledger."""

        try:
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
            )
        except Exception as error:  # noqa: BLE001 - host boundary stays redacted.
            raise ReviewedCapabilityHostExtensionError(
                "reviewed capability extension is unavailable"
            ) from error
