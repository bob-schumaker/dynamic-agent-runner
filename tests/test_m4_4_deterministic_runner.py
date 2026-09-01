"""Deterministic successor-lifecycle acceptance tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from m4_4_deterministic import (
    run_authoring_boundary_attack,
    run_document_summary,
    run_document_embedding,
    run_council_request,
    run_deferred_runtime_boundaries,
    run_email_file_body,
    run_file_provenance_missing_ingress,
    run_generic_email_send,
    run_guardrail_input,
    run_guardrail_missing_registry,
    run_tool_input_guardrail_missing_registry,
    run_guardrail_tool_input,
    run_hybrid_brief,
    run_invocation_schema_boundary_attack,
    run_mailbox_triage,
    run_mcp_missing_connection,
    run_no_tool_graph_and_skill,
    run_oauth_reconnect,
    run_portable_package_handoff,
    run_side_effect_recovery,
    run_structured_single_model_review,
    run_fixture_contract,
    supported_scenario_adapter_ids,
)
from m4_4_scenarios import load_m44_coverage, load_m44_scenario


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures"


def test_each_positive_successor_scenario_has_a_feature_specific_adapter() -> None:
    coverage = load_m44_coverage(FIXTURE_ROOT / "m4-4-successor-coverage.json")

    assert supported_scenario_adapter_ids() == {
        entry.scenario_id
        for entry in coverage.entries
        if entry.expected_status == "pass"
    }


def test_fixture_contract_dispatches_every_external_manifest_scenario() -> None:
    coverage = load_m44_coverage(FIXTURE_ROOT / "m4-4-successor-coverage.json")
    sources = {
        load_m44_scenario(source).scenario_id: source
        for root in (
            FIXTURE_ROOT / "dar-authoring" / "m4-4",
            FIXTURE_ROOT / "m4-4-successor",
        )
        for source in root.glob("*.json")
    }

    results = {
        scenario_id: run_fixture_contract(load_m44_scenario(sources[scenario_id]))
        for scenario_id in {entry.scenario_id for entry in coverage.entries}
    }

    assert set(results) == set(sources)
    assert all(result["model_calls"] >= 0 for result in results.values())


def test_authoring_boundary_attack_refuses_before_finalization_or_dispatch() -> None:
    scenario = load_m44_scenario(
        FIXTURE_ROOT / "dar-authoring" / "m4-4" / "authoring-boundary-attack.json"
    )

    result = run_authoring_boundary_attack(scenario)

    assert result == {
        "terminal_phase": "authoring_validation",
        "finalized": False,
        "model_calls": 0,
        "tool_dispatches": 0,
    }


@pytest.mark.parametrize(
    ("filename", "rewrite"),
    (
        ("mcp-tooling-missing-connection.json", "write"),
        ("read-only-mcp-missing-connection.json", "read"),
        ("oauth-missing-connection.json", "read"),
    ),
)
def test_mcp_missing_connection_stops_before_registration_or_dispatch(
    filename: str, rewrite: str
) -> None:
    scenario = load_m44_scenario(FIXTURE_ROOT / "m4-4-successor" / filename)

    result = run_mcp_missing_connection(scenario, rewrite=rewrite)

    assert result == {
        "terminal_phase": "capability_preflight",
        "registered": False,
        "model_calls": 0,
        "tool_dispatches": 0,
    }


def test_file_provenance_missing_ingress_stops_before_preparation_or_dispatch() -> None:
    scenario = load_m44_scenario(
        FIXTURE_ROOT / "m4-4-successor" / "file-provenance-missing-ingress.json"
    )

    result = run_file_provenance_missing_ingress(scenario)

    assert result == {
        "terminal_phase": "capability_preflight",
        "prepared": False,
        "model_calls": 0,
        "tool_dispatches": 0,
    }


def test_deferred_runtime_boundaries_finalize_then_stop_at_host_preflight() -> None:
    scenario = load_m44_scenario(
        FIXTURE_ROOT / "m4-4-successor" / "deferred-runtime-boundaries.json"
    )

    result = run_deferred_runtime_boundaries(scenario)

    assert result == {
        "terminal_phase": "capability_preflight",
        "registered": False,
        "model_calls": 0,
        "tool_dispatches": 0,
    }


def test_council_request_stops_before_subagent_dispatch() -> None:
    scenario = load_m44_scenario(
        FIXTURE_ROOT / "dar-authoring" / "m4-4" / "council-request.json"
    )

    result = run_council_request(scenario)

    assert result == {
        "terminal_phase": "capability_preflight",
        "registered": False,
        "model_calls": 0,
        "tool_dispatches": 0,
    }


def test_document_embedding_stops_before_embedding_dispatch() -> None:
    scenario = load_m44_scenario(
        FIXTURE_ROOT / "dar-authoring" / "m4-4" / "document-embedding.json"
    )

    result = run_document_embedding(scenario)

    assert result == {
        "terminal_phase": "capability_preflight",
        "registered": False,
        "model_calls": 0,
        "tool_dispatches": 0,
    }


def test_input_guardrail_missing_registry_stops_before_model_dispatch() -> None:
    scenario = load_m44_scenario(
        FIXTURE_ROOT / "m4-4-successor" / "guardrail-input-missing.json"
    )

    result = run_guardrail_missing_registry(scenario)

    assert result == {
        "terminal_phase": "capability_preflight",
        "model_calls": 0,
        "tool_dispatches": 0,
        "retry_model_calls": 1,
    }


def test_tool_input_guardrail_missing_registry_stops_before_model_dispatch() -> None:
    scenario = load_m44_scenario(
        FIXTURE_ROOT / "m4-4-successor" / "guardrail-tool-input-missing.json"
    )

    result = run_tool_input_guardrail_missing_registry(scenario)

    assert result == {
        "terminal_phase": "capability_preflight",
        "model_calls": 0,
        "tool_dispatches": 0,
        "retry_model_calls": 2,
        "retry_tool_dispatches": 1,
    }


def test_invocation_schema_attack_refuses_before_model_or_tool_dispatch() -> None:
    scenario = load_m44_scenario(
        FIXTURE_ROOT
        / "dar-authoring"
        / "m4-4"
        / "invocation-schema-boundary-attack.json"
    )

    result = run_invocation_schema_boundary_attack(scenario)

    assert result == {
        "terminal_phase": "invocation",
        "model_calls": 0,
        "tool_dispatches": 0,
    }


def test_unpublished_package_cannot_be_selected_by_a_recipient_host() -> None:
    scenario = load_m44_scenario(
        FIXTURE_ROOT / "dar-authoring" / "m4-4" / "portable-package-handoff.json"
    )

    result = run_portable_package_handoff(scenario)

    assert result == {
        "terminal_phase": "source_selection",
        "recipient_registered": False,
        "model_calls": 0,
        "tool_dispatches": 0,
    }


def test_document_summary_runs_the_complete_no_tool_host_lifecycle() -> None:
    scenario = load_m44_scenario(
        FIXTURE_ROOT / "dar-authoring" / "m4-4" / "document-summary.json"
    )

    result = run_document_summary(scenario)

    assert result == {
        "lifecycle": ("authored", "finalized", "registered", "prepared", "invoked"),
        "model_calls": 1,
        "tool_dispatches": 0,
    }


def test_mailbox_triage_runs_a_reviewed_read_only_mcp_lifecycle() -> None:
    scenario = load_m44_scenario(
        FIXTURE_ROOT / "dar-authoring" / "m4-4" / "mailbox-triage.json"
    )

    result = run_mailbox_triage(scenario)

    assert result == {
        "lifecycle": ("authored", "finalized", "registered", "prepared", "invoked"),
        "model_calls": 2,
        "tool_dispatches": 1,
    }


def test_generic_email_send_runs_an_approved_mcp_write_lifecycle() -> None:
    scenario = load_m44_scenario(
        FIXTURE_ROOT / "dar-authoring" / "m4-4" / "generic-email-send.json"
    )

    result = run_generic_email_send(scenario)

    assert result == {
        "lifecycle": ("authored", "finalized", "registered", "prepared", "invoked"),
        "model_calls": 2,
        "tool_dispatches": 1,
        "approval_requests": 1,
    }


def test_email_file_body_runs_trusted_ingress_and_artifact_provenance() -> None:
    scenario = load_m44_scenario(
        FIXTURE_ROOT / "dar-authoring" / "m4-4" / "email-file-body.json"
    )

    result = run_email_file_body(scenario)

    assert result == {
        "lifecycle": ("authored", "finalized", "registered", "prepared", "invoked"),
        "model_calls": 2,
        "tool_dispatches": 1,
        "approval_requests": 1,
    }


def test_side_effect_recovery_rejects_replay_after_one_dispatch() -> None:
    scenario = load_m44_scenario(
        FIXTURE_ROOT / "dar-authoring" / "m4-4" / "side-effect-recovery.json"
    )

    result = run_side_effect_recovery(scenario)

    assert result == {
        "lifecycle": ("authored", "finalized", "registered", "prepared", "invoked"),
        "model_calls": 2,
        "tool_dispatches": 1,
        "approval_requests": 1,
    }


def test_hybrid_brief_ingresses_each_declared_artifact_role() -> None:
    scenario = load_m44_scenario(
        FIXTURE_ROOT / "dar-authoring" / "m4-4" / "hybrid-brief.json"
    )

    result = run_hybrid_brief(scenario)

    assert result == {
        "lifecycle": ("authored", "finalized", "registered", "prepared", "invoked"),
        "model_calls": 1,
        "tool_dispatches": 0,
        "artifact_count": 2,
    }


def test_no_tool_graph_and_skill_bundles_evaluation_artifacts_and_runs() -> None:
    scenario = load_m44_scenario(
        FIXTURE_ROOT / "m4-4-successor" / "no-tool-graph-and-skill.json"
    )

    result = run_no_tool_graph_and_skill(scenario)

    assert result == {
        "lifecycle": ("authored", "finalized", "registered", "prepared", "invoked"),
        "model_calls": 2,
        "tool_dispatches": 0,
        "skill_count": 1,
        "evaluation_artifact_count": 3,
    }


def test_structured_single_model_review_returns_the_registered_terminal_shape() -> None:
    scenario = load_m44_scenario(
        FIXTURE_ROOT / "dar-authoring" / "m4-4" / "structured-single-model-review.json"
    )

    result = run_structured_single_model_review(scenario)

    assert result == {
        "lifecycle": ("authored", "finalized", "registered", "prepared", "invoked"),
        "model_calls": 1,
        "tool_dispatches": 0,
        "terminal_output": {"message": "review complete"},
    }


def test_input_guardrail_runs_in_the_saved_package_host_lifecycle() -> None:
    scenario = load_m44_scenario(
        FIXTURE_ROOT / "m4-4-successor" / "guardrail-input.json"
    )

    result = run_guardrail_input(scenario)

    assert result == {
        "lifecycle": ("authored", "finalized", "registered", "prepared", "invoked"),
        "model_calls": 1,
        "tool_dispatches": 0,
        "guardrail_calls": 1,
    }


def test_tool_input_guardrail_runs_before_the_reviewed_mcp_read_dispatch() -> None:
    scenario = load_m44_scenario(
        FIXTURE_ROOT / "m4-4-successor" / "guardrail-tool-input.json"
    )

    result = run_guardrail_tool_input(scenario)

    assert result == {
        "lifecycle": ("authored", "finalized", "registered", "prepared", "invoked"),
        "model_calls": 2,
        "tool_dispatches": 1,
        "guardrail_calls": 1,
    }


def test_oauth_reconnect_re_reviews_generation_before_saved_invocation() -> None:
    scenario = load_m44_scenario(
        FIXTURE_ROOT / "dar-authoring" / "m4-4" / "oauth-reconnect.json"
    )

    result = run_oauth_reconnect(scenario)

    assert result == {
        "lifecycle": ("authored", "finalized", "registered", "prepared", "invoked"),
        "model_calls": 2,
        "tool_dispatches": 1,
        "oauth_refreshes": 1,
        "review_generations": (1, 2),
    }
