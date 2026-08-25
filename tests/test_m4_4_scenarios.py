"""Tests for the checked-in M4.4 author-then-run scenario contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dynamic_agent_runner.workflow_host.m4_4_scenarios import (  # noqa: E402
    M44Scenario,
    M44ScenarioError,
    load_m44_scenario,
    validate_m44_evidence,
)
from dynamic_agent_runner.workflow_host.authoring_evidence import (  # noqa: E402
    AuthorThenRunEvidence,
)


def _scenario(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "format_version": "m4.4-v1",
        "scenario_id": "document-summary-v1",
        "expected_status": "pass",
        "required_gates": ["G3"],
        "required_host_fixtures": ["local-model-profile"],
        "invocation_mode": "mcp_prompt_only",
        "required_artifact_roles": [],
        "expected_terminal_phase": "invocation",
        "zero_dispatch_assertions": ["no-undeclared-tool-dispatch"],
    }
    value.update(overrides)
    return value


def test_scenario_loads_the_minimum_prompt_only_contract(tmp_path: Path) -> None:
    destination = tmp_path / "document-summary.json"
    destination.write_text(json.dumps(_scenario()), encoding="utf-8")

    scenario = load_m44_scenario(destination)

    assert scenario == M44Scenario(
        scenario_id="document-summary-v1",
        expected_status="pass",
        required_gates=("G3",),
        required_host_fixtures=("local-model-profile",),
        invocation_mode="mcp_prompt_only",
        required_artifact_roles=(),
        expected_terminal_phase="invocation",
        zero_dispatch_assertions=("no-undeclared-tool-dispatch",),
    )


def test_checked_in_document_summary_scenario_is_a_prompt_only_positive_case() -> None:
    source = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "dar-authoring"
        / "m4-4"
        / "document-summary.json"
    )

    scenario = load_m44_scenario(source)

    assert scenario.scenario_id == "document-summary-v1"
    assert scenario.invocation_mode == "mcp_prompt_only"
    assert scenario.expected_status == "pass"


def test_checked_in_scenario_corpus_covers_the_m4_4_stratified_cases() -> None:
    root = Path(__file__).resolve().parent / "fixtures" / "dar-authoring" / "m4-4"

    scenarios = {load_m44_scenario(path).scenario_id for path in root.glob("*.json")}

    assert scenarios == {
        "authoring-boundary-attack-v1",
        "council-request-v1",
        "document-embedding-v1",
        "document-summary-v1",
        "email-file-body-v1",
        "generic-email-send-v1",
        "hybrid-brief-v1",
        "invocation-schema-boundary-attack-v1",
        "mailbox-triage-v1",
        "oauth-reconnect-v1",
        "portable-package-handoff-v1",
        "side-effect-recovery-v1",
        "structured-single-model-review-v1",
    }


def test_scenario_checker_requires_its_declared_gate_and_fixture() -> None:
    scenario = M44Scenario.from_mapping(_scenario())
    evidence = AuthorThenRunEvidence(
        scenario_id="document-summary-v1",
        scenario_contract_version="m4.4-v1",
        checker_version="m4.4-checker-v1",
        expected_status="pass",
        observed_status="pending_human_review",
        terminal_phase="invocation",
        invocation_mode="mcp_prompt_only",
        plugin_identity="dar-authoring@local-test",
        skill_identity="agent-development@local-test",
        wheel_digest="a" * 64,
        harness_policy_digest="f" * 64,
        executable_identity="codex@0.149.1",
        module_identity="dynamic-agent-runner@0.1.16",
        authoring_material_set_id="v1.material-set.signature",
        authoring_output_id="v1.output.signature",
        authoring_receipt_digest="0" * 64,
        final_package_digest="b" * 64,
        catalog_revision_digest="c" * 64,
        registration_digest="d" * 64,
        prepared_input_registration_digest="d" * 64,
        action_trace_digest="e" * 64,
        dispatch_count=0,
        reviewer_id=None,
        reviewer_decision="pending",
        controller_fixture_digest="1" * 64,
    )

    validate_m44_evidence(
        scenario,
        evidence,
        available_gates=("G3",),
        available_host_fixtures=("local-model-profile",),
    )

    with pytest.raises(M44ScenarioError, match="required gates"):
        validate_m44_evidence(
            scenario,
            evidence,
            available_gates=(),
            available_host_fixtures=("local-model-profile",),
        )


@pytest.mark.parametrize(
    "overrides",
    (
        {"format_version": "m4.4-v2"},
        {"expected_status": "unknown"},
        {"required_gates": []},
        {"required_host_fixtures": []},
        {"zero_dispatch_assertions": []},
        {"invocation_mode": "mcp_prompt_only", "required_artifact_roles": ["brief"]},
        {
            "expected_status": "pass",
            "expected_terminal_phase": "capability_preflight",
        },
    ),
)
def test_scenario_rejects_an_overclaimed_or_incomplete_contract(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(M44ScenarioError):
        M44Scenario.from_mapping(_scenario(**overrides))


def test_scenario_rejects_unknown_fields_and_non_json_files(tmp_path: Path) -> None:
    unknown_field = _scenario(unexpected=True)
    with pytest.raises(M44ScenarioError):
        M44Scenario.from_mapping(unknown_field)

    non_json = tmp_path / "document-summary.yaml"
    non_json.write_text("not json", encoding="utf-8")
    with pytest.raises(M44ScenarioError):
        load_m44_scenario(non_json)
