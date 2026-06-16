# PyInstaller Packaging Support Implementation Plan

Status: implemented v1 baseline

## Goal

Record the implemented PyInstaller packaging support that allows downstream
PyInstaller clients to discover and use the package-owned
`openai-model-registry` hook.

## Spec Trace

- Spec: `specs/pyinstaller-packaging-support/spec.md`
- Primary runtime spec: `specs/dynamic-agent-runner/spec.md`
- Implementation surfaces:
  - `pyproject.toml`
  - `src/dynamic_agent_runner/__pyinstaller/__init__.py`
  - `src/dynamic_agent_runner/__pyinstaller/hook-openai_model_registry.py`
  - `tests/test_pyinstaller.py`

## Implemented Baseline

- `pyproject.toml` declares the `pyinstaller40` entry point:
  `hook-dirs = "dynamic_agent_runner.__pyinstaller:get_hook_dirs"`.
- `dynamic_agent_runner.__pyinstaller.get_hook_dirs()` returns the package-local
  PyInstaller hook directory.
- `hook-openai_model_registry.py` collects `openai_model_registry` data files and
  copies `openai-model-registry` distribution metadata.
- `tests/test_pyinstaller.py` verifies that the advertised hook directory exists
  and contains the expected hook file.

## Delivery Record

### Slice 1 — Hook Directory Advertisement

Status: complete.

Implemented package-owned hook directory discovery:

- add `src/dynamic_agent_runner/__pyinstaller/__init__.py`
- add `get_hook_dirs()` returning the hook package directory
- advertise `get_hook_dirs()` through the `pyinstaller40` entry-point group

### Slice 2 — `openai-model-registry` Hook

Status: complete.

Implemented the dependency hook:

- add `hook-openai_model_registry.py`
- collect `openai_model_registry` data files
- copy installed metadata for `openai-model-registry`
- avoid network, model, or registry-refresh behavior in hook evaluation

### Slice 3 — Test and Completion Evidence

Status: complete.

Added focused test coverage:

- verify the package returns one hook directory
- verify the hook directory exists
- verify the `openai_model_registry` hook file is present

## Design Decisions

- Keep PyInstaller support package-local and discoverable by standard
  PyInstaller entry-point lookup.
- Do not make downstream clients configure hook paths manually when the package
  can advertise them.
- Do not run PyInstaller in unit tests; the package only needs to prove that the
  advertised hook directory and hook file are present.
- Do not broaden this feature into generic frozen-application build support.

## Validation Strategy

Focused validation uses:

- `poetry run pytest tests/test_pyinstaller.py -q`
- `pre-commit run --files pyproject.toml`
  `src/dynamic_agent_runner/__pyinstaller/__init__.py`
  `src/dynamic_agent_runner/__pyinstaller/hook-openai_model_registry.py`
  `tests/test_pyinstaller.py`
  `specs/pyinstaller-packaging-support/spec.md`
  `specs/pyinstaller-packaging-support/plan.md`
  `specs/pyinstaller-packaging-support/tasks.md`
  `specs/pyinstaller-packaging-support/validation.md`

No validation should build a live downstream application unless a future
packaging-release task explicitly requires it.
