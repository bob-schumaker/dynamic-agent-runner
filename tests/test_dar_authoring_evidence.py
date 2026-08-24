"""Tests for redacted external authoring-evidence records."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


from dynamic_agent_runner.workflow_host.authoring_evidence import (  # noqa: E402
    AuthoringEvidence,
    AuthoringEvidenceError,
    write_authoring_evidence,
)


def _evidence(**overrides: object) -> AuthoringEvidence:
    values: dict[str, object] = {
        "corpus_digest": "a" * 64,
        "prompt_digest": "b" * 64,
        "material_set_id": "v1.material-set.signature",
        "authoring_provider": "local-test-provider",
        "authoring_model_id": "local-test-model",
        "generated_package_digests": ("c" * 64,),
        "validator_result": "passed",
        "reviewer_decision": "approved",
        "pass_criteria": ("package_loader", "fixture_contract"),
        "retention_policy": "redacted-evidence-v1",
    }
    values.update(overrides)
    return AuthoringEvidence(**values)  # type: ignore[arg-type]


def test_evidence_is_redacted_and_written_atomically(tmp_path: Path) -> None:
    destination = tmp_path / "evidence.json"

    write_authoring_evidence(destination, _evidence())

    value = json.loads(destination.read_text(encoding="utf-8"))
    assert value == {
        "authoring_model_id": "local-test-model",
        "authoring_provider": "local-test-provider",
        "corpus_digest": "a" * 64,
        "format_version": 1,
        "generated_package_digests": ["c" * 64],
        "material_set_id": "v1.material-set.signature",
        "pass_criteria": ["package_loader", "fixture_contract"],
        "prompt_digest": "b" * 64,
        "retention_policy": "redacted-evidence-v1",
        "reviewer_decision": "approved",
        "validator_result": "passed",
    }
    assert "prompt" not in value
    assert "material_content" not in value
    assert destination.stat().st_mode & 0o777 == 0o600


def test_evidence_records_a_failed_generation_without_a_valid_package_digest() -> None:
    evidence = _evidence(
        generated_package_digests=(),
        validator_result="failed",
        reviewer_decision="rejected",
    )

    assert evidence.to_mapping()["generated_package_digests"] == []


@pytest.mark.parametrize(
    "field,value",
    (
        ("corpus_digest", "not-a-digest"),
        ("validator_result", "unknown"),
        ("reviewer_decision", "pending"),
        ("pass_criteria", ()),
        ("retention_policy", ""),
    ),
)
def test_evidence_rejects_invalid_release_decision_fields(
    field: str, value: object
) -> None:
    with pytest.raises(AuthoringEvidenceError):
        _evidence(**{field: value})


def test_evidence_requires_a_valid_package_digest_for_a_passed_generation() -> None:
    with pytest.raises(AuthoringEvidenceError, match="generated package digests"):
        _evidence(generated_package_digests=())
