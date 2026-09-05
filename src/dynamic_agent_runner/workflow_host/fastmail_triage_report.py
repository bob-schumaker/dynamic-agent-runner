"""Validation for the bounded, non-actionable Fastmail triage report."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence


class FastmailTriageReportError(ValueError):
    """Raised when terminal triage output exceeds the host report contract."""


_STATUSES = frozenset({"complete", "needs_review", "failed"})
_CLASSIFICATIONS = frozenset({"urgent", "needs_reply", "fyi", "needs_review"})
_REPORT_FIELDS = frozenset(
    {"status", "window", "matched_count", "truncated", "items", "warnings"}
)
_ITEM_FIELDS = frozenset(
    {"message_reference", "subject", "classification", "rationale", "proposed_reply"}
)


def parse_fastmail_triage_report(value: str) -> dict[str, object]:
    """Parse one terminal report without accepting mailbox actions or raw data."""

    try:
        report = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise FastmailTriageReportError("triage report is not valid JSON") from error
    if not isinstance(report, Mapping) or set(report) != _REPORT_FIELDS:
        raise FastmailTriageReportError("triage report has an invalid shape")
    status = report.get("status")
    if status not in _STATUSES or report.get("window") != "previous_24_hours":
        raise FastmailTriageReportError("triage report has an invalid status or window")
    matched_count = report.get("matched_count")
    truncated = report.get("truncated")
    items = report.get("items")
    warnings = report.get("warnings")
    if (
        not isinstance(matched_count, int)
        or isinstance(matched_count, bool)
        or not 0 <= matched_count <= 5
        or not isinstance(truncated, bool)
        or not isinstance(items, Sequence)
        or isinstance(items, str | bytes)
        or len(items) != matched_count
        or not isinstance(warnings, Sequence)
        or isinstance(warnings, str | bytes)
        or len(warnings) > 5
        or any(not isinstance(warning, str) for warning in warnings)
    ):
        raise FastmailTriageReportError("triage report is not bounded")
    if truncated and matched_count != 5:
        raise FastmailTriageReportError("triage report truncation is not provable")
    normalized_items = [_item(item) for item in items]
    return {
        "status": status,
        "window": "previous_24_hours",
        "matched_count": matched_count,
        "truncated": truncated,
        "items": normalized_items,
        "warnings": list(warnings),
    }


def _item(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) - _ITEM_FIELDS:
        raise FastmailTriageReportError("triage report item is invalid")
    required = ("message_reference", "classification", "rationale")
    if any(
        not isinstance(value.get(field), str) or not value[field] for field in required
    ):
        raise FastmailTriageReportError("triage report item is invalid")
    if value["classification"] not in _CLASSIFICATIONS:
        raise FastmailTriageReportError("triage report item classification is invalid")
    for optional in ("subject", "proposed_reply"):
        if optional in value and (
            not isinstance(value[optional], str) or not value[optional]
        ):
            raise FastmailTriageReportError("triage report item is invalid")
    return dict(value)
