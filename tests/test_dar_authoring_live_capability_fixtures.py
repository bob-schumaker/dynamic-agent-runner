"""Keep v1 authored-workflow runtime claims bound to executable fixtures."""

from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
VALIDATION_RECORD = (
    REPOSITORY_ROOT / "specs" / "authored-workflow-runtime-v1" / "validation.md"
)
LIVE_FIXTURE_SELECTORS = (
    "tests/test_verify_dar_package_wheel.py::test_verifier_runs_dar_package_from_an_isolated_wheel",
    "tests/test_dar_authoring_plugin.py::test_plugin_is_skills_only",
    "tests/test_dar_authoring_preflight.py::test_preflight_returns_only_package_policy_and_capability_result",
    "tests/test_dar_authoring_runner.py::test_runner_executes_one_sealed_no_tool_workflow",
    "tests/test_dar_authoring_runner.py::test_runner_executes_one_registered_reviewed_read_only_mcp_workflow",
    "tests/test_dar_authoring_cli.py::test_cli_ingresses_a_registered_workspace_file_without_returning_its_path",
    "tests/test_dar_authoring_runner.py::test_runner_executes_one_registered_reviewed_side_effecting_mcp_workflow",
    "tests/test_dar_authoring_authorized_tools.py::test_authorized_binding_dispatches_only_after_local_approval",
)


def test_every_live_capability_claim_has_a_recorded_positive_fixture() -> None:
    record = VALIDATION_RECORD.read_text(encoding="utf-8")

    for selector in LIVE_FIXTURE_SELECTORS:
        test_path, test_name = selector.split("::")
        source = (REPOSITORY_ROOT / test_path).read_text(encoding="utf-8")
        assert f"def {test_name}(" in source
        assert selector in record
