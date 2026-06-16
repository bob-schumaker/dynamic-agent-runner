# SKILL.md Source Resolution Tasks

## Metadata

- Feature slug: `skill-source-resolution`
- Spec: `specs/skill-source-resolution/spec.md`
- Plan: `specs/skill-source-resolution/plan.md`
- Status: v1 implemented

## Slice 1: Policy and Data Model

- [x] T1.1 Add a parsed `skill_source_resolution` execution-policy model with
      defaults for disabled source loading.
- [x] T1.2 Validate policy shape for `enabled`, `allowed_sources`,
      `max_skill_bytes`, `max_node_skill_bytes`, `load_support_files`, and
      `prompt_role`.
- [x] T1.3 Add resolver result/provenance dataclasses for skill id, source kind,
      package id, bundled path, byte count, content hash, trust classification,
      and redaction-safe diagnostics.
- [x] T1.4 Add validation tests for omitted policy, disabled policy, valid
      package-bundle policy, unsupported sources, invalid byte limits, and
      unsupported support-file loading.
- [x] T1.5 Run targeted validation:
      `poetry run pytest tests/test_validation.py -q`.

## Slice 2: Package-Local Resolver

- [x] T2.1 Add `dynamic_agent_runner.skill_sources` with a package-local resolver
      that reads only `skills[*].bundled_path` under `skill_bundle_root`.
- [x] T2.2 Ensure `source_path` remains provenance-only and never authorizes a
      host-file read in v1.
- [x] T2.3 Fail closed for absolute paths, parent traversal, symlink escapes,
      missing files, non-files, unsupported encodings, binary-looking content,
      and per-skill size-limit violations.
- [x] T2.4 Enforce per-node combined skill body size limits.
- [x] T2.5 Keep support files validation-only; do not load support file content
      into prompts.
- [x] T2.6 Add tests using temporary package fixtures for successful
      package-local loading and each failure mode.
- [x] T2.7 Run targeted validation:
      `poetry run pytest tests/test_validation.py tests/test_artifacts.py -q`
      or the new targeted skill-source test file if created.

## Slice 3: Prompt Integration and Diagnostics

- [x] T3.1 Wire resolved skill bodies into effective node behavior without
      mutating `LoadedAgentWorkflow`, `CompiledAgentWorkflow`, or package files.
- [x] T3.2 Inject loaded bodies through the existing `skill_instructions` message
      lane in deterministic effective `skill_refs` order.
- [x] T3.3 Preserve current inline `instructions` behavior when source loading is
      disabled or when a skill already provides inline instructions.
- [x] T3.4 Apply runtime behavior overrides before source resolution so `only`,
      `add`, and `remove` control the loaded skill set.
- [x] T3.5 Add redacted prepared-input or trace metadata for loaded, omitted,
      and rejected skill sources without raw body leakage.
- [x] T3.6 Add fake-adapter executor tests proving prompt order:
      system/developer prompt, skill instructions, prepared context lanes, user
      prompt.
- [x] T3.7 Add tests proving no model call occurs after a source-loading failure.
- [x] T3.8 Run targeted validation:
      `poetry run pytest tests/test_executor.py tests/test_prompt_cache.py -q`.

## Slice 4: Capability Status and Documentation

- [x] T4.1 Update capability/status reporting so disabled skill refs remain
      metadata-only.
- [x] T4.2 Report live package-local source loading when policy is enabled and
      referenced bundled skill bodies pass checks.
- [x] T4.3 Report missing/rejected skill-source diagnostics for enabled policy
      failures.
- [x] T4.4 Update `README.md`, `specs/README.md`, and relevant `docs/files/`
      pages to describe opt-in package-local source loading and v1 non-goals.
- [x] T4.5 Add capability/status tests for disabled, live, and rejected
      source-loading states.
- [x] T4.6 Run targeted validation:
      `poetry run pytest tests/test_capabilities.py tests/test_validation.py -q`.

## Slice 5: Completion Evidence

- [x] T5.1 Run the focused skill-source test set from Slices 1-4.
- [x] T5.2 Run `poetry run pytest -q` unless the implementation slice explicitly
      scopes final validation narrower.
- [x] T5.3 Run `pre-commit run --files ...` for all changed files.
- [x] T5.4 Update `specs/README.md` completion wording if the v1 baseline is
      implemented.
- [ ] T5.5 Refresh `memory-bank/activeContext.md` and `memory-bank/progress.md`.
- [x] T5.6 Commit implementation and memory-bank refresh separately if requested
      by the active workflow.

## Done Definition

- Source loading is opt-in and package-local only.
- Existing packages behave the same with the policy absent or disabled.
- Referenced bundled `SKILL.md` bodies inject deterministically when enabled.
- Unsafe paths, encodings, binary content, and size violations fail before model
  calls.
- Capability/status distinguishes metadata-only, live, and rejected states.
- Tests use fake adapters and temporary package fixtures only.
