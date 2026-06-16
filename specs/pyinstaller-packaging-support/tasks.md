# PyInstaller Packaging Support Task List

Status: implemented v1 baseline

## Prerequisites

- Spec: `specs/pyinstaller-packaging-support/spec.md`
- Plan: `specs/pyinstaller-packaging-support/plan.md`
- Implementation surfaces:
  - `pyproject.toml`
  - `src/dynamic_agent_runner/__pyinstaller/__init__.py`
  - `src/dynamic_agent_runner/__pyinstaller/hook-openai_model_registry.py`
  - `tests/test_pyinstaller.py`

## Scope Rule

Keep this feature limited to package-owned PyInstaller hook discovery and the
`openai-model-registry` hook required by this package. Do not add hooks for
unrelated optional dependencies, downstream application packaging, or live
PyInstaller build execution.

## Slice 1 — Hook Directory Advertisement

- [x] T1.1 [implementation] Add package-local PyInstaller hook directory support.
  - Spec: FR-1
  - Plan: Slice 1
  - Files/components: `src/dynamic_agent_runner/__pyinstaller/__init__.py`
  - Validation: `poetry run pytest tests/test_pyinstaller.py -q`

- [x] T1.2 [implementation] Advertise the hook directory through
      `pyinstaller40`.
  - Spec: FR-1
  - Plan: Slice 1
  - Files/components: `pyproject.toml`
  - Validation: `poetry check`

## Slice 2 — `openai-model-registry` Hook

- [x] T2.1 [implementation] Add `hook-openai_model_registry.py`.
  - Spec: FR-2, FR-3
  - Plan: Slice 2
  - Files/components:
    `src/dynamic_agent_runner/__pyinstaller/hook-openai_model_registry.py`
  - Validation: `poetry run pytest tests/test_pyinstaller.py -q`

- [x] T2.2 [implementation] Collect `openai_model_registry` data files and copy
      `openai-model-registry` distribution metadata.
  - Spec: FR-2
  - Plan: Slice 2
  - Files/components:
    `src/dynamic_agent_runner/__pyinstaller/hook-openai_model_registry.py`
  - Validation: `poetry run pytest tests/test_pyinstaller.py -q`

## Slice 3 — Completion Evidence

- [x] T3.1 [tests] Add focused PyInstaller hook advertisement coverage.
  - Spec: FR-1
  - Plan: Slice 3
  - Files/components: `tests/test_pyinstaller.py`
  - Validation: `poetry run pytest tests/test_pyinstaller.py -q`

- [x] T3.2 [spec-maintenance] Add post-hoc SDD representation for the completed
      packaging support.
  - Spec: Metadata, Validation Checklist
  - Plan: Slice 3
  - Files/components:
    `specs/pyinstaller-packaging-support/spec.md`,
    `specs/pyinstaller-packaging-support/plan.md`,
    `specs/pyinstaller-packaging-support/tasks.md`,
    `specs/pyinstaller-packaging-support/validation.md`, `specs/README.md`,
    `specs/dynamic-agent-runner/tasks.md`
  - Validation:
    `pre-commit run --files specs/pyinstaller-packaging-support/spec.md`
    `specs/pyinstaller-packaging-support/plan.md`
    `specs/pyinstaller-packaging-support/tasks.md`
    `specs/pyinstaller-packaging-support/validation.md specs/README.md`
    `specs/dynamic-agent-runner/tasks.md`

## Final Validation

Completed implementation was validated with:

- `poetry run pytest tests/test_pyinstaller.py -q`
- `pre-commit run --files` over the PyInstaller implementation files, test file,
  and SDD artifacts
