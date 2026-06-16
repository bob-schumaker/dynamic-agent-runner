# SKILL.md Source Resolution Implementation Plan

## Purpose

Prepare a narrow v1 implementation for opt-in package-local `SKILL.md` source
loading. The goal is to let bundled package skills influence model prompts
through declared `skill_refs` while preserving the current safety boundary: no
implicit global skill directories, no arbitrary host-file reads, no network
fetching, and no generated-package mutation.

## Implementation Status

V1 is implemented. The remaining scope in this document describes deferred
expansions beyond opt-in package-local bundled `SKILL.md` loading.

## Current Baseline

Observed runtime surfaces:

- `LoadedAgentWorkflow` and `CompiledAgentWorkflow` already preserve
  `package_root`, `skill_bundle_root`, manifest `skills`, and node
  `skill_refs`.
- `validate_loaded_package_structure(...)` validates `skills[*].bundled_path`
  and `support_files[*].bundled_path` under package `skill-bundle/`.
- `behavior.effective_node_behavior(...)` builds an effective skill catalog from
  manifest, tool-index, and runtime override skills.
- `_render_message_parts(...)` injects only inline `skills[*].instructions`
  today.
- `capabilities.py` reports `metadata.skill_refs` as metadata-only because
  `SKILL.md` bodies are not loaded.

## V1 Scope

Implement only:

- opt-in policy under `runtime.execution_policy.skill_source_resolution`
- package-local `skills[*].bundled_path` loading under `skill-bundle/`
- UTF-8 Markdown/text skill bodies
- per-skill and per-node size limits
- deterministic injection in effective `skill_refs` order
- redacted provenance metadata and capability/status reporting
- tests with temporary package fixtures and fake model adapters only

Do not implement:

- external skill roots
- `source_path` reads
- global user skill discovery
- support-file prompt loading
- network fetching
- executable skill files
- raw skill-body trace payloads

## Runtime Contract

Policy example:

```yaml
runtime:
  execution_policy:
    skill_source_resolution:
      enabled: true
      allowed_sources:
        - package_bundle
      max_skill_bytes: 65536
      max_node_skill_bytes: 262144
      load_support_files: false
      prompt_role: developer
```

Default behavior when policy is absent or disabled:

- inline `instructions` continue to inject exactly as today
- bundled paths are validated as package metadata but not loaded
- capability/status reports remain metadata-only for skill refs

Behavior when policy is enabled:

- referenced skills with inline `instructions` inject those instructions
- referenced skills without inline `instructions` may load package-local
  `bundled_path` content
- missing, escaping, symlink-escaping, oversized, binary, or unsupported-encoding
  skill bodies fail before a model call
- support files remain validation metadata only

## Implementation Slices

### Slice 1: Policy and Data Model

Add parsed policy and resolver result types without changing execution behavior.

Likely files:

- `src/dynamic_agent_runner/models.py`
- `src/dynamic_agent_runner/validation.py`
- new `src/dynamic_agent_runner/skill_sources.py`
- `tests/test_validation.py`

Validation:

- policy accepts omitted/disabled state
- policy validates `enabled`, `allowed_sources`, byte limits, and
  `load_support_files`
- invalid policy shapes fail clearly

### Slice 2: Package-Local Resolver

Implement package-local bundled skill loading behind the policy.

Likely files:

- `src/dynamic_agent_runner/skill_sources.py`
- `src/dynamic_agent_runner/validation.py`
- `tests/test_validation.py`
- `tests/test_artifacts.py` or a new targeted test file

Validation:

- package-local `SKILL.md` loads only when enabled
- absolute paths, traversal, symlink escapes, missing files, binary-looking
  files, unsupported encodings, and size-limit violations fail before execution
- `source_path` is never read in v1
- support files are not loaded as prompt content

### Slice 3: Prompt Integration and Diagnostics

Inject resolved bodies through the existing skill-instruction lane and attach
redacted prepared-input metadata.

Likely files:

- `src/dynamic_agent_runner/behavior.py`
- `src/dynamic_agent_runner/executor.py`
- `src/dynamic_agent_runner/prompt_cache.py`
- `tests/test_executor.py`
- `tests/test_prompt_cache.py`

Validation:

- effective `skill_refs` order determines injection order
- runtime skill-reference overrides affect loaded source order without mutating
  package artifacts
- system/developer prompt remains before skills; file-backed context and user
  prompt remain after skills
- traces/prepared-input metadata identify loaded skills without raw skill body
  leakage

### Slice 4: Capability Status and Documentation

Report disabled, live, and rejected skill-source states, then update docs.

Likely files:

- `src/dynamic_agent_runner/capabilities.py`
- `README.md`
- `specs/README.md`
- `docs/files/` pages if user-facing API/CLI docs mention skill refs
- `tests/test_capabilities.py` or existing capability tests

Validation:

- absent/disabled policy reports metadata-only skill refs
- enabled policy reports live package-local skill loading when all referenced
  sources pass checks
- enabled policy reports missing/rejected status for source-loading failures
- docs describe opt-in package-local behavior and non-goals

## Test Strategy

Use only temporary package fixtures and fake model adapters. Do not read global
user skill directories and do not use network calls.

Core tests:

- package fixture with `skill-bundle/skills/demo/SKILL.md`
- node with `skill_refs: [demo]`
- policy disabled: no body loaded, current behavior preserved
- policy enabled: body injected into model messages
- runtime override `only`/`add`/`remove` changes effective source order
- traversal and symlink escape failures
- oversized and binary-looking file failures
- capability/status disabled/live/rejected states

## Risks

- Prompt-order regressions: keep skill bodies in the existing
  `skill_instructions` message lane.
- Accidental arbitrary file reads: v1 must reject external paths and treat
  `source_path` as provenance only.
- Trace leakage: raw bodies must not appear in trace metadata by default.
- Over-coupling validation and execution: resolver should be a small reusable
  module called by validation/preparation rather than ad hoc executor reads.

## Readiness

This plan is ready for implementation when `tasks.md` is accepted as the
execution checklist. Implementation should start at Slice 1 and commit each
slice independently.
