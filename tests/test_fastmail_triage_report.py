"""Tests for the bounded Fastmail triage terminal report contract."""

from __future__ import annotations

import json

import pytest


def _report(**overrides: object) -> str:
    value: dict[str, object] = {
        "status": "complete",
        "window": "previous_24_hours",
        "matched_count": 1,
        "truncated": False,
        "items": [
            {
                "message_reference": "opaque-1",
                "subject": "Account notice",
                "classification": "needs_reply",
                "rationale": "A response is requested.",
                "proposed_reply": "Thanks, I will respond shortly.",
            }
        ],
        "warnings": [],
    }
    value.update(overrides)
    return json.dumps(value)


def test_parse_fastmail_triage_report_accepts_bounded_read_only_report() -> None:
    from dynamic_agent_runner.workflow_host.fastmail_triage_report import (
        parse_fastmail_triage_report,
    )

    report = parse_fastmail_triage_report(_report())

    assert report["status"] == "complete"
    assert report["items"] == [
        {
            "message_reference": "opaque-1",
            "subject": "Account notice",
            "classification": "needs_reply",
            "rationale": "A response is requested.",
            "proposed_reply": "Thanks, I will respond shortly.",
        }
    ]


@pytest.mark.parametrize(
    "report",
    [
        "not JSON",
        _report(items=[], matched_count=1),
        _report(truncated=True, matched_count=1),
        _report(status="in_progress"),
        _report(items=[{"message_reference": "opaque-1", "classification": "send"}]),
        _report(
            items=[
                {
                    "message_reference": "opaque-1",
                    "classification": "fyi",
                    "attachments": [],
                }
            ]
        ),
    ],
)
def test_parse_fastmail_triage_report_rejects_unbounded_or_actionable_output(
    report: str,
) -> None:
    from dynamic_agent_runner.workflow_host.fastmail_triage_report import (
        FastmailTriageReportError,
        parse_fastmail_triage_report,
    )

    with pytest.raises(FastmailTriageReportError):
        parse_fastmail_triage_report(report)
