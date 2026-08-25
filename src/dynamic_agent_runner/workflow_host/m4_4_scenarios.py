"""Validated, content-free M4.4 author-then-run scenario manifests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dynamic_agent_runner.workflow_host.authoring_evidence import (
    AuthorThenRunEvidence,
)


class M44ScenarioError(ValueError):
    """Raised when an M4.4 scenario cannot make a safe harness claim."""


@dataclass(frozen=True)
class M44Scenario:
    """The checker-relevant contract for one author-then-run case."""

    scenario_id: str
    expected_status: str
    required_gates: tuple[str, ...]
    required_host_fixtures: tuple[str, ...]
    invocation_mode: str
    required_artifact_roles: tuple[str, ...]
    expected_terminal_phase: str
    zero_dispatch_assertions: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: object) -> M44Scenario:
        """Build one scenario after rejecting ambiguous or overclaimed input."""

        if not isinstance(value, dict) or set(value) != {
            "format_version",
            "scenario_id",
            "expected_status",
            "required_gates",
            "required_host_fixtures",
            "invocation_mode",
            "required_artifact_roles",
            "expected_terminal_phase",
            "zero_dispatch_assertions",
        }:
            raise M44ScenarioError("scenario fields are invalid")
        if value["format_version"] != "m4.4-v1":
            raise M44ScenarioError("scenario format version is invalid")
        scenario = cls(
            scenario_id=_text(value["scenario_id"], "scenario_id"),
            expected_status=_choice(
                value["expected_status"],
                "expected_status",
                {"pass", "expected_capability_unavailable", "expected_refusal"},
            ),
            required_gates=_text_list(value["required_gates"], "required_gates"),
            required_host_fixtures=_text_list(
                value["required_host_fixtures"], "required_host_fixtures"
            ),
            invocation_mode=_choice(
                value["invocation_mode"],
                "invocation_mode",
                {"mcp_prompt_only", "host_prepared_cli"},
            ),
            required_artifact_roles=_text_list(
                value["required_artifact_roles"], "required_artifact_roles", empty=True
            ),
            expected_terminal_phase=_choice(
                value["expected_terminal_phase"],
                "expected_terminal_phase",
                {
                    "authoring_validation",
                    "source_selection",
                    "capability_preflight",
                    "registration",
                    "invocation",
                },
            ),
            zero_dispatch_assertions=_text_list(
                value["zero_dispatch_assertions"], "zero_dispatch_assertions"
            ),
        )
        scenario._validate_claims()
        return scenario

    def _validate_claims(self) -> None:
        if self.invocation_mode == "mcp_prompt_only" and self.required_artifact_roles:
            raise M44ScenarioError("prompt-only scenarios cannot require artifacts")
        if (
            self.expected_status == "pass"
            and self.expected_terminal_phase != "invocation"
        ):
            raise M44ScenarioError("positive scenarios must reach invocation")
        if (
            self.expected_status != "pass"
            and self.expected_terminal_phase == "invocation"
        ):
            raise M44ScenarioError("non-pass scenarios cannot claim invocation")


def load_m44_scenario(source: Path) -> M44Scenario:
    """Load one checked-in JSON scenario without accepting arbitrary formats."""

    if not isinstance(source, Path) or source.suffix != ".json":
        raise M44ScenarioError("scenario source is invalid")
    try:
        value: Any = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M44ScenarioError("scenario source is invalid") from error
    return M44Scenario.from_mapping(value)


def validate_m44_evidence(
    scenario: M44Scenario,
    evidence: AuthorThenRunEvidence,
    *,
    available_gates: tuple[str, ...],
    available_host_fixtures: tuple[str, ...],
) -> None:
    """Reject evidence that does not satisfy its checked-in scenario contract."""

    if not isinstance(scenario, M44Scenario) or not isinstance(
        evidence, AuthorThenRunEvidence
    ):
        raise M44ScenarioError("scenario evidence is invalid")
    if (
        evidence.scenario_id != scenario.scenario_id
        or evidence.scenario_contract_version != "m4.4-v1"
        or evidence.expected_status != scenario.expected_status
        or evidence.terminal_phase != scenario.expected_terminal_phase
        or evidence.invocation_mode != scenario.invocation_mode
    ):
        raise M44ScenarioError("scenario evidence does not match the manifest")
    gates = _text_tuple(available_gates, "available_gates")
    fixtures = _text_tuple(available_host_fixtures, "available_host_fixtures")
    if scenario.expected_status == "pass" and not set(scenario.required_gates).issubset(
        gates
    ):
        raise M44ScenarioError("required gates are unavailable")
    if scenario.expected_status == "pass" and not set(
        scenario.required_host_fixtures
    ).issubset(fixtures):
        raise M44ScenarioError("required host fixtures are unavailable")


def _choice(value: object, label: str, allowed: set[str]) -> str:
    text = _text(value, label)
    if text not in allowed:
        raise M44ScenarioError(f"{label} is invalid")
    return text


def _text_list(value: object, label: str, *, empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (not empty and not value):
        raise M44ScenarioError(f"{label} is invalid")
    values = tuple(_text(item, label) for item in value)
    if len(set(values)) != len(values):
        raise M44ScenarioError(f"{label} is invalid")
    return values


def _text_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise M44ScenarioError(f"{label} is invalid")
    values = tuple(_text(item, label) for item in value)
    if len(set(values)) != len(values):
        raise M44ScenarioError(f"{label} is invalid")
    return values


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise M44ScenarioError(f"{label} is invalid")
    return value
