# DAR Authoring Plugin Validation Evidence

## Live Capability Fixture Audit

This record binds every currently advertised DAR-authoring capability to one
positive deterministic fixture. All named tests use injected fakes; the
fake-only unit-test policy blocks outbound IP connections. M8 is excluded: it
remains publication-gated and is not advertised live.

<!-- rumdl-disable MD013 -->

| Gate | Advertised capability | Positive fixture | Required positive outcome |
| --- | --- | --- | --- |
| G0 | Installed DAR CLI discovery and skills-only plugin shape | `tests/test_verify_dar_package_wheel.py::test_verifier_runs_dar_package_from_an_isolated_wheel` | An isolated wheel exposes `dar-package version --json`. |
| G0 | No plugin-provided MCP server | `tests/test_dar_authoring_plugin.py::test_plugin_is_skills_only` | The bundle has no MCP configuration or legacy launcher. |
| G1 | Package-only catalog preflight | `tests/test_dar_authoring_preflight.py::test_preflight_returns_only_package_policy_and_capability_result` | Preflight returns the package/policy/capability result without a live registration. |
| G3 | Sealed no-tool workflow execution | `tests/test_dar_authoring_runner.py::test_runner_executes_one_sealed_no_tool_workflow` | One registered workflow returns its bounded terminal result through the fake model adapter. |
| G2 + G3 | Reviewed read-only MCP workflow execution | `tests/test_dar_authoring_runner.py::test_runner_executes_one_registered_reviewed_read_only_mcp_workflow` | One fake reviewed read-only MCP handler dispatches within the declared policy. |
| G4 | Trusted workspace-file ingress | `tests/test_dar_authoring_cli.py::test_cli_ingresses_a_registered_workspace_file_without_returning_its_path` | A selected file becomes an opaque artifact without exposing its path. |
| G5 | `workflow_auto` side-effect execution | `tests/test_dar_authoring_runner.py::test_runner_executes_one_registered_reviewed_side_effecting_mcp_workflow` | One schema-valid fake side-effect dispatches once through the action ledger. |
| G5 | Local `--ask` approval path | `tests/test_dar_authoring_authorized_tools.py::test_authorized_binding_dispatches_only_after_local_approval` | One approved fake side effect dispatches once; unapproved paths are covered by adjacent negative tests. |

<!-- rumdl-enable MD013 -->

The regression check
[`tests/test_dar_authoring_live_capability_fixtures.py`](../../tests/test_dar_authoring_live_capability_fixtures.py)
requires each named fixture to remain both present in this record and defined
as a test.
