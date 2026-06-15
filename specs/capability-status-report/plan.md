# Capability Status Report Implementation Plan

Status: active planning record; implementation not started

## Goal

Implement the first read-only capability/status report so callers can inspect a
workflow package before execution and distinguish live runtime behavior from
metadata-only declarations, missing collaborators, disabled capabilities,
unsupported features, and invalid package state.

## Scope for v1

- Add a package-owned report model and public API.
- Load and validate packages through existing artifact APIs.
- Prepare an execution plan when validation succeeds.
- Report current live baseline capabilities.
- Report metadata-only declarations for approval interruption, sandbox runtime,
  MCP registry sources, guardrails, skill refs/source loading, loop completion
  policy, async session metadata, and handoffs.
- Report model adapter coverage and tool registry coverage without invoking
  models or tools.
- Keep output deterministic and redacted.

## Out of Scope for v1

- CLI output.
- Implementing any metadata-only feature.
- Live MCP, guardrail, approval, sandbox, session, skill-source, loop, or
  interpreter behavior.
- Starting servers, invoking tools, calling models, or probing networks.

## Clarification Decisions

- Public API:
  `inspect_agent_package_capabilities(...)` exported from package root and
  backed by a dedicated implementation module.
- Validation path: use the existing package loading and validation path. Invalid
  packages return an `invalid` report by default; a strict mode may raise the
  original validation error.
- State vocabulary: `live`, `metadata_only`, `missing_collaborator`, `disabled`,
  `unsupported`, and `invalid`.
- Metadata-only handling: report as first-class items with summary counts, not
  as warnings.
- Spec references: use stable owning feature slugs rather than repository-local
  spec paths.

## Technical Approach

1. Create `src/dynamic_agent_runner/capabilities.py`.
2. Define frozen dataclasses for:
   - `CapabilityStatusReport`
   - `CapabilityStatusSummary`
   - `CapabilityStatusItem`
3. Define a `CapabilityState` string enum.
4. Add `inspect_agent_package_capabilities(...)` that accepts the same package
   inputs needed for preflight:
   - `package_directory`
   - optional `runtime_overrides`
   - optional `tool_registry`
   - optional `model_adapter`
   - optional `model_adapter_coverage`
   - optional `built_in_tool_packs`
   - optional `strict`
5. Reuse `load_agent_package_workflow(...)`, `prepare_execution_plan(...)`, and
   existing model/tool metadata instead of reparsing manifests.
6. Keep diagnostics short and deterministic.
7. Export the public API and report types from `dynamic_agent_runner.__init__`.

## Report Shape

Each item should include:

- stable `id`
- `label`
- `state`
- `category`
- `summary`
- optional `owner`
- optional `required_collaborator`
- optional `details`

The report should include:

- `package_id`
- tuple of items sorted by category/id
- summary counts by state
- `valid` boolean
- optional validation error string

## Validation Strategy

- Unit tests in `tests/test_capabilities.py`.
- Use existing fixture packages and in-memory manifest fixtures.
- Use fake model adapters and fake registries only.
- Do not execute workflows, tools, model calls, network calls, MCP calls, or live
  local-model probes.

## Risks

- Reporting can accidentally imply a deferred feature is live. Mitigation:
  metadata-only features must use `metadata_only` and explicit summary text.
- Reusing validation may make advisory reporting fail too hard. Mitigation:
  default report returns invalid status; strict mode can raise.
- Tool registry protocols are intentionally narrow. Mitigation: v1 reports
  coverage through existing `get_tool(...)` behavior without requiring broader
  registry introspection.
