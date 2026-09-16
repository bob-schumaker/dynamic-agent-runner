"""Complete host bindings for reviewed capability templates."""

from __future__ import annotations

from dataclasses import dataclass

from dynamic_agent_runner.workflow_host.capabilities import ReviewedCapabilityTemplate


class ReviewedCapabilityHostExtensionError(ValueError):
    """Raised when a reviewed template lacks its required host operations."""


@dataclass(frozen=True)
class ReviewedCapabilityHostExtension:
    """One host-owned implementation binding eligible for template discovery."""

    template: ReviewedCapabilityTemplate
    host: object

    def __post_init__(self) -> None:
        if not isinstance(self.template, ReviewedCapabilityTemplate) or any(
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
        ):
            raise ReviewedCapabilityHostExtensionError(
                "reviewed capability extension is unavailable"
            )
