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

    def to_mapping(self) -> dict[str, object]:
        """Return the stable evidence projection without raw authoring input."""

        return {
            "format_version": 1,
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
    isolation_policy_digest: str
    executable_identity: str
    module_identity: str
    final_package_digest: str | None
    catalog_revision_digest: str | None
    registration_digest: str | None
    prepared_input_registration_digest: str | None
    action_trace_digest: str | None
    dispatch_count: int
    reviewer_id: str | None
    reviewer_decision: str

    def __post_init__(self) -> None:
        _validate_author_then_run_text(self)
        _digest(self.wheel_digest, "wheel_digest")
        _digest(self.isolation_policy_digest, "isolation_policy_digest")
        _validate_author_then_run_status(self)
        _validate_optional_digests(self)
        _validate_author_then_run_terminal_phase(self)

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
            "isolation_policy_digest": self.isolation_policy_digest,
            "executable_identity": self.executable_identity,
            "module_identity": self.module_identity,
            "final_package_digest": self.final_package_digest,
            "catalog_revision_digest": self.catalog_revision_digest,
            "registration_digest": self.registration_digest,
            "prepared_input_registration_digest": self.prepared_input_registration_digest,
            "action_trace_digest": self.action_trace_digest,
            "dispatch_count": self.dispatch_count,
            "reviewer_id": self.reviewer_id,
            "reviewer_decision": self.reviewer_decision,
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
    else:
        _text(evidence.reviewer_id, "reviewer_id")


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
    ):
        if value is not None:
            _digest(value, label)


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
    if evidence.expected_status == "pass":
        required = (
            evidence.final_package_digest,
            evidence.catalog_revision_digest,
            evidence.registration_digest,
            evidence.prepared_input_registration_digest,
        )
        if any(value is None for value in required):
            raise AuthoringEvidenceError("positive evidence requires handoff digests")
        if evidence.registration_digest != evidence.prepared_input_registration_digest:
            raise AuthoringEvidenceError("prepared input registration does not match")
        if evidence.action_trace_digest is None:
            raise AuthoringEvidenceError("positive evidence requires an action trace")
        return
    if evidence.dispatch_count != 0:
        raise AuthoringEvidenceError("non-pass evidence requires zero dispatch")
    prohibited = _later_evidence_for_terminal_phase(evidence)
    if any(value is not None for value in prohibited):
        raise AuthoringEvidenceError("non-pass evidence contains later evidence")


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
