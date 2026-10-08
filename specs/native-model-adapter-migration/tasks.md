# Native Model Adapter Migration Tasks

Status: Complete

## Prerequisites

- Spec: `spec.md` — approved
- Plan: `plan.md` — approved
- Data model: none
- Contracts: `specs/external-model-adapter-protocol/spec.md`

## Cited inputs

- `src/dynamic_agent_runner/external_adapter.py` — v1 descriptor, façade,
  bounded dispatch/health, request context, and response normalization —
  inspected
- `src/dynamic_agent_runner/apple_foundation_models.py` — Apple async adapter,
  aliases, availability, schema, and native callback bridge — inspected
- `src/dynamic_agent_runner/local_models.py` — direct llama.cpp adapter,
  material identity, configuration fingerprint, and lifecycle — inspected
- `src/dynamic_agent_runner/mlx_models.py` — MLX sync/async adapters and
  versioned `MLXToolCodec` — inspected
- `tests/test_workflow_model_support_matrix.py` — support classifier and
  receipt assertions — inspected

## Task list

### Slice 1 — Conformance RED tests and fixtures

- [x] T1.1 [tests, characterization] Lock the existing façade health and mode
  behavior with controlled fakes in `tests/test_native_model_adapter_migration.py`.
  - Spec: health, execution-mode, and cancellation requirements
  - Plan: M1; Verification Strategy
  - Files/components: `tests/test_native_model_adapter_migration.py`,
    `ExternalModelAdapterFacade`
  - Depends on: none
  - Validation:
    `poetry run pytest tests/test_native_model_adapter_migration.py -q`
  - Evidence: current façade health timeout, worker saturation, late-probe,
    sync-dispatch, async-dispatch, and worker-offloaded sync-generation
    behavior is captured without live providers.

- [x] T1.2 [tests, RED] Add reusable fake Apple, llama.cpp, and MLX native
  adapters plus a parity projection that compares canonical content, ordered
  normalized tool calls, response-format behavior, and package-owned error
  class/code while excluding raw payloads and unstable IDs.
  - Spec: parity and fake-only validation requirements
  - Plan: M1; Architecture and data flow
  - Files/components: `tests/test_native_model_adapter_migration.py`
  - Depends on: T1.1
  - Validation: focused test command above; expected RED for absent wrappers
  - Evidence: provider-independent fixtures and a stable comparison oracle.

- [x] T1.3 [tests, RED] Define the Apple wrapper contract and failing tests for
  `create_apple_foundation_external_adapter`, including exact-one-alias
  admission, async-only mode, derived identity, structured-output capability,
  omitted callback-only tools, health, and unavailable-SDK behavior.
  - Spec: Apple provider requirements and capability matrix
  - Plan: M1, M3
  - Files/components: `tests/test_native_model_adapter_migration.py`,
    `AppleFoundationModelConfig`, `AppleFoundationModelAsyncAdapter`
  - Depends on: T1.2
  - Validation: focused test command; expected RED
  - Evidence: multi-alias rejection and positive/negative Apple capability
    cases are executable before implementation.

- [x] T1.4 [tests, RED] Define the llama.cpp wrapper contract and failing
  tests for `create_llama_cpp_external_adapter`, including material/configuration
  identity, sync mode, health, memory-fit/lifecycle preservation, and supported
  versus denied structured-output/tool capability.
  - Spec: llama.cpp provider requirements and capability matrix
  - Plan: M1, M4
  - Files/components: `tests/test_native_model_adapter_migration.py`,
    `LlamaCppLocalModelAdapter`
  - Depends on: T1.2
  - Validation: focused test command; expected RED
  - Evidence: exact identity and capability assertions use a fake native
    adapter and never load llama.cpp.

- [x] T1.5 [tests, RED] Define the MLX sync and async wrapper contracts and
  failing tests for `create_mlx_external_adapter` and
  `create_mlx_async_external_adapter`, including resolved identity, mode
  matching, codec-gated tools, text-only denial, health, late sync results,
  and async cancellation.
  - Spec: MLX provider requirements and capability matrix
  - Plan: M1, M5
  - Files/components: `tests/test_native_model_adapter_migration.py`,
    `MLXLocalModelAdapter`, `AsyncMLXLocalModelAdapter`, `MLXToolCodec`
  - Depends on: T1.2
  - Validation: focused test command; expected RED
  - Evidence: both variants and codec/no-codec paths are covered.

- [x] T1.6 [tests, RED] Add identity-mismatch and capability-overclaim tests for
  every factory, proving callers cannot supply an unrelated model identity or
  advertise unsupported structured output/tools.
  - Spec: identity and capability fail-closed rules
  - Plan: M1; Risks and mitigations
  - Files/components: `tests/test_native_model_adapter_migration.py`
  - Depends on: T1.3, T1.4, T1.5
  - Validation: focused test command; expected RED
  - Evidence: mismatched aliases/material/configuration and overclaim attempts
    fail before native dispatch.

Checkpoint: characterization tests pass; all provider-wrapper RED tests fail
only because the wrappers/factories are absent.

### Slice 2 — Shared protocol mechanics and façade ownership

- [x] T2.1 [implementation] Add minimal generic descriptor, canonical identity,
  timeout validation, and redacted native-error helpers in
  `src/dynamic_agent_runner/external_adapter.py`.
  - Spec: common contract and identity/health rules
  - Plan: M2; Work-package WP2
  - Files/components: `external_adapter.py`
  - Depends on: T1.6
  - Validation:
    `poetry run pytest tests/test_external_adapter_protocol.py
    tests/test_native_model_adapter_migration.py -q`
  - Evidence: helpers preserve v1 digest computation and reject invalid timeout
    or non-secret identity inputs.

- [x] T2.2 [implementation] Make the façade health-worker contract explicit
  and non-recursive for sync dispatch, async dispatch, and worker-offloaded
  sync generation. Enforce `(0, 120]` health timeout, saturation refusal, and
  late-probe handling without changing the protocol wire ID.
  - Spec: bounded health and cancellation rules
  - Plan: M2; Architecture and data flow
  - Files/components: `external_adapter.py`,
    `tests/test_native_model_adapter_migration.py`
  - Depends on: T1.1, T2.1
  - Validation: focused migration and external-protocol tests
  - Evidence: blocking fakes prove bounded behavior, no recursive worker
    scheduling, no late success, and no retry/fallback.

- [x] T2.3 [implementation] Add shared mode/context checks for exact v1
  `create_response` behavior, including async-only rejection from sync dispatch,
  request-context propagation, deadline checks, and cancellation translation.
  - Spec: common contract
  - Plan: M2
  - Files/components: `external_adapter.py`
  - Depends on: T2.1, T2.2
  - Validation: focused migration test command
  - Evidence: sync and async façade paths reject incompatible variants before
    native invocation.

- [x] T2.4 [tests, GREEN] Rerun the shared contract suite and confirm existing
  installed-registry exact tuple resolution and OpenAI-compatible external
  adapter behavior remain unchanged.
  - Spec: non-goals and installed-adapter compatibility
  - Plan: M2 exit gate
  - Files/components: `tests/test_external_adapter_protocol.py`,
    `tests/test_external_adapter_registry.py`,
    `tests/test_native_model_adapter_migration.py`
  - Depends on: T2.1, T2.2, T2.3
  - Validation:
    `poetry run pytest tests/test_external_adapter_protocol.py
    tests/test_external_adapter_registry.py
    tests/test_native_model_adapter_migration.py -q`
  - Evidence: shared mechanics pass and no existing external-adapter regression
    appears.

Checkpoint: shared mechanics are green; provider work can proceed independently.

### Slice 3 — Apple wrapper

- [x] T3.1 [implementation] Implement `create_apple_foundation_external_adapter`
  beside the existing Apple adapter. Accept one resolved alias, derive identity
  and capabilities from the native binding, preserve Apple preflight, and return
  an async-only v1 wrapper without callback objects.
  - Spec: Apple provider requirements
  - Plan: M3; Provider implementation boundaries
  - Files/components: `apple_foundation_models.py`
  - Depends on: T2.4
  - Validation: focused migration tests
  - Evidence: wrapper never reloads SDK/materials or receives a handler,
    registry, approval object, or callback.

- [x] T3.2 [tests, GREEN] Make Apple identity, health, structured-output,
  callback-tool denial, cancellation, and unavailable-SDK tests pass with fakes.
  - Spec: Apple acceptance criteria and capability matrix
  - Plan: M3 exit gate
  - Files/components: `tests/test_native_model_adapter_migration.py`,
    `tests/test_apple_foundation_models.py`
  - Depends on: T3.1
  - Validation:
    `poetry run pytest tests/test_native_model_adapter_migration.py
    tests/test_apple_foundation_models.py -q`
  - Evidence: all advertised Apple capabilities have positive tests and omitted
    callback-only capabilities have denial tests.

### Slice 4 — Direct llama.cpp wrapper

- [x] T4.1 [implementation] Implement `create_llama_cpp_external_adapter`
  beside the direct llama.cpp adapter. Derive canonical identity from prepared
  material/configuration, preserve memory-fit/loading/cleanup, and expose only
  proven chat/template capabilities.
  - Spec: llama.cpp provider requirements
  - Plan: M4; Provider implementation boundaries
  - Files/components: `local_models.py`
  - Depends on: T2.4
  - Validation: focused migration tests
  - Evidence: wrapper delegates to the existing native lifecycle and does not
    introduce a second runtime.

- [x] T4.2 [tests, GREEN] Make llama.cpp identity, health, capability,
  blocking-generation, late-result, cleanup, and parity tests pass with fakes.
  - Spec: llama.cpp acceptance criteria
  - Plan: M4 exit gate
  - Files/components: `tests/test_native_model_adapter_migration.py`,
    `tests/test_local_models.py`
  - Depends on: T4.1
  - Validation:
    `poetry run pytest tests/test_native_model_adapter_migration.py
    tests/test_local_models.py -q`
  - Evidence: sync wrapper works through existing async façade offload and late
    native results are discarded.

### Slice 5 — MLX wrappers

- [x] T5.1 [implementation] Implement `create_mlx_external_adapter` and
  `create_mlx_async_external_adapter` beside the existing MLX adapters. Derive
  identity/capabilities from resolved native material and gate tools on the
  exact versioned `MLXToolCodec`.
  - Spec: MLX provider requirements
  - Plan: M5; Provider implementation boundaries
  - Files/components: `mlx_models.py`
  - Depends on: T2.4
  - Validation: focused migration tests
  - Evidence: sync and async wrappers preserve caller-controlled material and
    runtime ownership.

- [x] T5.2 [tests, GREEN] Make MLX mode, identity, health, codec-gated tools,
  text-only denial, structured-output, late-result, cancellation, and parity
  tests pass with fakes.
  - Spec: MLX acceptance criteria and capability matrix
  - Plan: M5 exit gate
  - Files/components: `tests/test_native_model_adapter_migration.py`,
    `tests/test_mlx_models.py`
  - Depends on: T5.1
  - Validation:
    `poetry run pytest tests/test_native_model_adapter_migration.py
    tests/test_mlx_models.py -q`
  - Evidence: both variants pass without a live MLX runtime.

Checkpoint: Apple, llama.cpp, and MLX wrappers independently pass their
provider conformance slices.

### Slice 6 — Opt-in integration and support evidence

- [x] T6.1 [implementation] Export the four approved wrapper factories from
  `src/dynamic_agent_runner/__init__.py` without exporting native transport
  internals or secrets.
  - Spec: public BYOM seam
  - Plan: M6; Scope and ownership
  - Files/components: `src/dynamic_agent_runner/__init__.py`
  - Depends on: T3.2, T4.2, T5.2
  - Validation: `poetry run pytest tests/test_import.py -q`
  - Evidence: public imports work and existing native factories remain present.

- [x] T6.2 [tests, GREEN] Add three text-adapter candidate rows to
  `tests/fixtures/workflow-model-support-matrix/native-model-adapter-migration.json`
  and classifier assertions in `tests/test_workflow_model_support_matrix.py`.
  Record row ownership and non-transferable identity fields in
  `specs/workflow-model-support-matrix/discovery.md`.
  - Spec: support-matrix coverage requirement
  - Plan: M6; Verification Strategy
  - Files/components: fixture JSON, matrix test, matrix discovery record
  - Depends on: T3.2, T4.2, T5.2
  - Validation: `poetry run pytest tests/test_workflow_model_support_matrix.py -q`
  - Evidence: rows classify exact adapter/material/ABI identity and reject
    stale or transferable evidence.

- [x] T6.3 [docs] Document caller-owned BYOM construction, native lifecycle,
  capability omissions, and deferred registry/default-path migration in
  `README.md` without changing existing provider instructions.
  - Spec: migration and removal gates
  - Plan: M6
  - Files/components: `README.md`
  - Depends on: T6.1
  - Validation: documentation hook or `git diff --check`
  - Evidence: usage example and explicit out-of-scope boundaries are present.

### Slice 7 — Validation and handoff

- [x] T7.1 [validation] Record focused migration evidence in
  `specs/native-model-adapter-migration/validation.md`, including RED/GREEN
  checkpoints, provider capability results, health behavior, and deferred
  native-only capabilities.
  - Spec: acceptance criteria
  - Plan: M7
  - Files/components: `validation.md`
  - Depends on: T6.2, T6.3
  - Validation: inspect the traceability matrix and command results
  - Evidence: every acceptance criterion maps to a test or explicit evidence.

- [x] T7.2 [validation] Run affected provider and protocol regressions:
  `poetry run pytest tests/test_external_adapter_protocol.py
  tests/test_external_adapter_registry.py tests/test_apple_foundation_models.py
  tests/test_local_models.py tests/test_mlx_models.py
  tests/test_workflow_model_support_matrix.py -q`.
  - Spec: regression and fake-only requirements
  - Plan: Verification Strategy
  - Files/components: affected test suites
  - Depends on: T7.1
  - Validation: exact command above
  - Evidence: all affected tests pass without live provider calls.

- [x] T7.3 [validation] Run repository gates: `poetry run pytest -q`,
  `poetry run ruff check src tests`, and `poetry build`.
  - Spec: final acceptance and non-goals
  - Plan: M7 exit gate
  - Files/components: repository-wide
  - Depends on: T7.2
  - Validation: exact commands above
  - Evidence: full suite, Ruff, and package build are green.

- [x] T7.4 [review] Perform final spec/plan/tasks/code/validation drift review
  and record any provider capability that remains native-only before declaring
  the migration slice complete.
  - Spec: migration and removal gates
  - Plan: M7; Risks and mitigations
  - Files/components: spec, plan, tasks, implementation, validation
  - Depends on: T7.3
  - Validation: `git diff --check` plus artifact inspection
  - Evidence: no undocumented registry/default-path migration or live-test
    dependency remains.

## Checkpoints

- **C1 — RED boundary:** characterization tests pass and all provider wrapper
  tests fail at the missing-wrapper boundary.
- **C2 — Shared mechanics:** descriptor, health, mode, context, and redaction
  tests pass; installed adapter behavior is unchanged.
- **C3 — Provider conformance:** Apple, llama.cpp, and MLX wrappers each pass
  their own identity, health, capability, cancellation, and parity tests.
- **C4 — Opt-in surface:** exports, support-matrix rows, and documentation pass
  without changing default routing.
- **C5 — Handoff:** affected regressions, full suite, Ruff, build, and drift
  review are green.

## Validation commands

- `poetry run pytest tests/test_native_model_adapter_migration.py -q`

- ```text
  poetry run pytest tests/test_external_adapter_protocol.py \
    tests/test_external_adapter_registry.py \
    tests/test_apple_foundation_models.py tests/test_local_models.py \
    tests/test_mlx_models.py tests/test_workflow_model_support_matrix.py -q
  ```

- `poetry run pytest -q`
- `poetry run ruff check src tests`
- `poetry build`

## Boundary notes

- Provider wrappers own translation only; native loading, materials, lifecycle,
  and domain behavior remain provider-owned.
- The façade owns generic admission, bounded health, cancellation, output
  validation, tracing, tool re-entry, and removal.
- No task permits registry configuration binding, CLI install/remove, service
  startup/downloads, embeddings, multimodal output, streaming, or live tests.
