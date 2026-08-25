"""Tests for the checked-in M4.4 author-then-run scenario contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dynamic_agent_runner.workflow_host.m4_4_scenarios import (  # noqa: E402
    M44Scenario,
    M44ScenarioError,
    load_m44_scenario,
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
            "expected_status": "expected_refusal",
            "expected_terminal_phase": "invocation",
        },
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
