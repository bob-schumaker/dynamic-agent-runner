"""Capability/status reporting contracts for workflow preflight."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum


class CapabilityState(str, Enum):
    """Effective status for one runtime capability."""

    LIVE = "live"
    METADATA_ONLY = "metadata_only"
    MISSING_COLLABORATOR = "missing_collaborator"
    DISABLED = "disabled"
    UNSUPPORTED = "unsupported"
    INVALID = "invalid"


@dataclass(frozen=True)
class CapabilityStatusItem:
    """One capability entry in a preflight report."""

    id: str
    label: str
    state: CapabilityState | str
    category: str
    summary: str
    owner: str | None = None
    required_collaborator: str | None = None
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", CapabilityState(self.state))
        object.__setattr__(self, "details", dict(self.details))


@dataclass(frozen=True)
class CapabilityStatusSummary:
    """Summary counts for a capability report."""

    total: int = 0
    counts_by_state: Mapping[str, int] = field(default_factory=dict)

    @classmethod
    def from_items(
        cls,
        items: Iterable[CapabilityStatusItem],
    ) -> CapabilityStatusSummary:
        """Build deterministic counts from report items."""

        counts = Counter(item.state.value for item in items)
        return cls(
            total=sum(counts.values()),
            counts_by_state=dict(sorted(counts.items())),
        )


@dataclass(frozen=True)
class CapabilityStatusReport:
    """Read-only preflight report for a workflow package."""

    package_id: str | None
    items: tuple[CapabilityStatusItem, ...] = ()
    summary: CapabilityStatusSummary = field(default_factory=CapabilityStatusSummary)
    valid: bool = True
    validation_error: str | None = None

    @classmethod
    def from_items(
        cls,
        *,
        package_id: str | None,
        items: Iterable[CapabilityStatusItem],
        valid: bool = True,
        validation_error: str | None = None,
    ) -> CapabilityStatusReport:
        """Build a report with stable item ordering and summary counts."""

        sorted_items = tuple(
            sorted(items, key=lambda item: (item.category, item.id, item.label))
        )
        return cls(
            package_id=package_id,
            items=sorted_items,
            summary=CapabilityStatusSummary.from_items(sorted_items),
            valid=valid,
            validation_error=validation_error,
        )


def inspect_agent_package_capabilities(
    *_: object, **__: object
) -> CapabilityStatusReport:
    """Inspect a workflow package's capabilities.

    Full package inspection is implemented in the next slice; this placeholder
    keeps the public contract importable without claiming report behavior.
    """

    raise NotImplementedError(
        "capability status inspection is not implemented until Slice 2"
    )
