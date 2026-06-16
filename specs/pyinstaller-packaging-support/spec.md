# PyInstaller Packaging Support Specification

## Metadata

- Feature slug: `pyinstaller-packaging-support`
- Mode: `light`
- Artifact type: authoritative packaging feature specification
- Status: implemented v1 baseline; `openai-model-registry` hook discovery,
  hook contents, package advertisement, tests, and focused validation complete
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related implementation surfaces:
  - `pyproject.toml`
  - `src/dynamic_agent_runner/__pyinstaller/__init__.py`
  - `src/dynamic_agent_runner/__pyinstaller/hook-openai_model_registry.py`
  - `tests/test_pyinstaller.py`

## Objective

Define the package-owned PyInstaller integration that lets downstream
PyInstaller clients bundle `dynamic-agent-runner` workflows that depend on
`openai-model-registry` without each client hand-authoring the same hook.

## Problem Statement

`dynamic-agent-runner` uses `openai-model-registry` for model capability
metadata. PyInstaller does not always discover package data files and installed
distribution metadata automatically. Without a package-advertised hook,
downstream frozen applications can fail at runtime because registry data or
metadata is missing from the bundle.

The repository already implements and tests the hook. This spec records the
feature boundary and completion evidence so the work is represented in the SDD
surface.

## Scope

This feature covers:

1. a package-local PyInstaller hook directory
2. a hook for `openai_model_registry`
3. collection of `openai_model_registry` data files
4. copying installed distribution metadata for `openai-model-registry`
5. package advertisement through the `pyinstaller40` entry point group
6. tests proving the package exposes the hook directory and hook file

This feature does not cover:

1. building this repository with PyInstaller in CI
2. shipping a downstream frozen application
3. writing hooks for unrelated optional dependencies
4. replacing `openai-model-registry` with package-local model metadata
5. testing PyInstaller's own hook execution internals

## Functional Requirements

### FR-1: Advertise package-owned PyInstaller hooks

The installed package must let PyInstaller discover its hook directory through
standard entry-point discovery.

Acceptance criteria:

- Given the package is installed, when PyInstaller evaluates the `pyinstaller40`
  entry-point group, then it can resolve
  `dynamic_agent_runner.__pyinstaller:get_hook_dirs`.
- Given `get_hook_dirs()` is called, when it returns hook directories, then the
  first returned path exists and contains the package-owned hooks.

### FR-2: Collect `openai-model-registry` runtime assets

The package-owned hook must collect the runtime assets required by
`openai-model-registry`.

Acceptance criteria:

- Given PyInstaller loads `hook-openai_model_registry.py`, when hook variables
  are evaluated, then `datas` includes `collect_data_files("openai_model_registry")`.
- Given PyInstaller loads the same hook, then `datas` also includes
  `copy_metadata("openai-model-registry")`.
- Given the hook is imported by PyInstaller, then it does not perform network,
  model, registry-refresh, or downstream application work.

### FR-3: Keep packaging support narrow

The PyInstaller integration must remain a packaging support layer rather than a
runtime feature.

Acceptance criteria:

- Given normal library import or workflow execution, when PyInstaller is not in
  use, then the hook code is not part of runtime model execution.
- Given new optional dependencies are added later, then their hooks require a
  separate spec update or task slice rather than being added opportunistically.
- Given downstream clients need custom application hooks, then this package only
  owns hooks for dependencies required by this package's own runtime behavior.

## Implementation Status

- Implemented `dynamic_agent_runner.__pyinstaller.get_hook_dirs()`.
- Added package-owned `hook-openai_model_registry.py`.
- Added `pyinstaller40` entry-point advertisement in `pyproject.toml`.
- Added unit coverage in `tests/test_pyinstaller.py`.
- Completed focused validation with
  `poetry run pytest tests/test_pyinstaller.py -q`.

## Validation Checklist

- [x] Hook directory resolver exists and returns the package hook directory.
- [x] Hook directory contains `hook-openai_model_registry.py`.
- [x] Hook collects `openai_model_registry` data files.
- [x] Hook copies `openai-model-registry` distribution metadata.
- [x] `pyproject.toml` advertises hook discovery through `pyinstaller40`.
- [x] Unit tests cover hook-directory advertisement without running PyInstaller.
