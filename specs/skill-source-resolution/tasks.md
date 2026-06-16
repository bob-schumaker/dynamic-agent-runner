# SKILL.md Source Resolution Tasks

## Metadata

- Feature slug: `skill-source-resolution`
- Spec: `specs/skill-source-resolution/spec.md`
- Plan: `specs/skill-source-resolution/plan.md`
- Status: prepared for implementation

## Slice 1: Policy and Data Model

- [ ] T1.1 Add a parsed `skill_source_resolution` execution-policy model with
      defaults for disabled source loading.
- [ ] T1.2 Validate policy shape for `enabled`, `allowed_sources`,
      `max_skill_bytes`, `max_node_skill_bytes`, `load_support_files`, and
      `prompt_role`.
- [ ] T1.3 Add resolver result/provenance dataclasses for skill id, source kind,
      package id, bundled path, byte count, content hash, trust classification,
      and redaction-safe diagnostics.
- [ ] T1.4 Add validation tests for omitted policy, disabled policy, valid
      package-bundle policy, unsupported sources, invalid byte limits, and
      unsupported support-file loading.
- [ ] T1.5 Run targeted validation:
      `poetry run pytest tests/test_validation.py -q`.

## Slice 2: Package-Local Resolver

- [ ] T2.1 Add `dynamic_agent_runner.skill_sources` with a package-local resolver
      that reads only `skills[*].bundled_path` under `skill_bundle_root`.
- [ ] T2.2 Ensure `source_path` remains provenance-only and never authorizes a
      host-file read in v1.
- [ ] T2.3 Fail closed for absolute paths, parent traversal, symlink escapes,
      missing files, non-files, unsupported encodings, binary-looking content,
      and per-skill size-limit violations.
- [ ] T2.4 Enforce per-node combined skill body size limits.
- [ ] T2.5 Keep support files validation-only; do not load support file content
      into prompts.
- [ ] T2.6 Add tests using temporary package fixtures for successful
      package-local loading and each failure mode.
- [ ] T2.7 Run targeted validation:
      `poetry run pytest tests/test_validation.py tests/test_artifacts.py -q`
      or the new targeted skill-source test file if created.

## Slice 3: Prompt Integration and Diagnostics

- [ ] T3.1 Wire resolved skill bodies into effective node behavior without
      mutating `LoadedAgentWorkflow`, `CompiledAgentWorkflow`, or package files.
- [ ] T3.2 Inject loaded bodies through the existing `skill_instructions` message
      lane in deterministic effective `skill_refs` order.
- [ ] T3.3 Preserve current inline `instructions` behavior when source loading is
      disabled or when a skill already provides inline instructions.
- [ ] T3.4 Apply runtime behavior overrides before source resolution so `only`,
      `add`, and `remove` control the loaded skill set.
- [ ] T3.5 Add redacted prepared-input or trace metadata for loaded, omitted,
      and rejected skill sources without raw body leakage.
- [ ] T3.6 Add fake-adapter executor tests proving prompt order:
      system/developer prompt, skill instructions, prepared context lanes, user
      prompt.
- [ ] T3.7 Add tests proving no model call occurs after a source-loading failure.
- [ ] T3.8 Run targeted validation:
      `poetry run pytest tests/test_executor.py tests/test_prompt_cache.py -q`.

## Slice 4: Capability Status and Documentation

- [ ] T4.1 Update capability/status reporting so disabled skill refs remain
      metadata-only.
- [ ] T4.2 Report live package-local source loading when policy is enabled and
      referenced bundled skill bodies pass checks.
- [ ] T4.3 Report missing/rejected skill-source diagnostics for enabled policy
      failures.
- [ ] T4.4 Update `README.md`, `specs/README.md`, and relevant `docs/files/`
      pages to describe opt-in package-local source loading and v1 non-goals.
- [ ] T4.5 Add capability/status tests for disabled, live, and rejected
      source-loading states.
- [ ] T4.6 Run targeted validation:
      `poetry run pytest tests/test_capabilities.py tests/test_validation.py -q`.

## Slice 5: Completion Evidence

- [ ] T5.1 Run the focused skill-source test set from Slices 1-4.
- [ ] T5.2 Run `poetry run pytest -q` unless the implementation slice explicitly
      scopes final validation narrower.
- [ ] T5.3 Run `pre-commit run --files ...` for all changed files.
- [ ] T5.4 Update `specs/README.md` completion wording if the v1 baseline is
      implemented.
- [ ] T5.5 Refresh `memory-bank/activeContext.md` and `memory-bank/progress.md`.
- [ ] T5.6 Commit implementation and memory-bank refresh separately if requested
      by the active workflow.

## Done Definition

- Source loading is opt-in and package-local only.
- Existing packages behave the same with the policy absent or disabled.
- Referenced bundled `SKILL.md` bodies inject deterministically when enabled.
- Unsafe paths, encodings, binary content, and size violations fail before model
  calls.
- Capability/status distinguishes metadata-only, live, and rejected states.
- Tests use fake adapters and temporary package fixtures only.
