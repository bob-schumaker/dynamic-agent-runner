# OpenAI-Compatible Provider Wrapper Specification

## Metadata

- Feature slug: `openai-compatible-provider-wrapper`
- Mode: `guided`
- Status: partially implemented follow-up; Slices 1-4 are implemented in the
  current repo state, while later slices remain planned
- Related artifacts:
  - `src/dynamic_agent_runner/openai_client.py`
  - `src/dynamic_agent_runner/executor.py`
  - `src/dynamic_agent_runner/__init__.py`
  - `tests/test_openai_client.py`
  - `tests/test_executor.py`
  - `specs/llama-cpp-graph-mutation/spec.md`

## Objective

Refactor the runtime's OpenAI integration so `dynamic-agent-runner` depends on a
repository-owned provider/client facade rather than directly depending on the
construction shape of the `openai` Python package, while also supporting
arbitrary OpenAI-compatible endpoints through configurable `base_url` and
optional `api_key` inputs.

## Problem Statement

The current runtime already has a useful model-adapter seam, and the first two
provider-wrapper slices have improved the default OpenAI path inside
`src/dynamic_agent_runner/openai_client.py`:

- `OpenAIProviderConfig`, `OpenAIClientProvider`, and
  `AsyncOpenAIClientProvider` now provide a repository-owned provider/client
  facade boundary
- `SDKBackedOpenAIClientProvider` and `SDKBackedAsyncOpenAIClientProvider` now
  isolate the official `openai` SDK-backed default transport
- `create_default_openai_client(...)` and
  `create_default_async_openai_client(...)` now accept a repository-owned
  provider configuration object and support `base_url` plus optional `api_key`
- `OpenAIClientAdapter` and `AsyncOpenAIClientAdapter` now lazily resolve their
  default sync/async clients through the repository-owned default provider
  facades instead of bypassing that seam on the default path
- repository-owned sync/async response-dispatch helpers now centralize transport
  calls, runtime-facing error translation, and response normalization inside
  `openai_client.py`

That is meaningful progress, but the runtime has not yet completed the full
refactor. Slice 4 now makes request dispatch and response normalization ownership
more explicit by routing both adapters through repository-owned sync/async
helpers while preserving existing metadata-based routing semantics. The
remaining slices are now focused on broader validation bookkeeping and optional
follow-up polish.

The repository also has a preserved local-model direction in
`specs/llama-cpp-graph-mutation/spec.md` that prefers fitting local execution
into the existing adapter contract rather than inventing a parallel runtime
model family. A provider/client wrapper around the OpenAI-compatible wire
protocol supports that direction better than introducing backend-specific
runtime logic for each future local provider.

## Users

- Runtime maintainers who need a stable internal integration boundary.
- Callers using the hosted OpenAI service through the default runtime path.
- Callers using OpenAI-compatible local or self-hosted providers such as mac-only
  local servers.

## Existing Runtime Context

- `executor.py` already depends on `OpenAIClientAdapter` /
  `AsyncOpenAIClientAdapter` rather than directly importing SDK client classes.
- `openai_client.py` already owns request construction (`build_openai_request`)
  and response normalization (`normalize_openai_response`), which are good
  repository-owned seams to preserve.
- `openai_client.py` now also exposes repository-owned provider/configuration
  seams and SDK-backed default provider wrappers, and the adapters now consume
  that seam consistently for both explicit-provider and default lazy
  construction paths.
- `openai_client.py` now also exposes repository-owned sync/async response-
  dispatch helpers so transport calls, runtime-facing error translation, and
  normalization remain centralized in repository code rather than spread across
  adapter implementations.
- Adapter selection already preserves `models` and `is_local`, and executor
  routing already supports `local_only` requirements using those existing
  adapter attributes.

## Functional Requirements

### FR-1: Introduce a repository-owned provider/client facade

The runtime must define a repository-owned sync and async facade for creating
Responses API calls, so runtime-facing code is isolated from direct dependency on
the constructor and type shape of the official `openai` package.

Acceptance criteria:

- Given the runtime imports `dynamic_agent_runner.openai_client`, when adapter
  construction occurs, then runtime-facing code depends on repository-owned
  protocols or wrapper classes rather than directly requiring `openai.OpenAI` or
  `openai.AsyncOpenAI` objects.
- Given the official `openai` package remains the default transport, when SDK
  integration code imports that package, then that import occurs only inside the
  SDK-backed wrapper implementation or wrapper factory path rather than inside
  executor logic.
- Given sync and async execution both exist, when wrappers are defined, then the
  repository provides both sync and async wrapper variants instead of forcing one
  execution mode to emulate the other.

### FR-2: Preserve the hosted OpenAI default path

The refactor must preserve the current default behavior of using the official
`openai` package when callers do not provide custom provider configuration.

Acceptance criteria:

- Given an existing caller that relies on default OpenAI environment variables,
  when the refactor lands, then the default adapter path still constructs an SDK
  backed client lazily and continues to work without requiring a new mandatory
  provider object.
- Given the `openai` package is unavailable, when the default wrapper is
  constructed, then the runtime still raises a project-specific
  `ModelExecutionError` rather than leaking raw import details.

### FR-3: Support arbitrary OpenAI-compatible endpoint configuration

The runtime must support configuration of an OpenAI-compatible provider endpoint
without changing executor logic.

Acceptance criteria:

- Given a caller provides a `base_url`, when the default SDK-backed wrapper is
  constructed, then requests are routed to that OpenAI-compatible endpoint.
- Given a caller provides an `api_key`, when the wrapper is constructed, then the
  key is passed through to the SDK-backed transport path.
- Given a caller omits `api_key` for a local provider that does not require one,
  when the wrapper is constructed, then the configuration remains valid as long
  as the downstream SDK/client path supports the omission.
- Given a caller targets an OpenAI-compatible local endpoint, when the adapter is
  marked `is_local=True`, then no executor changes are required for that provider
  to participate in existing local-only model selection.

### FR-4: Preserve adapter metadata and selection semantics

The refactor must preserve the existing adapter-level metadata used by executor
selection.

Acceptance criteria:

- Given an adapter advertises `models`, when executor model matching runs, then
  the refactor preserves the current behavior of model-aware adapter selection.
- Given an adapter advertises `is_local=True`, when executor evaluates
  `local_only` requirements, then the existing local-provider selection behavior
  continues to function.
- Given provider-specific diagnostics are helpful, when the implementation adds
  provider metadata such as a provider name, then that metadata remains optional
  and does not replace `models` or `is_local` as the executor's canonical
  routing metadata.

### FR-5: Keep request construction and response normalization repository-owned

The runtime must continue to own request shaping and response normalization
instead of delegating those concerns to provider-specific wrappers.

Acceptance criteria:

- Given model request construction occurs, when an adapter sends a request, then
  `build_openai_request(...)` or a directly equivalent repository-owned helper
  remains the canonical request-shaping path.
- Given a provider returns an OpenAI Responses-style object, when runtime code
  converts it to internal types, then `normalize_openai_response(...)` or a
  directly equivalent repository-owned helper remains the canonical
  normalization path.
- Given future providers vary in minor protocol details, when compatibility fixes
  are needed, then those fixes can be implemented in repository-owned adapter or
  normalization logic without changing executor behavior.

### FR-6: Keep testing fake-client-friendly and live-network-free

The refactor must preserve the current unit-test direction of using fake clients
and no live network calls.

Acceptance criteria:

- Given `tests/test_openai_client.py`, when unit tests cover the adapter and
  wrapper path, then tests use fake repository-owned clients or fake wrapper
  implementations rather than live API calls.
- Given the SDK-backed wrapper is the default implementation, when tests need to
  validate construction behavior, then that behavior is covered with isolated
  fake or monkeypatched construction rather than a real external request.

## Non-Goals

- No direct llama.cpp in-process adapter implementation in this feature.
- No provider auto-discovery from remote `/v1/models` or equivalent endpoints.
- No guarantee that every third-party OpenAI-compatible endpoint fully matches
  hosted OpenAI semantics.
- No workflow-definition schema changes for provider selection in this feature.
- No deep integration with any one local server product as a required dependency.

## Design Constraints

- Prefer composition and repository-owned protocols/facades over subclassing the
  official `openai` SDK client classes.
- Preserve current executor-facing adapter usage as much as possible to limit
  churn outside `openai_client.py` and its tests.
- Preserve backward compatibility for existing hosted OpenAI callers where
  reasonable.
- Keep the default `openai` SDK dependency path available because it is still the
  repository's canonical hosted provider path.

## Risks and Compatibility Notes

- Some OpenAI-compatible providers may diverge subtly in Responses API behavior,
  tool-call formatting, or usage metadata.
- Supporting `base_url` and optional `api_key` creates a broader provider surface
  than the currently implicit hosted OpenAI-only path, so tests should focus on
  repository-owned normalization and routing rather than assuming full wire-level
  equivalence.
- Naming of the runtime adapter may remain `OpenAIClientAdapter` for backward
  compatibility even if the implementation becomes more explicitly
  OpenAI-compatible and provider-agnostic under the hood.
