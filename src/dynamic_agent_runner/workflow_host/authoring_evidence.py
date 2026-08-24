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
            "reviewer_decision": self.reviewer_decision,
            "pass_criteria": list(self.pass_criteria),
            "retention_policy": self.retention_policy,
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
