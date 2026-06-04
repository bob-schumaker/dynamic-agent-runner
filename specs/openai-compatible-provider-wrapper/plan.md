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
  client classes, which means the main remaining coupling is inside
  `openai_client.py`.
- `openai_client.py` currently defines protocol types for a minimal Responses API
  client, but its default factory functions still directly instantiate
  `openai.OpenAI()` and `openai.AsyncOpenAI()`.
- Request construction and response normalization already live in repository code
  and should remain repository-owned after the refactor.

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

1. Add the repository-owned sync/async wrapper/facade and configuration seam.
2. Move SDK-specific construction behind that seam.
3. Refactor adapters to consume the seam while preserving `models` and
   `is_local`.
4. Add tests for default construction, fake clients, and custom
   OpenAI-compatible endpoint configuration.
5. Update exports or docs only if the refactor changes public usage or naming.
