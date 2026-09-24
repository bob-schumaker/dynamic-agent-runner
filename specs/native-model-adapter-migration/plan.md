# Native Model Adapter Migration Implementation Plan

Status: Approved

## Spec trace

- Spec: `specs/native-model-adapter-migration/spec.md`
- Protocol authority: `specs/external-model-adapter-protocol/spec.md`
- Existing provider authorities:
  - `specs/apple-foundation-model-adapter/spec.md`
  - `specs/llama-cpp-local-model/spec.md`
  - `specs/mlx-local-model-adapter/spec.md`
  - `specs/mlx-local-model-tool-use/spec.md`
- Repository guardrails: `AGENTS.md` and `AGENTS.local.md`
- Planning mode: guided; implementation must not begin until this plan and its
  later task breakdown are approved

## Objective

Provide caller-constructed BYOM wrappers for Apple Foundation Models, direct
llama.cpp, and MLX text generation that implement
`DARExternalAdapterProtocol`. Preserve each provider's native loading,
material, template, resource, and runtime behavior. Add no registry or default
provider migration in this slice.

## Current state

- `external_adapter.py` owns the v1 descriptor, health, façade, bounded health
  and dispatch workers, request context, response normalization, redaction,
  and installed-adapter admission.
- `apple_foundation_models.py` exposes an async OpenAI-compatible client adapter
  with Apple availability, structured-output, and native tool-bridge behavior.
- `local_models.py` exposes direct llama.cpp generation and embedding adapters,
  including material identity, configuration fingerprints, memory-fit, and
  local lifecycle behavior.
- `mlx_models.py` exposes sync and async text adapters and the versioned
  `MLXToolCodec` seam.
- The receiver registry can resolve an installed adapter by an exact identity
  tuple, while direct BYOM callers use construction-time immutable wrappers.
- Existing provider factories and executor routing must remain unchanged until
  parity evidence and an explicit compatibility decision authorize migration.

## Scope and ownership

### In scope

1. A shared conformance test vocabulary and fake-native fixtures.
2. Caller-owned BYOM factories for Apple, llama.cpp, and MLX generation.
3. Deterministic descriptor identity and capability projection.
4. Bounded, redacted provider health probes using the existing façade worker.
5. Exact v1 `create_response` sync/async mode handling and cancellation rules.
6. Layered structured-output and tool-call behavior with no callback leakage.
7. Package exports, support-matrix rows, and migration documentation.

### Out of scope

- Changes to `DARExternalAdapterProtocol` or its wire ID.
- Receiver-owned configuration binding for native providers.
- Removal or replacement of native provider factories.
- Embedding, multimodal, streaming, persistent sessions, or native callbacks.
- Model downloads, endpoint discovery, arbitrary model-directory scanning, or
  process management.
- Live Apple, llama.cpp, MLX, Metal, or Hugging Face calls in ordinary tests.

## Architecture and data flow

```text
caller-resolved native config/material
              |
              v
provider BYOM factory
              |
              v
immutable v1 descriptor + native wrapper
              |
              v
ExternalModelAdapterFacade
  - descriptor admission
  - bounded health
  - deadline/cancellation
  - response validation
  - tool re-entry
              |
              v
existing DAR executor/model path
```

The wrapper is an anti-corruption layer, not a second provider runtime. It
captures the resolved native binding at construction. Native configuration
identity is encoded into `canonical_model_id` before the existing descriptor
digest is computed. A changed binding creates a new wrapper and descriptor.

The façade remains the only owner of generic admission, JSON-schema result
validation, tracing, tool approval/re-entry, and removal. Provider-native
schema checks may run before dispatch. Wrappers may normalize provider tool
calls, but never receive handlers, registries, approval objects, or callbacks.

The existing bounded health worker is used for zero-argument provider health.
Each wrapper validates a non-secret `health_timeout_seconds` in `(0, 120]`.
Worker saturation and late blocking probes fail closed as unavailable; late
native work is not retried or treated as a successful result.

## Factory contracts

The public factory names are fixed for task planning and must preserve one
shared shape:

```python
create_<provider>_external_adapter(
    native_adapter,
    *,
    adapter_id: str,
    health_timeout_seconds: float = 30.0,
) -> DARExternalAdapterProtocol
```

The concrete names are `create_apple_foundation_external_adapter`,
`create_llama_cpp_external_adapter`, `create_mlx_external_adapter`, and
`create_mlx_async_external_adapter`. They live beside their native provider
adapters in `apple_foundation_models.py`, `local_models.py`, and
`mlx_models.py`; shared protocol mechanics remain in `external_adapter.py`.

The Apple factory accepts the already-constructed async Apple adapter and
returns an async-only wrapper. The llama.cpp factory accepts the already-
constructed direct local adapter and returns a sync wrapper. MLX exposes one
sync and one async factory accepting the corresponding already-constructed
native adapter. Each factory derives the single model alias, canonical model
identity, and capability set from that native binding; no public override can
add capabilities or supply an unrelated identity. A provider-specific alias
argument, if needed for a one-alias binding, must be checked against the native
adapter and rejected on mismatch. Factories never reload materials, download
models, start processes, or take ownership of native lifecycle. Test-only
injected health and response probes may replace the native calls, but are not
public runtime configuration.

## Provider implementation boundaries

### Apple Foundation Models

Add an async-only external wrapper around the existing Apple client path. The
factory accepts exactly one resolved Apple model alias; a multi-alias
`AppleFoundationModelConfig` is rejected for this wrapper rather than silently
choosing an alias. Callers needing multiple aliases construct one immutable
wrapper per alias.

The descriptor advertises `execution_modes={"async"}`. Preserve macOS/SDK/model
availability and Apple pre-dispatch schema checks. Omit `tool_calling` unless
the wrapper can return normalized `ModelToolCall` values without the native
callback bridge; the existing callback path remains native-only.

### Direct llama.cpp

Add a sync-first wrapper around the existing direct adapter. The descriptor
binds the prepared material-lock digest and configuration fingerprint. Preserve
memory-fit, loading, cleanup, local policy, and chat/template capability
checks. Async workflow use is the existing façade worker offload, not a new
pseudo-async native runtime.

### MLX

Add matching sync and async wrappers around the existing MLX adapters. The
descriptor binds resolved model/material/configuration identity. Plain text is
the default. Tool calling is advertised only for the exact versioned
`MLXToolCodec`; arbitrary MLX models remain text-only.

## Milestones and work packages

### M1 — Conformance RED tests and shared fixtures

Dependencies: none.

Deliverables:

- characterization tests for the existing façade health worker and dispatch
  mode behavior;
- genuinely failing RED tests for each absent provider BYOM factory,
  descriptor/parity path, identity derivation, identity mismatch, and
  capability-overclaim rejection;
- fake Apple, llama.cpp, and MLX native implementations;
- a parity projection that compares canonical content, ordered normalized tool
  calls, response-format behavior, and package-owned error class/code while
  excluding raw payloads and unstable IDs;
- positive and negative tests for every advertised capability, plus denial
  tests for intentionally omitted or conditional capabilities.

Exit gate: characterization tests pass unchanged, while provider wrapper RED
tests fail at the absent-wrapper boundary and identify each public contract
before provider implementation begins.

### M2 — Shared wrapper/admission support

Dependencies: M1.

Deliverables:

- small shared helpers for v1 descriptor construction, canonical identity
  derivation, health timeout validation, and native error redaction;
- BYOM factory shape and immutable construction-time binding;
- sync/async `create_response` mode checks and context propagation;
- explicit façade health-worker implementation/maintenance in
  `external_adapter.py`, including non-recursive ordering for sync dispatch,
  async dispatch, and worker-offloaded sync generation;
- focused façade tests proving no callback/handler leakage and exact
  installed-registry tuple resolution remains unchanged.
- explicit health-offload tests for sync dispatch, async dispatch, and
  worker-offloaded sync generation, including timeout, saturation, and late
  probe behavior; async-only adapters must never be invoked through sync
  dispatch.

Exit gate: shared contract tests pass with synthetic providers and existing
OpenAI-compatible external adapter tests remain green.

### M3 — Apple wrapper

Dependencies: M2.

Deliverables:

- async-only Apple protocol wrapper and factory;
- Apple identity derivation and bounded health mapping;
- structured-output preflight and capability omission for callback-only tools;
- positive structured-output and negative tool-call capability tests, plus
  parity, deadline, cancellation, and unavailable-SDK tests using fakes.

Exit gate: Apple wrapper passes all advertised capability tests without a live
Apple SDK or callback handler.

### M4 — Direct llama.cpp wrapper

Dependencies: M2.

Deliverables:

- sync llama.cpp protocol wrapper and factory;
- material/configuration identity binding and health mapping;
- chat/template capability projection for structured output and tools;
- positive/negative capability tests, blocking-generation, late-result,
  memory-fit, cleanup, and parity tests.

Exit gate: wrapper passes the conformance suite and proves async workflow use
through existing façade offload without adding a second native runtime.

### M5 — MLX wrappers

Dependencies: M2; MLX tool codec work must remain available for tool-enabled
cells.

Deliverables:

- sync and async MLX protocol wrappers and factories;
- resolved material/configuration identity and bounded health mapping;
- codec-gated tool capability and normalized tool-call tests;
- text-only negative tests for unsupported model/tokenizer combinations;
- positive/negative structured-output tests, sync late-result, and async
  cancellation tests.

Exit gate: both variants pass the mode and capability matrix with no live MLX
runtime.

### M6 — Opt-in integration and documentation

Dependencies: M3, M4, and M5.

Deliverables:

- package-root exports for approved wrapper factories/configuration types;
- support-matrix candidate rows for the three text adapters in
  `tests/fixtures/workflow-model-support-matrix/native-model-adapter-migration.json`,
  with row ownership recorded in
  `specs/workflow-model-support-matrix/discovery.md`;
- README/provider documentation describing caller-owned BYOM construction,
  native lifecycle ownership, and deferred registry/default-path migration;
- explicit proof that existing native factories remain selectable.

Exit gate: import, documentation, and support-matrix checks pass with no
runtime default-path change. The matrix evidence is exercised by
`tests/test_workflow_model_support_matrix.py`.

### M7 — Validation and handoff

Dependencies: M6.

Deliverables:

- focused validation record for every milestone and provider;
- full pytest, Ruff, and package-build evidence;
- spec/plan/task consistency review and drift check;
- implementation handoff notes identifying any provider capability that remains
  native-only.

Exit gate: all required commands pass, no live model call is required, and the
legacy OpenAI/LiteLLM/provider regression floor remains green.

## Work-package dependency map

| Package | Responsibility | Primary touch points | Depends on |
| --- | --- | --- | --- |
| WP1 | RED conformance fixtures and parity projection | `tests/`, new migration test module | none |
| WP2 | Shared identity, descriptor, health, and mode helpers | `src/dynamic_agent_runner/external_adapter.py`; provider identity remains in provider modules | WP1 |
| WP3 | Apple wrapper | `apple_foundation_models.py`, Apple tests | WP2 |
| WP4 | llama.cpp wrapper | `local_models.py`, local-model tests | WP2 |
| WP5 | MLX sync/async wrappers | `mlx_models.py`, MLX tests | WP2 |
| WP6 | Exports, matrix, and docs | `__init__.py`, README, support specs | WP3–WP5 |
| WP7 | Validation and drift evidence | migration `validation.md` when created | WP6 |

WP1 owns all RED tests. WP2 owns only reusable protocol mechanics, not provider
semantics. WP3–WP5 own their provider wrappers independently and must not
change one another's native loading paths. WP6 and WP7 are sequential release
gates.

## Verification strategy

| Requirement | Evidence | Command |
| --- | --- | --- |
| Descriptor identity and digest | focused fake-provider tests | `poetry run pytest tests/test_native_model_adapter_migration.py -q` |
| Health timeout, saturation, and late probes | blocking-health fakes | same focused test command |
| Sync/async mode and cancellation | mode-specific fake tests | same focused test command |
| Capability matrix and tool boundary | positive/negative provider fixtures | same focused test command |
| Support-matrix rows and identity evidence | migration fixture plus classifier assertions | `poetry run pytest tests/test_workflow_model_support_matrix.py -q` |
| Existing provider behavior | provider-specific regression suites | `poetry run pytest tests/test_apple_foundation_models.py tests/test_local_models.py tests/test_mlx_models.py -q` |
| Import and public API | package import tests | `poetry run pytest tests/test_import.py -q` |
| Repository regression | full suite | `poetry run pytest -q` |
| Static quality | Ruff | `poetry run ruff check src tests` |
| Package integrity | build | `poetry build` |

All model/provider tests use controlled fakes. Any platform-specific live
acceptance remains an explicit later gate and is not part of ordinary CI.

## Risks and mitigations

- **Capability overclaim:** immutable factory-time capability matrix and
  positive/negative tests prevent request-time capability drift.
- **Native identity drift:** canonical model identity includes the resolved
  non-secret binding; installed resolution retains exact tuple checks.
- **Blocking native work:** façade worker semantics explicitly discard late
  results and avoid retries or fallback.
- **Apple callback leakage:** Apple tool calling remains omitted until callback-
  free normalized tool results are proven.
- **Provider coupling:** wrappers stay in provider modules; shared helpers are
  limited to protocol mechanics.
- **Regression risk:** native factories and default routing remain unchanged
  until named parity/provenance evidence exists.
