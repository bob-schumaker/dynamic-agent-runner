"""Tests for capability/status reporting."""

from __future__ import annotations


def test_capability_report_types_are_package_exports() -> None:
    import dynamic_agent_runner

    assert dynamic_agent_runner.CapabilityState.LIVE == "live"
    assert dynamic_agent_runner.CapabilityStatusItem is not None
    assert dynamic_agent_runner.CapabilityStatusReport is not None
    assert dynamic_agent_runner.CapabilityStatusSummary is not None
    assert dynamic_agent_runner.inspect_agent_package_capabilities is not None


def test_capability_status_report_summarizes_items_deterministically() -> None:
    from dynamic_agent_runner.capabilities import (
        CapabilityState,
        CapabilityStatusItem,
        CapabilityStatusReport,
    )

    report = CapabilityStatusReport.from_items(
        package_id="demo-agent",
        items=[
            CapabilityStatusItem(
                id="metadata.guardrails",
                label="Guardrail declarations",
                state=CapabilityState.METADATA_ONLY,
                category="metadata",
                summary="Guardrail declarations are preserved but not executed.",
                owner="live-guardrail-execution",
            ),
            CapabilityStatusItem(
                id="runtime.execution",
                label="Finite workflow execution",
                state=CapabilityState.LIVE,
                category="runtime",
                summary="Finite workflow execution is implemented.",
            ),
        ],
    )

    assert report.package_id == "demo-agent"
    assert [item.id for item in report.items] == [
        "metadata.guardrails",
        "runtime.execution",
    ]
    assert report.summary.total == 2
    assert report.summary.counts_by_state == {
        "live": 1,
        "metadata_only": 1,
    }
    assert report.valid is True
