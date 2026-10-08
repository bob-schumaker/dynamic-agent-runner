"""Private candidate validation for reviewed host-capability outputs."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from jsonschema import Draft202012Validator, SchemaError, ValidationError

from dynamic_agent_runner.workflow_host.capabilities import (
    ReviewedCapabilityTemplateOutput,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactHandleError,
    SealedArtifactOutput,
    SealedArtifactOutputHandleService,
    SealedArtifactPrivateOutputSet,
)


class ReviewedCapabilityCandidateOutputError(ValueError):
    """Raised when a private reviewed-capability candidate is unsafe."""


@dataclass(frozen=True)
class ReviewedCapabilityCandidateOutput:
    """One private, handle-free host output candidate."""

    role: str
    media_type: str
    content: bytes


@dataclass(frozen=True)
class ReviewedCapabilityHostContribution:
    """The closed host contribution to DAR's later success receipt."""

    generation_id: str
    counts: Mapping[str, int]


@dataclass(frozen=True)
class StagedReviewedCapabilityCandidates:
    """Validated host candidates retained privately for later publication."""

    private: SealedArtifactPrivateOutputSet
    contribution: ReviewedCapabilityHostContribution


_COUNT_FIELDS = frozenset(
    {"source_records", "embedding_units", "indexed", "skipped", "deleted", "errored"}
)
_UNSAFE_MANIFEST_KEY_PARTS = frozenset(
    {"content", "path", "profile", "vector", "source_identifier", "source_id"}
)


def validate_reviewed_capability_candidates(
    *,
    outputs: Sequence[ReviewedCapabilityTemplateOutput],
    candidates: Sequence[ReviewedCapabilityCandidateOutput],
    canonical_manifest_schema: Mapping[str, object],
    contribution: ReviewedCapabilityHostContribution,
    count_ceiling: int,
) -> tuple[ReviewedCapabilityCandidateOutput, ...]:
    """Validate all private candidates before a host pending-publication call."""

    expected = tuple(outputs)
    received = tuple(candidates)
    if (
        not expected
        or len(expected) != len(received)
        or not isinstance(count_ceiling, int)
        or isinstance(count_ceiling, bool)
        or count_ceiling < 0
    ):
        raise ReviewedCapabilityCandidateOutputError("candidate is invalid")
    for output, candidate in zip(expected, received, strict=True):
        if (
            not isinstance(output, ReviewedCapabilityTemplateOutput)
            or not isinstance(candidate, ReviewedCapabilityCandidateOutput)
            or candidate.role != output.role
            or candidate.media_type != output.media_type
            or not isinstance(candidate.content, bytes)
            or len(candidate.content) > output.max_bytes
        ):
            raise ReviewedCapabilityCandidateOutputError("candidate is invalid")
    _validate_contribution(contribution, count_ceiling)
    values = {candidate.role: candidate for candidate in received}
    _validate_manifest(
        values.get("index_manifest"),
        canonical_manifest_schema=canonical_manifest_schema,
    )
    _validate_coverage(values.get("coverage_report"), count_ceiling)
    return received


def stage_reviewed_capability_candidates(
    *,
    artifacts: SealedArtifactOutputHandleService,
    template_digest: str,
    outputs: Sequence[ReviewedCapabilityTemplateOutput],
    candidates: Sequence[ReviewedCapabilityCandidateOutput],
    canonical_manifest_schema: Mapping[str, object],
    contribution: ReviewedCapabilityHostContribution,
    count_ceiling: int,
    receiver_id: str,
    revision_digest: str,
    invocation_id: str,
    expires_at: datetime,
    now: datetime,
) -> StagedReviewedCapabilityCandidates:
    """Validate then privately stage the vector template's declared candidates."""

    accepted = validate_reviewed_capability_candidates(
        outputs=outputs,
        candidates=candidates,
        canonical_manifest_schema=canonical_manifest_schema,
        contribution=contribution,
        count_ceiling=count_ceiling,
    )
    if not isinstance(artifacts, SealedArtifactOutputHandleService):
        raise ReviewedCapabilityCandidateOutputError("candidate is invalid")
    retention_seconds = {output.retention_seconds for output in outputs}
    if len(retention_seconds) != 1 or expires_at != now + timedelta(
        seconds=retention_seconds.pop()
    ):
        raise ReviewedCapabilityCandidateOutputError("candidate is invalid")
    declarations = tuple(
        SealedArtifactOutput(
            output.role,
            output.media_type,
            output.max_bytes,
            None,
        )
        for output in outputs
    )
    try:
        private = artifacts.stage_declared(
            declaration_digest=template_digest,
            outputs=declarations,
            receiver_id=receiver_id,
            revision_digest=revision_digest,
            invocation_id=invocation_id,
            sealed=tuple(
                (candidate.role, candidate.media_type, candidate.content)
                for candidate in accepted
            ),
            expires_at=expires_at,
            now=now,
        )
    except SealedArtifactHandleError as error:
        raise ReviewedCapabilityCandidateOutputError("candidate is invalid") from error
    return StagedReviewedCapabilityCandidates(private, contribution)


def _validate_contribution(contribution: object, count_ceiling: int) -> None:
    if (
        not isinstance(contribution, ReviewedCapabilityHostContribution)
        or not isinstance(contribution.generation_id, str)
        or not contribution.generation_id
        or set(contribution.counts) != _COUNT_FIELDS
        or any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            or value > count_ceiling
            for value in contribution.counts.values()
        )
    ):
        raise ReviewedCapabilityCandidateOutputError("candidate is invalid")


def _validate_manifest(
    candidate: ReviewedCapabilityCandidateOutput | None,
    *,
    canonical_manifest_schema: Mapping[str, object],
) -> None:
    if candidate is None:
        return
    document = _json_object(candidate.content)
    try:
        schema = dict(canonical_manifest_schema)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(document)
    except (SchemaError, ValidationError) as error:
        raise ReviewedCapabilityCandidateOutputError("candidate is invalid") from error
    if _contains_unsafe_manifest_key(document):
        raise ReviewedCapabilityCandidateOutputError("candidate is invalid")


def _validate_coverage(
    candidate: ReviewedCapabilityCandidateOutput | None, count_ceiling: int
) -> None:
    if candidate is None:
        return
    document = _json_object(candidate.content)
    if any(
        key not in _COUNT_FIELDS
        or not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        or value > count_ceiling
        for key, value in document.items()
    ):
        raise ReviewedCapabilityCandidateOutputError("candidate is invalid")


def _json_object(content: bytes) -> Mapping[str, object]:
    try:
        document = json.loads(content)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReviewedCapabilityCandidateOutputError("candidate is invalid") from error
    if not isinstance(document, dict) or not all(
        isinstance(key, str) for key in document
    ):
        raise ReviewedCapabilityCandidateOutputError("candidate is invalid")
    return document


def _contains_unsafe_manifest_key(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(
            any(part in key.lower() for part in _UNSAFE_MANIFEST_KEY_PARTS)
            or _contains_unsafe_manifest_key(item)
            for key, item in value.items()
            if isinstance(key, str)
        )
    if isinstance(value, list):
        return any(_contains_unsafe_manifest_key(item) for item in value)
    return False
