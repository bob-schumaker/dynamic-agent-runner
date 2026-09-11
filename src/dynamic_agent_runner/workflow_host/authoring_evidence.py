"""Redacted evidence contract for external DAR authoring evaluation."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from dynamic_agent_runner.workflow_host.authoring_materials import (
    AuthoringMaterialSetProjection,
)
from dynamic_agent_runner.workflow_host.authoring_output import (
    validate_authored_package,
)


class AuthoringEvidenceError(ValueError):
    """Raised when an external authoring-evidence record is invalid."""


@dataclass(frozen=True)
class ExternalAuthoringHarnessRequest:
    """Private input supplied to an external authoring harness, never recorded."""

    skill_name: str
    request: str
    materials: AuthoringMaterialSetProjection


@dataclass(frozen=True)
class ExternalAuthoringHarnessOutcome:
    """Redaction-safe external harness result before human release review."""

    generated_package_digests: tuple[str, ...]
    validator_result: str


class ExternalAuthoringHarness(Protocol):
    """Collaborator for an out-of-process authoring-model evaluation run."""

    def run(
        self, request: ExternalAuthoringHarnessRequest
    ) -> ExternalAuthoringHarnessOutcome:
        """Generate and validate one package without persisting private input."""


class PackageGeneratingAuthoringHarness(Protocol):
    """Private collaborator that returns one controlled generated directory."""

    def generate(self, request: ExternalAuthoringHarnessRequest) -> Path:
        """Generate one package directory from the selected authoring request."""


class ValidatingExternalAuthoringHarness:
    """Validate external package output before returning a redacted outcome."""

    def __init__(self, generator: PackageGeneratingAuthoringHarness) -> None:
        self._generator = generator

    def run(
        self, request: ExternalAuthoringHarnessRequest
    ) -> ExternalAuthoringHarnessOutcome:
        """Generate and validate without returning paths or material content."""

        try:
            package_root = self._generator.generate(request)
            validation = validate_authored_package(
                package_root=package_root,
                materials=request.materials,
            )
        except Exception:  # noqa: BLE001 - external authoring harnesses vary.
            return ExternalAuthoringHarnessOutcome((), "failed")
        return ExternalAuthoringHarnessOutcome((validation.package_digest,), "passed")


@dataclass(frozen=True)
class AuthoringBehaviorEvidence:
    """Redacted execution facts for one manually reviewed package run."""

    case_digest: str
    transcript_digest: str
    execution_model_id: str
    terminal_outcome: str
    tool_dispatch_count: int

    def __post_init__(self) -> None:
        _digest(self.case_digest, "case_digest")
        _digest(self.transcript_digest, "transcript_digest")
        _text(self.execution_model_id, "execution_model_id")
        if self.terminal_outcome not in {"completed", "failed"}:
            raise AuthoringEvidenceError("behavioral terminal outcome is invalid")
        if (
            not isinstance(self.tool_dispatch_count, int)
            or isinstance(self.tool_dispatch_count, bool)
            or self.tool_dispatch_count < 0
        ):
            raise AuthoringEvidenceError("behavioral tool dispatch count is invalid")

    def to_mapping(self) -> dict[str, object]:
        """Return a transcript-free stable behavioral evidence projection."""

        return {
            "case_digest": self.case_digest,
            "transcript_digest": self.transcript_digest,
            "execution_model_id": self.execution_model_id,
            "terminal_outcome": self.terminal_outcome,
            "tool_dispatch_count": self.tool_dispatch_count,
        }


@dataclass(frozen=True)
class AuthoringEvidence:
    """One redacted outcome from an external authoring-harness invocation."""

    corpus_digest: str
    prompt_digest: str
    material_set_id: str
    authoring_provider: str
    authoring_model_id: str
    generated_package_digests: tuple[str, ...]
    validator_result: str
    reviewer_id: str
    reviewer_decision: str
    pass_criteria: tuple[str, ...]
    retention_policy: str
    behavioral_runs: tuple[AuthoringBehaviorEvidence, ...] = ()
    package_revision_provenance: str = "external_authoring"

    def __post_init__(self) -> None:
        _digest(self.corpus_digest, "corpus_digest")
        _digest(self.prompt_digest, "prompt_digest")
        _text(self.material_set_id, "material_set_id")
        _text(self.authoring_provider, "authoring_provider")
        _text(self.authoring_model_id, "authoring_model_id")
        if self.validator_result not in {"passed", "failed"}:
            raise AuthoringEvidenceError("validator result is invalid")
        if not self.generated_package_digests and self.validator_result != "failed":
            raise AuthoringEvidenceError("generated package digests are required")
        for digest in self.generated_package_digests:
            _digest(digest, "generated_package_digests")
        _text(self.reviewer_id, "reviewer_id")
        if self.reviewer_decision not in {"approved", "rejected"}:
            raise AuthoringEvidenceError("reviewer decision is invalid")
        if not self.pass_criteria or any(
            not isinstance(criterion, str) or not criterion
            for criterion in self.pass_criteria
        ):
            raise AuthoringEvidenceError("pass criteria are invalid")
        _text(self.retention_policy, "retention_policy")
        if self.package_revision_provenance not in {
            "external_authoring",
            "external_authoring_with_human_model_retarget",
        }:
            raise AuthoringEvidenceError("package revision provenance is invalid")
        if any(
            not isinstance(run, AuthoringBehaviorEvidence)
            for run in self.behavioral_runs
        ):
            raise AuthoringEvidenceError("behavioral runs are invalid")

    def to_mapping(self) -> dict[str, object]:
        """Return the stable evidence projection without raw authoring input."""

        return {
            "format_version": 2,
            "corpus_digest": self.corpus_digest,
            "prompt_digest": self.prompt_digest,
            "material_set_id": self.material_set_id,
            "authoring_provider": self.authoring_provider,
            "authoring_model_id": self.authoring_model_id,
            "generated_package_digests": list(self.generated_package_digests),
            "validator_result": self.validator_result,
            "reviewer_id": self.reviewer_id,
            "reviewer_decision": self.reviewer_decision,
            "pass_criteria": list(self.pass_criteria),
            "retention_policy": self.retention_policy,
            "behavioral_runs": [run.to_mapping() for run in self.behavioral_runs],
            "package_revision_provenance": self.package_revision_provenance,
        }


@dataclass(frozen=True)
class AuthorThenRunEvidence:
    """Redacted evidence for one M4.4 author-then-run scenario."""

    scenario_id: str
    scenario_contract_version: str
    checker_version: str
    expected_status: str
    observed_status: str
    terminal_phase: str
    invocation_mode: str
    plugin_identity: str
    skill_identity: str
    wheel_digest: str
    harness_policy_digest: str
    executable_identity: str
    module_identity: str
    authoring_material_set_id: str | None
    authoring_output_id: str | None
    authoring_receipt_digest: str | None
    final_package_digest: str | None
    catalog_revision_digest: str | None
    registration_digest: str | None
    prepared_input_registration_digest: str | None
    action_trace_digest: str | None
    dispatch_count: int
    reviewer_id: str | None
    reviewer_decision: str
    controller_fixture_digest: str | None = None
    mcp_snapshot_id: str | None = None
    mcp_binding_id: str | None = None
    mcp_read_tool_names: tuple[str, ...] = ()
    mcp_read_call_count: int = 0
    forbidden_send_dispatch_count: int = 0
    marketplace_manifest_digest: str | None = None
    generated_manifest_digest: str | None = None
    router_authority_digest: str | None = None
    payload_manifest_digest: str | None = None
    source_map_digest: str | None = None
    release_metadata_digest: str | None = None
    dar_runtime_version: str | None = None
    dar_runtime_wheel_filename: str | None = None
    dar_runtime_wheel_metadata_digest: str | None = None
    dar_runtime_release_descriptor_digest: str | None = None
    dar_runtime_payload_selector_list_digest: str | None = None
    actor_durations_ms: tuple[int, ...] = ()
    author_return_code: int | None = None
    invocation_return_code: int | None = None
    author_decisions: tuple[str, ...] = ()
    invocation_decisions: tuple[str, ...] = ()
    author_event_trace: tuple[str, ...] = ()
    invocation_event_trace: tuple[str, ...] = ()
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        _validate_author_then_run_text(self)
        _digest(self.wheel_digest, "wheel_digest")
        _digest(self.harness_policy_digest, "harness_policy_digest")
        _validate_author_then_run_status(self)
        _validate_optional_digests(self)
        _validate_author_then_run_terminal_phase(self)
        _validate_mcp_summary(self)
        _validate_actor_durations(self.actor_durations_ms)
        _validate_diagnostics(self)

    def to_mapping(self) -> dict[str, object]:
        """Return a redaction-safe stable evidence projection."""

        return {
            "format_version": 1,
            "scenario_id": self.scenario_id,
            "scenario_contract_version": self.scenario_contract_version,
            "checker_version": self.checker_version,
            "expected_status": self.expected_status,
            "observed_status": self.observed_status,
            "terminal_phase": self.terminal_phase,
            "invocation_mode": self.invocation_mode,
            "plugin_identity": self.plugin_identity,
            "skill_identity": self.skill_identity,
            "wheel_digest": self.wheel_digest,
            "harness_policy_digest": self.harness_policy_digest,
            "executable_identity": self.executable_identity,
            "module_identity": self.module_identity,
            "authoring_material_set_id": self.authoring_material_set_id,
            "authoring_output_id": self.authoring_output_id,
            "authoring_receipt_digest": self.authoring_receipt_digest,
            "final_package_digest": self.final_package_digest,
            "catalog_revision_digest": self.catalog_revision_digest,
            "registration_digest": self.registration_digest,
            "prepared_input_registration_digest": self.prepared_input_registration_digest,
            "action_trace_digest": self.action_trace_digest,
            "dispatch_count": self.dispatch_count,
            "reviewer_id": self.reviewer_id,
            "reviewer_decision": self.reviewer_decision,
            "controller_fixture_digest": self.controller_fixture_digest,
            "mcp_snapshot_id": self.mcp_snapshot_id,
            "mcp_binding_id": self.mcp_binding_id,
            "mcp_read_tool_names": list(self.mcp_read_tool_names),
            "mcp_read_call_count": self.mcp_read_call_count,
            "forbidden_send_dispatch_count": self.forbidden_send_dispatch_count,
            "marketplace_manifest_digest": self.marketplace_manifest_digest,
            "generated_manifest_digest": self.generated_manifest_digest,
            "router_authority_digest": self.router_authority_digest,
            "payload_manifest_digest": self.payload_manifest_digest,
            "source_map_digest": self.source_map_digest,
            "release_metadata_digest": self.release_metadata_digest,
            "dar_runtime_version": self.dar_runtime_version,
            "dar_runtime_wheel_filename": self.dar_runtime_wheel_filename,
            "dar_runtime_wheel_metadata_digest": self.dar_runtime_wheel_metadata_digest,
            "dar_runtime_release_descriptor_digest": (
                self.dar_runtime_release_descriptor_digest
            ),
            "dar_runtime_payload_selector_list_digest": (
                self.dar_runtime_payload_selector_list_digest
            ),
            "actor_durations_ms": list(self.actor_durations_ms),
            "author_return_code": self.author_return_code,
            "invocation_return_code": self.invocation_return_code,
            "author_decisions": list(self.author_decisions),
            "invocation_decisions": list(self.invocation_decisions),
            "author_event_trace": list(self.author_event_trace),
            "invocation_event_trace": list(self.invocation_event_trace),
            "failure_reason": self.failure_reason,
        }


def write_authoring_evidence(destination: Path, evidence: AuthoringEvidence) -> None:
    """Atomically write one redacted evidence record with private permissions."""

    if not isinstance(destination, Path) or destination.name != "evidence.json":
        raise AuthoringEvidenceError("evidence destination is invalid")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(evidence.to_mapping(), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)


def write_author_then_run_evidence(
    destination: Path, evidence: AuthorThenRunEvidence
) -> None:
    """Atomically write one private redacted M4.4 evidence record."""

    if not isinstance(destination, Path) or destination.name != "author-then-run.json":
        raise AuthoringEvidenceError("evidence destination is invalid")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(evidence.to_mapping(), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)


def _validate_author_then_run_text(evidence: AuthorThenRunEvidence) -> None:
    for value, label in (
        (evidence.scenario_id, "scenario_id"),
        (evidence.scenario_contract_version, "scenario_contract_version"),
        (evidence.checker_version, "checker_version"),
        (evidence.plugin_identity, "plugin_identity"),
        (evidence.skill_identity, "skill_identity"),
        (evidence.executable_identity, "executable_identity"),
        (evidence.module_identity, "module_identity"),
    ):
        _text(value, label)


def _validate_author_then_run_status(evidence: AuthorThenRunEvidence) -> None:
    if evidence.expected_status not in {
        "pass",
        "expected_capability_unavailable",
        "expected_refusal",
    }:
        raise AuthoringEvidenceError("expected_status is invalid")
    if evidence.observed_status not in {
        "pass",
        "expected_capability_unavailable",
        "expected_refusal",
        "pending_human_review",
        "harness_failure",
    }:
        raise AuthoringEvidenceError("observed_status is invalid")
    if evidence.invocation_mode not in {"mcp_prompt_only", "host_prepared_cli"}:
        raise AuthoringEvidenceError("invocation_mode is invalid")
    if evidence.reviewer_decision not in {"pending", "approved", "rejected"}:
        raise AuthoringEvidenceError("reviewer_decision is invalid")
    if evidence.reviewer_decision == "pending":
        if evidence.reviewer_id is not None:
            raise AuthoringEvidenceError("pending review must not name a reviewer")
        if evidence.observed_status == "pass":
            raise AuthoringEvidenceError("unreviewed evidence cannot pass")
    else:
        _text(evidence.reviewer_id, "reviewer_id")
    if evidence.observed_status == "pass":
        if (
            evidence.expected_status != "pass"
            or evidence.reviewer_decision != "approved"
        ):
            raise AuthoringEvidenceError("observed pass is not approved")


def _validate_optional_digests(evidence: AuthorThenRunEvidence) -> None:
    for value, label in (
        (evidence.final_package_digest, "final_package_digest"),
        (evidence.catalog_revision_digest, "catalog_revision_digest"),
        (evidence.registration_digest, "registration_digest"),
        (
            evidence.prepared_input_registration_digest,
            "prepared_input_registration_digest",
        ),
        (evidence.action_trace_digest, "action_trace_digest"),
        (evidence.authoring_receipt_digest, "authoring_receipt_digest"),
        (evidence.marketplace_manifest_digest, "marketplace_manifest_digest"),
        (evidence.generated_manifest_digest, "generated_manifest_digest"),
        (evidence.router_authority_digest, "router_authority_digest"),
        (evidence.payload_manifest_digest, "payload_manifest_digest"),
        (evidence.source_map_digest, "source_map_digest"),
        (evidence.release_metadata_digest, "release_metadata_digest"),
        (
            evidence.dar_runtime_wheel_metadata_digest,
            "dar_runtime_wheel_metadata_digest",
        ),
        (
            evidence.dar_runtime_release_descriptor_digest,
            "dar_runtime_release_descriptor_digest",
        ),
        (
            evidence.dar_runtime_payload_selector_list_digest,
            "dar_runtime_payload_selector_list_digest",
        ),
    ):
        if value is not None:
            _digest(value, label)
    for value, label in (
        (evidence.authoring_material_set_id, "authoring_material_set_id"),
        (evidence.authoring_output_id, "authoring_output_id"),
        (evidence.dar_runtime_version, "dar_runtime_version"),
        (evidence.dar_runtime_wheel_filename, "dar_runtime_wheel_filename"),
    ):
        if value is not None:
            _text(value, label)


def _validate_author_then_run_terminal_phase(evidence: AuthorThenRunEvidence) -> None:
    if evidence.terminal_phase not in {
        "authoring_validation",
        "source_selection",
        "capability_preflight",
        "registration",
        "invocation",
    }:
        raise AuthoringEvidenceError("terminal_phase is invalid")
    if (
        not isinstance(evidence.dispatch_count, int)
        or isinstance(evidence.dispatch_count, bool)
        or evidence.dispatch_count < 0
    ):
        raise AuthoringEvidenceError("dispatch_count is invalid")
    if evidence.observed_status in {"pass", "pending_human_review"}:
        required = (
            evidence.authoring_material_set_id,
            evidence.authoring_output_id,
            evidence.authoring_receipt_digest,
            evidence.final_package_digest,
            evidence.catalog_revision_digest,
            evidence.registration_digest,
            evidence.prepared_input_registration_digest,
            evidence.marketplace_manifest_digest,
        )
        if any(value is None for value in required):
            raise AuthoringEvidenceError("positive evidence requires handoff digests")
        if evidence.registration_digest != evidence.prepared_input_registration_digest:
            raise AuthoringEvidenceError("prepared input registration does not match")
        if evidence.action_trace_digest is None:
            raise AuthoringEvidenceError("positive evidence requires an action trace")
        return
    if evidence.observed_status not in {
        "expected_capability_unavailable",
        "expected_refusal",
        "harness_failure",
    }:
        return
    if evidence.dispatch_count != 0:
        raise AuthoringEvidenceError("non-pass evidence requires zero dispatch")
    prohibited = _later_evidence_for_terminal_phase(evidence)
    if any(value is not None for value in prohibited):
        raise AuthoringEvidenceError("non-pass evidence contains later evidence")


def _validate_actor_durations(value: tuple[int, ...]) -> None:
    if not isinstance(value, tuple) or any(
        not isinstance(duration, int) or isinstance(duration, bool) or duration < 0
        for duration in value
    ):
        raise AuthoringEvidenceError("actor durations are invalid")


def _validate_diagnostics(evidence: AuthorThenRunEvidence) -> None:
    for value, label in (
        (evidence.author_return_code, "author_return_code"),
        (evidence.invocation_return_code, "invocation_return_code"),
    ):
        if value is not None and (not isinstance(value, int) or value < 0):
            raise AuthoringEvidenceError(f"{label} is invalid")
    for values, label in (
        (evidence.author_decisions, "author_decisions"),
        (evidence.invocation_decisions, "invocation_decisions"),
        (evidence.author_event_trace, "author_event_trace"),
        (evidence.invocation_event_trace, "invocation_event_trace"),
    ):
        if not isinstance(values, tuple) or any(
            not isinstance(item, str) or not item or len(item) > 96 for item in values
        ):
            raise AuthoringEvidenceError(f"{label} is invalid")
    if evidence.failure_reason is not None and (
        not isinstance(evidence.failure_reason, str)
        or not evidence.failure_reason
        or len(evidence.failure_reason) > 96
    ):
        raise AuthoringEvidenceError("failure_reason is invalid")


def _later_evidence_for_terminal_phase(
    evidence: AuthorThenRunEvidence,
) -> tuple[str | None, ...]:
    if evidence.terminal_phase == "authoring_validation":
        return (
            evidence.final_package_digest,
            evidence.catalog_revision_digest,
            evidence.registration_digest,
            evidence.prepared_input_registration_digest,
            evidence.action_trace_digest,
        )
    if evidence.terminal_phase == "source_selection":
        return (
            evidence.catalog_revision_digest,
            evidence.registration_digest,
            evidence.prepared_input_registration_digest,
            evidence.action_trace_digest,
        )
    if evidence.terminal_phase in {"capability_preflight", "registration"}:
        return (
            evidence.registration_digest,
            evidence.prepared_input_registration_digest,
            evidence.action_trace_digest,
        )
    return ()


def _validate_mcp_summary(evidence: AuthorThenRunEvidence) -> None:
    if evidence.controller_fixture_digest is not None:
        _digest(evidence.controller_fixture_digest, "controller_fixture_digest")
    for value, label in (
        (evidence.mcp_snapshot_id, "mcp_snapshot_id"),
        (evidence.mcp_binding_id, "mcp_binding_id"),
    ):
        if value is not None:
            _text(value, label)
    if (
        not isinstance(evidence.mcp_read_tool_names, tuple)
        or any(
            not isinstance(name, str) or not name
            for name in evidence.mcp_read_tool_names
        )
        or len(set(evidence.mcp_read_tool_names)) != len(evidence.mcp_read_tool_names)
    ):
        raise AuthoringEvidenceError("MCP read-tool summary is invalid")
    for value, label in (
        (evidence.mcp_read_call_count, "mcp_read_call_count"),
        (evidence.forbidden_send_dispatch_count, "forbidden_send_dispatch_count"),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise AuthoringEvidenceError(f"{label} is invalid")


def _digest(value: object, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise AuthoringEvidenceError(f"{label} is invalid")


def _text(value: object, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise AuthoringEvidenceError(f"{label} is invalid")
