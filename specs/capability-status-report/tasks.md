# Capability Status Report Task List

Status: ready for first implementation slice

## Slice 0 — Planning Checkpoint

- [x] T0.1 Resolve v1 public API, validation path, state vocabulary, and CLI
      deferral decisions in `spec.md`.
- [x] T0.2 Add `plan.md`, `tasks.md`, and `validation.md` before implementation.
- [x] T0.3 Commit the planning checkpoint before code changes.
  - Completed in commit `0367f84`
    (`docs(specs): plan capability status report`)

## Slice 1 — Public Report Contract

- [x] T1.1 [tests] Add RED tests for package-root exports and report dataclass
      shape.
  - Spec: FR-1, FR-4, FR-5
  - Files/components: `tests/test_capabilities.py`,
    `src/dynamic_agent_runner/__init__.py`,
    `src/dynamic_agent_runner/capabilities.py`
  - Validation: `poetry run pytest tests/test_capabilities.py -q`
  - RED:
    - `poetry run pytest tests/test_capabilities.py -q` — failed with missing
      `CapabilityState` package export and missing
      `dynamic_agent_runner.capabilities` module

- [x] T1.2 [implementation] Add `CapabilityState`,
      `CapabilityStatusItem`, `CapabilityStatusSummary`, and
      `CapabilityStatusReport`.
  - Spec: FR-1, FR-4, FR-5
  - Files/components: `src/dynamic_agent_runner/capabilities.py`,
    `src/dynamic_agent_runner/__init__.py`
  - Validation: `poetry run pytest tests/test_capabilities.py -q`
  - GREEN:
    - `poetry run pytest tests/test_capabilities.py tests/test_import.py -q` —
      `3 passed in 0.12s`

## Slice 2 — Package Inspection and Metadata-Only Reporting

- [x] T2.1 [tests] Add RED tests for metadata-only approval, sandbox, MCP,
      guardrail, skill, loop, async session, and handoff declarations.
  - Spec: FR-1, FR-2, FR-4
  - Files/components: `tests/test_capabilities.py`
  - Validation: `poetry run pytest tests/test_capabilities.py -q`
  - RED:
    - `poetry run pytest tests/test_capabilities.py -q` — failed because
      `inspect_agent_package_capabilities(...)` still raised the Slice 1
      placeholder `NotImplementedError`

- [x] T2.2 [implementation] Add `inspect_agent_package_capabilities(...)` using
      existing package loading, validation, and execution-plan preparation.
  - Spec: FR-1, FR-2, FR-4, FR-5
  - Files/components: `src/dynamic_agent_runner/capabilities.py`,
    `src/dynamic_agent_runner/__init__.py`
  - Validation: `poetry run pytest tests/test_capabilities.py -q`
  - GREEN:
    - `poetry run pytest tests/test_capabilities.py -q` —
      `4 passed in 0.12s`

## Slice 3 — Collaborator Coverage

- [ ] T3.1 [tests] Add RED tests for model adapter coverage, missing tools,
      disabled tools, and built-in tool-pack status.
  - Spec: FR-3, FR-5
  - Files/components: `tests/test_capabilities.py`
  - Validation: `poetry run pytest tests/test_capabilities.py -q`

- [ ] T3.2 [implementation] Report model adapter and tool registry coverage
      without invoking models or tools.
  - Spec: FR-3, FR-5
  - Files/components: `src/dynamic_agent_runner/capabilities.py`
  - Validation: `poetry run pytest tests/test_capabilities.py -q`

## Slice 4 — Validation and Completion Evidence

- [ ] T4.1 [validation] Run focused capability tests.
  - Command: `poetry run pytest tests/test_capabilities.py -q`

- [ ] T4.2 [validation] Run affected package tests.
  - Command:
    `poetry run pytest tests/test_capabilities.py tests/test_validation.py`
    `tests/test_executor.py tests/test_import.py -q`

- [ ] T4.3 [validation] Run focused pre-commit.
  - Command:
    `pre-commit run --files src/dynamic_agent_runner/capabilities.py`
    `src/dynamic_agent_runner/__init__.py tests/test_capabilities.py`
    `specs/capability-status-report/spec.md`
    `specs/capability-status-report/plan.md`
    `specs/capability-status-report/tasks.md`
    `specs/capability-status-report/validation.md`

- [ ] T4.4 [docs] Record validation evidence in
      `specs/capability-status-report/validation.md`.
