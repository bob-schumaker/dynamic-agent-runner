"""Validated, content-free M4.4 author-then-run scenario manifests."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dynamic_agent_runner.workflow_host.authoring_evidence import (
    AuthorThenRunEvidence,
)


class M44ScenarioError(ValueError):
    """Raised when an M4.4 scenario cannot make a safe harness claim."""


@dataclass(frozen=True)
class M44CoverageEntry:
    """One capability-to-scenario acceptance binding."""

    capability_id: str
    scenario_id: str
    expected_status: str
    configured_fixture_ids: tuple[str, ...]
    missing_fixture_ids: tuple[str, ...]
    expected_terminal_phase: str
    capability_assertions: tuple[str, ...]


@dataclass(frozen=True)
class M44Coverage:
    """Versioned successor acceptance coverage manifest."""

    entries: tuple[M44CoverageEntry, ...]


@dataclass(frozen=True)
class M44ExternalScenarioPlanEntry:
    """One model-visible request pair bound to an immutable scenario."""

    scenario_id: str
    package_name: str
    workflow_id: str
    author_request: str
    run_request: str
    fixture_ids: tuple[str, ...]


@dataclass(frozen=True)
class M44ExternalScenarioPlan:
    """Versioned actor inputs for a complete external acceptance replay."""

    entries: tuple[M44ExternalScenarioPlanEntry, ...]


def load_m44_original_scenario_ids(source: Path) -> tuple[str, ...]:
    """Load the immutable original M4.4 scenario admission set."""

    if not isinstance(source, Path) or source.suffix != ".json":
        raise M44ScenarioError("original scenario IDs are invalid")
    try:
        value: Any = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M44ScenarioError("original scenario IDs are invalid") from error
    if (
        not isinstance(value, dict)
        or set(value) != {"format_version", "scenario_ids"}
        or value["format_version"] != "m4.4-original-scenario-ids-v1"
    ):
        raise M44ScenarioError("original scenario IDs are invalid")
    scenario_ids = _text_list(value["scenario_ids"], "original scenario IDs")
    if len(scenario_ids) != 13 or len(set(scenario_ids)) != len(scenario_ids):
        raise M44ScenarioError("original scenario IDs are invalid")
    return scenario_ids


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


def load_m44_scenario(source: Path) -> M44Scenario:
    """Load one checked-in JSON scenario without accepting arbitrary formats."""

    if not isinstance(source, Path) or source.suffix != ".json":
        raise M44ScenarioError("scenario source is invalid")
    try:
        value: Any = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M44ScenarioError("scenario source is invalid") from error
    return M44Scenario.from_mapping(value)


def load_m44_coverage(source: Path) -> M44Coverage:
    """Load the closed successor coverage manifest."""

    if not isinstance(source, Path) or source.suffix != ".json":
        raise M44ScenarioError("coverage source is invalid")
    try:
        value: Any = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M44ScenarioError("coverage source is invalid") from error
    if not isinstance(value, dict) or set(value) != {"format_version", "entries"}:
        raise M44ScenarioError("coverage fields are invalid")
    if value["format_version"] != "m4.4-successor-coverage-v1":
        raise M44ScenarioError("coverage format version is invalid")
    if not isinstance(value["entries"], list) or not value["entries"]:
        raise M44ScenarioError("coverage entries are invalid")
    entries = tuple(_coverage_entry(entry) for entry in value["entries"])
    if len({(entry.capability_id, entry.scenario_id) for entry in entries}) != len(
        entries
    ):
        raise M44ScenarioError("coverage entries are invalid")
    return M44Coverage(entries=entries)


def load_m44_external_scenario_plan(source: Path) -> M44ExternalScenarioPlan:
    """Load closed model-visible inputs for the external acceptance command."""

    if not isinstance(source, Path) or source.suffix != ".json":
        raise M44ScenarioError("external scenario plan source is invalid")
    try:
        value: Any = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M44ScenarioError("external scenario plan source is invalid") from error
    if not isinstance(value, dict) or set(value) != {"format_version", "scenarios"}:
        raise M44ScenarioError("external scenario plan fields are invalid")
    if value["format_version"] != "m4.4-external-scenario-plan-v1":
        raise M44ScenarioError("external scenario plan format version is invalid")
    if not isinstance(value["scenarios"], list) or not value["scenarios"]:
        raise M44ScenarioError("external scenario plan entries are invalid")
    entries = tuple(
        _external_scenario_plan_entry(entry) for entry in value["scenarios"]
    )
    if len({entry.scenario_id for entry in entries}) != len(entries):
        raise M44ScenarioError("external scenario plan entries are invalid")
    if len({entry.package_name for entry in entries}) != len(entries):
        raise M44ScenarioError("external scenario plan package names are invalid")
    if len({entry.workflow_id for entry in entries}) != len(entries):
        raise M44ScenarioError("external scenario plan workflow IDs are invalid")
    return M44ExternalScenarioPlan(entries=entries)


def validate_m44_external_scenario_plan(
    plan: M44ExternalScenarioPlan,
    *,
    coverage: M44Coverage,
    scenario_roots: tuple[Path, ...],
) -> None:
    """Require plan inputs to exactly match the complete immutable corpus."""

    if not isinstance(plan, M44ExternalScenarioPlan) or not isinstance(
        coverage, M44Coverage
    ):
        raise M44ScenarioError("external scenario plan is invalid")
    scenarios = _load_scenario_corpus(scenario_roots)
    covered_ids = {entry.scenario_id for entry in coverage.entries}
    planned_ids = {entry.scenario_id for entry in plan.entries}
    if planned_ids != covered_ids or planned_ids != set(scenarios):
        raise M44ScenarioError("external scenario plan scenarios are invalid")
    for entry in plan.entries:
        scenario = scenarios[entry.scenario_id]
        if set(entry.fixture_ids) != set(scenario.required_host_fixtures):
            raise M44ScenarioError("external scenario plan fixtures are invalid")


def validate_m44_original_scenario_admission(
    original_scenario_ids: tuple[str, ...],
    *,
    plan: M44ExternalScenarioPlan,
    coverage: M44Coverage,
    scenario_roots: tuple[Path, ...],
) -> None:
    """Require every original M4.4 scenario to remain in the complete replay."""

    if (
        not isinstance(original_scenario_ids, tuple)
        or len(original_scenario_ids) != 13
        or any(not isinstance(item, str) or not item for item in original_scenario_ids)
        or len(set(original_scenario_ids)) != len(original_scenario_ids)
        or not isinstance(plan, M44ExternalScenarioPlan)
        or not isinstance(coverage, M44Coverage)
    ):
        raise M44ScenarioError("original scenario admission is invalid")
    original_ids = set(original_scenario_ids)
    scenario_ids = set(_load_scenario_corpus(scenario_roots))
    covered_ids = {entry.scenario_id for entry in coverage.entries}
    planned_ids = {entry.scenario_id for entry in plan.entries}
    if not (
        original_ids.issubset(scenario_ids)
        and original_ids.issubset(covered_ids)
        and original_ids.issubset(planned_ids)
    ):
        raise M44ScenarioError("original scenario admission is invalid")


def validate_m44_coverage(
    coverage: M44Coverage, *, matrix_source: Path, scenario_roots: tuple[Path, ...]
) -> None:
    """Validate complete matrix coverage against immutable scenario contracts."""

    if not isinstance(coverage, M44Coverage):
        raise M44ScenarioError("coverage is invalid")
    matrix = _load_capability_matrix(matrix_source)
    scenarios = _load_scenario_corpus(scenario_roots)
    capability_ids = {entry.capability_id for entry in coverage.entries}
    if capability_ids != set(matrix):
        raise M44ScenarioError("coverage capability IDs are invalid")
    scenario_ids = {entry.scenario_id for entry in coverage.entries}
    if scenario_ids != set(scenarios):
        raise M44ScenarioError("coverage scenarios are invalid")
    for entry in coverage.entries:
        _validate_coverage_entry(entry, scenarios)
    for capability_id, support_status in matrix.items():
        _validate_capability_coverage(capability_id, support_status, coverage.entries)


def _validate_coverage_entry(
    entry: M44CoverageEntry, scenarios: dict[str, M44Scenario]
) -> None:
    scenario = scenarios.get(entry.scenario_id)
    if scenario is None:
        raise M44ScenarioError("coverage entry is invalid")
    if (
        entry.expected_status != scenario.expected_status
        or entry.expected_terminal_phase != scenario.expected_terminal_phase
    ):
        raise M44ScenarioError("coverage entry does not match scenario")
    if not _required_gates(entry.capability_id).issubset(scenario.required_gates):
        raise M44ScenarioError("coverage entry is under-gated")
    if not entry.capability_assertions:
        raise M44ScenarioError("coverage assertions are invalid")
    configured, missing = (
        set(entry.configured_fixture_ids),
        set(entry.missing_fixture_ids),
    )
    if configured & missing or configured | missing != set(
        scenario.required_host_fixtures
    ):
        raise M44ScenarioError("coverage fixtures are invalid")
    if entry.expected_status == "pass" and missing:
        raise M44ScenarioError("positive coverage fixtures are invalid")


def _validate_capability_coverage(
    capability_id: str, support_status: str, entries: tuple[M44CoverageEntry, ...]
) -> None:
    capability_entries = tuple(
        entry for entry in entries if entry.capability_id == capability_id
    )
    if support_status == "supported" and not any(
        entry.expected_status == "pass" for entry in capability_entries
    ):
        raise M44ScenarioError("supported coverage is incomplete")
    if support_status == "conditional":
        has_positive = any(
            entry.expected_status == "pass" and not entry.missing_fixture_ids
            for entry in capability_entries
        )
        has_missing_fixture = any(
            entry.expected_status == "expected_capability_unavailable"
            and len(entry.missing_fixture_ids) == 1
            for entry in capability_entries
        )
        if not has_positive or not has_missing_fixture:
            raise M44ScenarioError("conditional coverage is incomplete")
    if support_status == "deferred" and any(
        entry.expected_status == "pass" for entry in capability_entries
    ):
        raise M44ScenarioError("deferred coverage is invalid")


def _coverage_entry(value: object) -> M44CoverageEntry:
    if not isinstance(value, dict) or set(value) != {
        "capability_id",
        "scenario_id",
        "expected_status",
        "configured_fixture_ids",
        "missing_fixture_ids",
        "expected_terminal_phase",
        "capability_assertions",
    }:
        raise M44ScenarioError("coverage entry fields are invalid")
    return M44CoverageEntry(
        capability_id=_text(value["capability_id"], "capability_id"),
        scenario_id=_text(value["scenario_id"], "scenario_id"),
        expected_status=_choice(
            value["expected_status"],
            "expected_status",
            {"pass", "expected_capability_unavailable", "expected_refusal"},
        ),
        configured_fixture_ids=_text_list(
            value["configured_fixture_ids"], "configured_fixture_ids", empty=True
        ),
        missing_fixture_ids=_text_list(
            value["missing_fixture_ids"], "missing_fixture_ids", empty=True
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
        capability_assertions=_text_list(
            value["capability_assertions"], "capability_assertions"
        ),
    )


def _external_scenario_plan_entry(value: object) -> M44ExternalScenarioPlanEntry:
    if not isinstance(value, dict) or set(value) != {
        "scenario_id",
        "package_name",
        "workflow_id",
        "author_request",
        "run_request",
        "fixture_ids",
    }:
        raise M44ScenarioError("external scenario plan entry fields are invalid")
    return M44ExternalScenarioPlanEntry(
        scenario_id=_text(value["scenario_id"], "scenario_id"),
        package_name=_text(value["package_name"], "package_name"),
        workflow_id=_text(value["workflow_id"], "workflow_id"),
        author_request=_text(value["author_request"], "author_request"),
        run_request=_text(value["run_request"], "run_request"),
        fixture_ids=_text_list(value["fixture_ids"], "fixture_ids", empty=True),
    )


def _load_capability_matrix(source: Path) -> dict[str, str]:
    if not isinstance(source, Path):
        raise M44ScenarioError("capability matrix is invalid")
    try:
        rows = re.findall(
            r"^\| `([a-z0-9-]+)` \| .*? \| (supported|conditional|deferred) \|",
            source.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
    except (OSError, UnicodeDecodeError) as error:
        raise M44ScenarioError("capability matrix is invalid") from error
    matrix = dict(rows)
    if len(matrix) != len(rows) or not matrix:
        raise M44ScenarioError("capability matrix is invalid")
    return matrix


def _load_scenario_corpus(roots: tuple[Path, ...]) -> dict[str, M44Scenario]:
    if (
        not isinstance(roots, tuple)
        or not roots
        or any(not isinstance(root, Path) or not root.is_dir() for root in roots)
    ):
        raise M44ScenarioError("scenario corpus is invalid")
    scenarios = {}
    sources = tuple(path for root in roots for path in root.glob("*.json"))
    for path in sources:
        scenario = load_m44_scenario(path)
        scenarios[scenario.scenario_id] = scenario
    if not scenarios or len(scenarios) != len(sources):
        raise M44ScenarioError("scenario corpus is invalid")
    return scenarios


def _required_gates(capability_id: str) -> set[str]:
    return {
        "basic-reasoning": {"G3"},
        "no-tool-multi-step": {"G3"},
        "tool-using-graph": {"G2", "G5"},
        "structured-terminal-output": {"G3"},
        "package-local-skill": {"G3"},
        "read-only-mcp-tool": {"G2"},
        "mcp-mutation": {"G2", "G5"},
        "file-backed-task": {"G4"},
        "hybrid-input": {"G3"},
        "tool-argument-provenance": {"G5"},
        "react-tool-loop": {"G2", "G5"},
        "oauth-mcp-connection": {"G2"},
        "package-portability": {"M8"},
        "evaluation": {"G3"},
        "guardrails": {"G3"},
        "context-pruning-pipeline": {"G3"},
        "scratch-workspace": {"G3"},
        "durable-session-continuation": {"G3"},
        "collaboration-subagents": {"G3"},
        "retrieval-embedding-rag": {"G3"},
        "custom-host-tools": {"G3"},
        "native-approval-resume": {"G5"},
    }[capability_id]


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
        or (
            evidence.observed_status != "harness_failure"
            and evidence.terminal_phase != scenario.expected_terminal_phase
        )
        or evidence.invocation_mode != scenario.invocation_mode
    ):
        raise M44ScenarioError("scenario evidence does not match the manifest")
    gates = _text_tuple(available_gates, "available_gates")
    fixtures = _text_tuple(available_host_fixtures, "available_host_fixtures")
    if (
        evidence.observed_status != "harness_failure"
        and scenario.expected_status == "pass"
        and not set(scenario.required_gates).issubset(gates)
    ):
        raise M44ScenarioError("required gates are unavailable")
    if (
        evidence.observed_status != "harness_failure"
        and scenario.expected_status == "pass"
        and not set(scenario.required_host_fixtures).issubset(fixtures)
    ):
        raise M44ScenarioError("required host fixtures are unavailable")
    if (
        evidence.observed_status != "harness_failure"
        and scenario.expected_status == "pass"
        and evidence.controller_fixture_digest is None
    ):
        raise M44ScenarioError("controller fixture evidence is unavailable")
    if (
        evidence.observed_status != "harness_failure"
        and scenario.expected_status == "pass"
        and "reviewed-mcp-connection" in scenario.required_host_fixtures
    ):
        if evidence.mcp_snapshot_id is None or evidence.mcp_binding_id is None:
            raise M44ScenarioError("reviewed MCP evidence is unavailable")
    if "no-send-handler-dispatch" in scenario.zero_dispatch_assertions:
        if (
            not evidence.mcp_read_tool_names
            or evidence.mcp_read_call_count <= 0
            or evidence.forbidden_send_dispatch_count != 0
        ):
            raise M44ScenarioError("read-only MCP dispatch evidence is unavailable")


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
