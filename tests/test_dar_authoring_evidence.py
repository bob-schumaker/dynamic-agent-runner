"""Tests for redacted external authoring-evidence records."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import shutil

import pytest


from dynamic_agent_runner.workflow_host.authoring_evidence import (  # noqa: E402
    AuthorThenRunEvidence,
    AuthoringBehaviorEvidence,
    AuthoringEvidence,
    AuthoringEvidenceError,
    ExternalAuthoringHarnessRequest,
    ValidatingExternalAuthoringHarness,
    write_authoring_evidence,
    write_author_then_run_evidence,
)
from dynamic_agent_runner.workflow_host.authoring_materials import (  # noqa: E402
    AuthoringMaterialProjectionMember,
    AuthoringMaterialSetProjection,
)
from dynamic_agent_runner.workflow_host.authoring_output import (  # noqa: E402
    write_authored_package_manifest,
)


def _evidence(**overrides: object) -> AuthoringEvidence:
    values: dict[str, object] = {
        "corpus_digest": "a" * 64,
        "prompt_digest": "b" * 64,
        "material_set_id": "v1.material-set.signature",
        "package_revision_provenance": "external_authoring",
        "authoring_provider": "local-test-provider",
        "authoring_model_id": "local-test-model",
        "generated_package_digests": ("c" * 64,),
        "validator_result": "passed",
        "reviewer_id": "human-reviewer",
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
        "behavioral_runs": [],
        "corpus_digest": "a" * 64,
        "format_version": 2,
        "generated_package_digests": ["c" * 64],
        "material_set_id": "v1.material-set.signature",
        "package_revision_provenance": "external_authoring",
        "pass_criteria": ["package_loader", "fixture_contract"],
        "prompt_digest": "b" * 64,
        "retention_policy": "redacted-evidence-v1",
        "reviewer_id": "human-reviewer",
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
        ("reviewer_id", ""),
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


def test_evidence_binds_redacted_behavioral_run_facts(tmp_path: Path) -> None:
    destination = tmp_path / "evidence.json"
    evidence = _evidence(
        behavioral_runs=(
            AuthoringBehaviorEvidence(
                case_digest="d" * 64,
                transcript_digest="e" * 64,
                execution_model_id="gpt-5.6-terra",
                terminal_outcome="completed",
                tool_dispatch_count=1,
            ),
        )
    )

    write_authoring_evidence(destination, evidence)

    recorded = json.loads(destination.read_text(encoding="utf-8"))
    assert recorded["behavioral_runs"] == [
        {
            "case_digest": "d" * 64,
            "execution_model_id": "gpt-5.6-terra",
            "terminal_outcome": "completed",
            "tool_dispatch_count": 1,
            "transcript_digest": "e" * 64,
        }
    ]
    assert "transcript" not in recorded


def test_evidence_records_a_human_model_retarget_without_renaming_the_author() -> None:
    evidence = _evidence(
        package_revision_provenance="external_authoring_with_human_model_retarget"
    )

    assert (
        evidence.to_mapping()["package_revision_provenance"]
        == "external_authoring_with_human_model_retarget"
    )


def test_author_then_run_evidence_binds_a_positive_handoff_without_raw_content(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "author-then-run.json"
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
        module_identity="dynamic-agent-runner@0.2.1",
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
        marketplace_manifest_digest="f" * 64,
    )

    write_author_then_run_evidence(destination, evidence)

    recorded = json.loads(destination.read_text(encoding="utf-8"))
    assert recorded["format_version"] == 1
    assert recorded["final_package_digest"] == "b" * 64
    assert recorded["harness_policy_digest"] == "f" * 64
    assert recorded["executable_identity"] == "codex@0.149.1"
    assert recorded["authoring_receipt_digest"] == "0" * 64
    assert "prompt" not in recorded
    assert "material_content" not in recorded
    assert destination.stat().st_mode & 0o777 == 0o600


def test_author_then_run_evidence_requires_no_later_handles_for_early_refusal() -> None:
    with pytest.raises(AuthoringEvidenceError):
        AuthorThenRunEvidence(
            scenario_id="authoring-boundary-attack-v1",
            scenario_contract_version="m4.4-v1",
            checker_version="m4.4-checker-v1",
            expected_status="expected_refusal",
            observed_status="expected_refusal",
            terminal_phase="authoring_validation",
            invocation_mode="mcp_prompt_only",
            plugin_identity="dar-authoring@local-test",
            skill_identity="agent-development@local-test",
            wheel_digest="a" * 64,
            harness_policy_digest="f" * 64,
            executable_identity="codex@0.149.1",
            module_identity="dynamic-agent-runner@0.2.1",
            authoring_material_set_id=None,
            authoring_output_id=None,
            authoring_receipt_digest=None,
            final_package_digest=None,
            catalog_revision_digest="c" * 64,
            registration_digest=None,
            prepared_input_registration_digest=None,
            action_trace_digest=None,
            dispatch_count=0,
            reviewer_id=None,
            reviewer_decision="pending",
        )


def test_author_then_run_evidence_requires_zero_dispatch_for_a_non_pass() -> None:
    with pytest.raises(AuthoringEvidenceError, match="zero dispatch"):
        AuthorThenRunEvidence(
            scenario_id="capability-unavailable-v1",
            scenario_contract_version="m4.4-v1",
            checker_version="m4.4-checker-v1",
            expected_status="expected_capability_unavailable",
            observed_status="expected_capability_unavailable",
            terminal_phase="capability_preflight",
            invocation_mode="mcp_prompt_only",
            plugin_identity="dar-authoring@local-test",
            skill_identity="agent-development@local-test",
            wheel_digest="a" * 64,
            harness_policy_digest="f" * 64,
            executable_identity="codex@0.149.1",
            module_identity="dynamic-agent-runner@0.2.1",
            authoring_material_set_id=None,
            authoring_output_id=None,
            authoring_receipt_digest=None,
            final_package_digest="b" * 64,
            catalog_revision_digest="c" * 64,
            registration_digest=None,
            prepared_input_registration_digest=None,
            action_trace_digest=None,
            dispatch_count=1,
            reviewer_id=None,
            reviewer_decision="pending",
        )


def test_author_then_run_evidence_rejects_an_unreviewed_observed_pass() -> None:
    with pytest.raises(AuthoringEvidenceError, match="unreviewed"):
        AuthorThenRunEvidence(
            scenario_id="document-summary-v1",
            scenario_contract_version="m4.4-v1",
            checker_version="m4.4-checker-v1",
            expected_status="pass",
            observed_status="pass",
            terminal_phase="invocation",
            invocation_mode="mcp_prompt_only",
            plugin_identity="dar-authoring@local-test",
            skill_identity="agent-development@local-test",
            wheel_digest="a" * 64,
            harness_policy_digest="f" * 64,
            executable_identity="codex@0.149.1",
            module_identity="dynamic-agent-runner@0.2.1",
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
        )


def test_validating_external_harness_projects_only_selected_material_and_redacts_output(
    tmp_path: Path,
) -> None:
    template = (
        Path(__file__).resolve().parents[1]
        / "specs"
        / "agent-engineering-plugin-migration"
        / "legacy-dar-authoring"
        / "templates"
    )
    requests: list[ExternalAuthoringHarnessRequest] = []

    class Generator:
        def generate(self, request: ExternalAuthoringHarnessRequest) -> Path:
            requests.append(request)
            package = tmp_path / "generated-package"
            shutil.copytree(template, package)
            write_authored_package_manifest(package)
            return package

    request = ExternalAuthoringHarnessRequest(
        skill_name="agent-development",
        request="Create a bounded document workflow.",
        materials=AuthoringMaterialSetProjection(
            material_set_id="v1.material-set.example",
            members=(
                AuthoringMaterialProjectionMember(
                    artifact_id="v1.material.example",
                    digest="a" * 64,
                    role="example",
                    disposition="reference_only",
                    content="selected private example",
                ),
            ),
            expires_at=datetime(2026, 8, 24, tzinfo=UTC),
        ),
    )

    outcome = ValidatingExternalAuthoringHarness(Generator()).run(request)

    assert requests == [request]
    assert outcome.validator_result == "passed"
    assert len(outcome.generated_package_digests) == 1
    assert str(tmp_path) not in repr(outcome)
    assert "selected private example" not in repr(outcome)


def test_validating_external_harness_redacts_an_invalid_generated_package(
    tmp_path: Path,
) -> None:
    template = (
        Path(__file__).resolve().parents[1]
        / "specs"
        / "agent-engineering-plugin-migration"
        / "legacy-dar-authoring"
        / "templates"
    )

    class Generator:
        def generate(self, request: ExternalAuthoringHarnessRequest) -> Path:
            package = tmp_path / "generated-package"
            shutil.copytree(template, package)
            design = package / "agent-design.md"
            design.write_text(
                design.read_text(encoding="utf-8") + "\nselected private example\n",
                encoding="utf-8",
            )
            write_authored_package_manifest(package)
            return package

    request = ExternalAuthoringHarnessRequest(
        skill_name="agent-development",
        request="Create a bounded document workflow.",
        materials=AuthoringMaterialSetProjection(
            material_set_id="v1.material-set.example",
            members=(
                AuthoringMaterialProjectionMember(
                    artifact_id="v1.material.example",
                    digest="a" * 64,
                    role="example",
                    disposition="reference_only",
                    content="selected private example",
                ),
            ),
            expires_at=datetime(2026, 8, 24, tzinfo=UTC),
        ),
    )

    outcome = ValidatingExternalAuthoringHarness(Generator()).run(request)

    assert outcome == type(outcome)((), "failed")
    assert str(tmp_path) not in repr(outcome)
    assert "selected private example" not in repr(outcome)


def test_validating_external_harness_redacts_generator_failures() -> None:
    class BrokenGenerator:
        def generate(self, request: ExternalAuthoringHarnessRequest) -> Path:
            del request
            raise RuntimeError("private generator failure")

    request = ExternalAuthoringHarnessRequest(
        skill_name="agent-development",
        request="Create a bounded document workflow.",
        materials=AuthoringMaterialSetProjection(
            material_set_id="v1.material-set.example",
            members=(),
            expires_at=datetime(2026, 8, 24, tzinfo=UTC),
        ),
    )

    outcome = ValidatingExternalAuthoringHarness(BrokenGenerator()).run(request)

    assert outcome == type(outcome)((), "failed")
    assert "private generator failure" not in repr(outcome)
