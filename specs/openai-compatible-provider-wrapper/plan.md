# OpenAI-Compatible Provider Wrapper Implementation Plan

## Goal

Implement a repository-owned provider/client wrapper around the official
`openai` SDK so the runtime can use OpenAI-compatible endpoints through a stable
internal facade, while preserving existing adapter routing semantics and the
hosted OpenAI default path.

## Source Artifacts

- `specs/openai-compatible-provider-wrapper/spec.md` — source of truth for this
  refactor.
- `src/dynamic_agent_runner/openai_client.py` — current adapter, request, and
  normalization implementation.
- `src/dynamic_agent_runner/executor.py` — adapter selection and model call site.
- `src/dynamic_agent_runner/__init__.py` — public exports.
- `tests/test_openai_client.py` — primary validation surface for this refactor.
- `tests/test_executor.py` — secondary validation surface if adapter metadata or
  construction semantics change.
- `specs/llama-cpp-graph-mutation/spec.md` — related future local-model design
  direction that should keep using the adapter contract rather than a parallel
  runtime family.

## Current Repository State

- The runtime already exposes `OpenAIClientAdapter` and
  `AsyncOpenAIClientAdapter` as the model-execution boundary.
- `executor.py` already depends on those adapters rather than importing raw SDK
  client classes, which means the remaining work is now focused on tightening
  adapter-level use of the provider seam inside `openai_client.py`.
- `openai_client.py` now defines repository-owned provider/configuration seams
  (`OpenAIProviderConfig`, `OpenAIClientProvider`,
  `AsyncOpenAIClientProvider`) and SDK-backed default provider wrappers
  (`SDKBackedOpenAIClientProvider`, `SDKBackedAsyncOpenAIClientProvider`).
- The default client factories now route through provider-backed construction and
  support `base_url` plus optional `api_key`.
- `OpenAIClientAdapter` and `AsyncOpenAIClientAdapter` now lazily resolve their
  default clients through the default provider facades as well, so the adapter
  layer consistently depends on the provider seam for both injected-provider and
  default-construction paths while preserving `models` / `is_local` executor
  routing semantics.
- Request construction and response normalization already live in repository code
  and should remain repository-owned after the refactor.

## Current Implementation Status

- **Slice 1** is complete in commit `99e225f`
  (`feat(openai-client): add provider facade seam`).
- **Slice 2** is complete in commit `282b93d`
  (`feat(openai-client): isolate sdk-backed provider defaults`).
- **Slice 3** is complete in commit `bc1ce39`
  (`feat(openai-client): route default adapters through providers`).
- Slice 3 validation passed with:
  - `poetry run pytest tests/test_openai_client.py -q` (`22 passed`)
  - `poetry run pytest tests/test_executor.py -q` (`49 passed`)
  - focused `pre-commit run --files src/dynamic_agent_runner/openai_client.py`
    `tests/test_openai_client.py`
- The next planned implementation step is **Slice 4 — Preserve repository-owned
  request and normalization logic**.

## Architectural Decision

### Chosen approach

Use **composition** with a repository-owned facade and SDK-backed implementation,
not subclassing of `openai.OpenAI` or `openai.AsyncOpenAI`.

### Why composition is preferred

- It isolates the runtime from SDK constructor and inheritance details.
- It keeps sync and async transport paths explicit.
- It makes fake-client testing easier.
- It supports generic OpenAI-compatible endpoints without inventing a new model
  execution family.

### Why subclassing is rejected

- SDK subclassing would still couple the runtime to vendor-specific inheritance
  and constructor behavior.
- Sync and async SDK variants would still need separate inheritance trees.
- It would provide weaker isolation than a repository-owned wrapper/facade.

## Target Architecture

### Layer 1 — Runtime adapter layer

Keep the existing runtime adapter concept and its executor-facing metadata:

- `OpenAIClientAdapter`
- `AsyncOpenAIClientAdapter`
- `models`
- `is_local`

This layer continues to own:

- request dispatch entry points (`create_response(...)`)
- adapter metadata used by executor routing
- runtime-facing error translation to `ModelExecutionError`

This layer should not need to know whether the underlying transport is hosted
OpenAI or an OpenAI-compatible endpoint.

### Layer 2 — Repository-owned provider/client facade

Introduce or tighten repository-owned sync and async wrapper protocols or
facade classes that represent the minimum capability the adapter needs.

This layer should own:

- provider configuration surface such as `base_url` and optional `api_key`
- lazy construction behavior for default SDK-backed clients
- a stable internal contract that can be implemented by both the official SDK
  wrapper and fake test clients

Concrete naming may vary during implementation, but the abstraction should read
as repository-owned rather than vendor-owned.

### Layer 3 — SDK-backed implementation layer

Keep the actual `openai` package import and `OpenAI` / `AsyncOpenAI`
construction inside the SDK-backed wrapper implementation.

This layer should own:

- importing `openai`
- constructing SDK clients
- applying `base_url` and optional `api_key`
- exposing the minimal repo-owned facade expected by Layer 2

## Proposed Implementation Shape

### `openai_client.py`

Refactor `src/dynamic_agent_runner/openai_client.py` so it contains or references
these responsibilities more explicitly:

1. **Request and response data models**
   - keep `OpenAIModelRequest`, `ModelResponse`, and `ModelToolCall`
   - keep repository-owned request and normalization helpers

2. **Provider/client facade**
   - define repository-owned sync and async wrapper protocols or thin classes
   - optionally add a small provider configuration structure for `base_url`,
     optional `api_key`, and optional provider diagnostics metadata

3. **SDK-backed wrapper implementation**
   - isolate `openai` imports and direct SDK construction here
   - preserve project-specific import/availability error translation

4. **Runtime adapters**
   - keep existing adapter semantics
   - refactor them to depend on the facade rather than raw SDK client instances

### Backward compatibility strategy

- Prefer keeping `OpenAIClientAdapter` and `AsyncOpenAIClientAdapter` names to
  minimize churn unless implementation reveals a strong reason to rename them.
- If clearer terminology is desired later, introduce aliases or staged export
  migration rather than combining naming churn with the wrapper refactor.

## Delivery Priorities and ROI Framing

### Highest-ROI feature work

The highest-ROI work in this feature is the **core provider-wrapper
implementation** that turns the current direct SDK construction path into a
repository-owned provider/client facade with configurable OpenAI-compatible
endpoint support.

That highest-value cluster is:

1. repository-owned sync/async provider-client facades
2. SDK-backed wrapper isolation
3. `base_url` and optional `api_key` provider configuration
4. adapter refactoring that preserves existing `models` and `is_local` routing
5. preservation of repository-owned request construction and response
   normalization

This work has the best return because it:

- fixes a concrete current coupling in `src/dynamic_agent_runner/openai_client.py`
- unlocks arbitrary OpenAI-compatible endpoints without executor redesign
- preserves the hosted OpenAI default path
- improves future compatibility with local or self-hosted providers without
  creating a separate runtime family
- keeps request shaping and response normalization under repository ownership

### Priority tiers

#### Priority 1 — core feature implementation

These slices create the main user and architectural value of the feature:

- **Slice 1 — Repository-owned provider/client facade**
  - define narrow repository-owned sync and async wrapper/facade contracts
  - add any small provider configuration structure needed for `base_url`,
    optional `api_key`, and optional diagnostics metadata
- **Slice 2 — SDK-backed default wrapper isolation**
  - move direct `openai` import and SDK construction behind the wrapper layer
  - preserve the default hosted OpenAI path
  - add OpenAI-compatible `base_url` support and optional `api_key`
    passthrough
- **Slice 3 — Adapter refactor and routing preservation**
  - refactor `OpenAIClientAdapter` and `AsyncOpenAIClientAdapter` to consume the
    wrapper/facade rather than raw SDK-construction assumptions
  - preserve `models` and `is_local` as the canonical executor-routing metadata
- **Slice 4 — Preserve repository-owned request/normalization logic**
  - keep `build_openai_request(...)` as the canonical request-construction path
  - keep `normalize_openai_response(...)` as the canonical normalization path
  - prevent provider-specific transport concerns from leaking into executor
    logic

#### Priority 2 — validation that protects the feature investment

These slices are required to prove the boundary refactor preserved behavior:

- **Slice 5 — Tests for wrapper behavior and compatible endpoints**
  - cover sync and async wrapper paths
  - cover hosted-default construction without live network calls
  - cover custom `base_url`, optional `api_key`, and preserved `is_local`
    routing semantics
- **Slice 7 — Validation evidence**
  - run the focused validation commands for `tests/test_openai_client.py`
  - widen to executor and import validation only when the implementation surface
    requires it

#### Priority 3 — optional polish

This slice is valuable but should not delay the core transport-boundary work:

- **Slice 6 — Optional export and documentation follow-up**
  - export new public wrapper/configuration types only if they should be
    caller-visible
  - update docs only when usage materially changes or an endpoint example adds
    clarity

### Smallest useful kickoff slice

The smallest coherent first implementation pass should deliver the seam and the
main OpenAI-compatible endpoint unlock before broader polishing:

1. define the repository-owned sync/async facades
2. add the provider configuration seam
3. move direct SDK construction behind the wrapper
4. preserve default hosted OpenAI construction
5. add `base_url` support
6. add optional `api_key` passthrough

Immediately after that, the next pass should refactor the adapters onto the new
seam, preserve routing metadata, and lock behavior down with focused tests.

## Scope Boundaries

### In scope

- repository-owned wrapper/facade around the official `openai` SDK
- `base_url` and optional `api_key` support for OpenAI-compatible endpoints
- preservation of `models` and `is_local` adapter metadata
- continued repository ownership of request shaping and response normalization
- fake-client-friendly tests with no live network calls

### Out of scope

- direct llama.cpp adapter implementation
- provider capability auto-discovery
- runtime schema changes for provider declarations
- product-specific deep integration with any one local provider

## Validation Strategy

Primary validation should stay narrow and local to the refactor:

- `poetry run pytest tests/test_openai_client.py -q`

Run secondary validation if adapter construction or executor assumptions change:

- `poetry run pytest tests/test_executor.py -q`

If public exports change:

- `poetry run pytest tests/test_import.py -q`

## Risks and Tradeoffs

- Adding `base_url` support increases provider flexibility but also increases the
  number of compatibility edge cases that may need normalization fixes later.
- Keeping current adapter names reduces churn but may leave slightly vendor-heavy
  naming around a more general OpenAI-compatible endpoint model.
- Splitting the implementation into too many small modules could add churn beyond
  the actual abstraction win, so the first implementation should prefer minimal
  file movement unless `openai_client.py` becomes hard to maintain.

## Recommended Implementation Order

Implement the feature in phases so the highest-value boundary changes land
before polish work:

### Phase A — establish the repository-owned seam

1. Define the sync provider/client facade.
2. Define the async provider/client facade.
3. Introduce a small provider-configuration seam for `base_url`, optional
   `api_key`, and optional diagnostics metadata.
4. Keep the facade narrow enough for fake-client tests and future alternate
   implementations.

### Phase B — isolate SDK construction and unlock compatible endpoints

5. Move direct `openai` SDK import and construction behind the repository-owned
   wrapper implementation.
6. Preserve project-specific `ModelExecutionError` behavior when the SDK is
   unavailable.
7. Preserve default hosted OpenAI construction with no mandatory new provider
   object.
8. Add optional `base_url` support for OpenAI-compatible endpoints.
9. Add optional `api_key` passthrough support.

### Phase C — refactor adapters while preserving executor routing

10. Refactor `OpenAIClientAdapter` to consume the wrapper/facade.
11. Refactor `AsyncOpenAIClientAdapter` to consume the async wrapper/facade.
12. Preserve `models` metadata.
13. Preserve `is_local` metadata.
14. Keep any additional provider diagnostics optional and non-authoritative for
    executor routing.

### Phase D — preserve repository ownership of request/response semantics

15. Keep `build_openai_request(...)` or a directly equivalent helper as the
    canonical request-construction path.
16. Keep `normalize_openai_response(...)` or a directly equivalent helper as the
    canonical response-normalization path.
17. Ensure provider-transport changes do not move request or response semantics
    into executor logic.

### Phase E — prove behavior with focused tests

18. Update sync wrapper tests using fake clients or monkeypatched construction.
19. Update async wrapper tests using fake clients or monkeypatched construction.
20. Add coverage for hosted-default construction without live network calls.
21. Add coverage for custom `base_url` configuration.
22. Add coverage for optional `api_key` passthrough.
23. Add coverage confirming `is_local=True` adapters preserve existing routing
    semantics.

### Phase F — validate and polish

24. Run `poetry run pytest tests/test_openai_client.py -q` and record the
    result.
25. If adapter integration behavior changed, run
    `poetry run pytest tests/test_executor.py -q` and record the result.
26. If exports changed, run `poetry run pytest tests/test_import.py -q` and
    record the result.
27. Update exports only if new public wrapper/configuration types should be
    caller-visible.
28. Update README or adjacent docs only if public usage changed or a new
    endpoint example materially improves clarity.

This ordering intentionally treats Slices 1 through 4 as the core feature,
Slice 5 plus Slice 7 as the confidence-building validation layer, and Slice 6
as optional polish that should not delay the main transport-boundary refactor.
