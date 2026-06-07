# llama.cpp local-model adapter specification

## Metadata

- Feature slug: `llama-cpp-local-model`
- Mode: `guided`
- Artifact type: authoritative SDD feature specification
- Status: active feature record; Slices 1-2 complete; direct in-process
  llama.cpp chat is the next planned follow-up
- Version: `1.0`
- Owner: repository maintainers and future implementers of local-model support
- Next gate: Slice 3 follow-up may begin with direct in-process
  `llama_cpp.Llama` chat adapter tests, while `validation.md` remains the source
  of truth for fresh execution evidence
- Approval state: user-directed refresh to make this file the authoritative SDD
  spec for the feature
  - first-slice local endpoint helper implementation landed in commit `6d269ad`
    (`feat(local-models): add local openai endpoint helpers`)
  - provider-seam wiring follow-up landed in commit `ee0bf33`
    (`refactor(local-models): route helpers through adapter factories`)
  - package-root export follow-up landed in commit `dd37c62`
    (`feat(local-models): export local endpoint helpers`)
  - Slice 2 model-resolution precedence RED tests landed in commit `f564caa`
    (`test(local-models): add RED resolution precedence coverage`)
  - Slice 2 failure-taxonomy RED tests landed in commit `cdc1b00`
    (`test(local-models): add RED failure taxonomy coverage`)
  - Slice 2 model-reference resolution implementation landed in commit
    `7a11464` (`feat(local-models): add runtime model path resolution`)
  - Slice 2 endpoint-failure translation implementation landed in commit
    `f4bcb0e` (`feat(local-models): translate local endpoint failures`)
  - Slice 2 default Hugging Face download wiring landed in commit `d5857dd`
    (`feat(local-models): wire default hub downloads`)
  - Slice 2 authoritative model-identity preservation landed in commit
    `9b7078f` (`feat(local-models): preserve authoritative model identity`)
  - fresh T1.1, T1.2, T2.1, and T2.2 RED checkpoints plus targeted T1.3, T1.4,
    T1.5, T2.3, T2.4, T2.5, and T2.6 GREEN validation now exist; Slice 2 is now
    complete and any next follow-up is an optional Slice 3 step
  - any earlier prototype work is non-authoritative historical context only
- Related artifacts:
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/openai-compatible-provider-wrapper/spec.md`
  - `specs/internal-graph-mutation/spec.md`
  - `specs/llama-cpp-local-model/plan.md`
  - `specs/llama-cpp-local-model/tasks.md`
  - `specs/llama-cpp-local-model/validation.md`
  - `src/dynamic_agent_runner/openai_client.py`
  - `src/dynamic_agent_runner/executor.py`
  - local llama-cpp Python source checkout:
    `/Users/roschuma/Repos/github/llama-cpp-python/`
  - local `huggingface_hub` source checkout:
    `/Users/roschuma/Repos/github/huggingface_hub/`

## Objective

Define the authoritative repository direction for caller-provided local
llama.cpp-backed model adapters, including direct in-process execution with
`llama_cpp.Llama`, while still fitting the runtime's existing model-adapter
contract instead of introducing a parallel local-model execution family.

## Problem Statement

`dynamic-agent-runner` already has a useful model execution boundary:

- model adapters advertise `models`
- adapters expose `is_local` for local adapter metadata
- executor routing depends on adapter-level model coverage and the public
  `model_adapter_coverage` policy
- the provider-wrapper direction preserves repository-owned request and response
  boundaries around OpenAI-compatible transports

The repository does not yet have an authoritative feature-level source of truth
for how llama.cpp local execution should fit those seams. Earlier prototype work
was intentionally reverted, so future work must not reintroduce an ad hoc local
execution path that bypasses the established adapter contract or requires a
local server when the caller wants direct in-process execution.

## Users

- Runtime maintainers defining the next local-model execution seam.
- Internal callers or downstream hosts that need local-only model execution.
- Future implementers of local embedding-backed runtime features.

## User Stories

- As a runtime maintainer, I want llama.cpp local-model support to reuse the
  existing adapter/provider seams, so that local execution does not fork the
  runtime architecture into a separate model family.
- As a caller or downstream host, I want to run a local GGUF model directly
  through `llama_cpp.Llama`, so that llama.cpp use does not require a local
  server to be installed, started, or reachable.
- As a caller or downstream host, I want to target a caller-owned or
  deployer-owned OpenAI-compatible local endpoint when I already have one, so
  that server-backed deployments remain possible without giving the core library
  ownership of server installation, launch, and lifecycle behavior.
- As a future implementer of local embedding-backed features, I want the chat,
  embedding, model-resolution, and error-boundary contracts defined up front, so
  that later work can extend the feature without rewriting the initial local
  chat slice.

## Existing Runtime Context

- The canonical executable input remains the immutable runtime package directory
  defined in `specs/dynamic-agent-runner/spec.md`.
- The runtime already supports model-adapter selection through advertised model
  metadata and the public strict/augmented `model_adapter_coverage` policy.
- The OpenAI-compatible provider-wrapper direction already aims to isolate
  transport details behind repository-owned seams, which is compatible with
  OpenAI-style local transports and response normalization.
- A local source checkout for future API and behavior inspection is available at
  `/Users/roschuma/Repos/github/llama-cpp-python/`.
- The upstream docs currently expose two relevant integration surfaces:
  - a high-level in-process Python API on `llama_cpp.Llama`, including
    `create_chat_completion`, `create_chat_completion_openai_v1`,
    `create_embedding`, and `embed`
  - an OpenAI-compatible local server started with
    `python3 -m llama_cpp.server --model <model_path>`
- The upstream server docs also describe deployment-facing configuration such as
  `chat_format`, `chat_template_kwargs`, environment-variable mirroring of CLI
  flags, JSON config-file support, and alias-based multi-model routing via
  `model_alias`.
- The upstream README documents additional behavior that affects spec realism:
  - high-level text completion and streaming are available from the in-process
    `Llama` API
  - embeddings require `embedding=True` at model construction time
  - chat completion formatting follows a precedence order of `chat_handler`,
    then explicit `chat_format`, then GGUF tokenizer chat template metadata,
    then fallback behavior
  - `from_pretrained(...)` can pull GGUF assets from Hugging Face and cache
    them outside the workflow package contract
- The upstream docs describe the server as a Python-installed capability
  (`pip install llama-cpp-python[server]`) rather than as a repository-defined
  standalone binary contract.
- The local `huggingface_hub` source and README document repository-owned file
  and snapshot download helpers:
  - `hf_hub_download(...)` for specific files with cache reuse
  - `snapshot_download(...)` for repository snapshots
  - configurable `revision` and `cache_dir`
- A separate future spec at `specs/internal-graph-mutation/spec.md` owns graph
  mutation and context-pruning design. Local embeddings may enable that work,
  but they do not define this feature's architectural boundary.

## Scope

This feature specification covers:

1. local llama.cpp-backed chat adapter support through the existing adapter
   contract
2. optional separate local embedding-capable configuration for internal runtime
   use
3. direct in-process llama.cpp chat execution with `llama_cpp.Llama`
4. repository-owned normalization of llama.cpp in-process and OpenAI-compatible
   chat responses
5. configuration boundaries between portable workflow metadata and runtime-owned
   local model settings
6. support for caller-owned or deployer-owned OpenAI-compatible llama.cpp
   endpoints through the existing provider seam
7. runtime-owned download of referenced model assets when they are missing
   locally

## Current Status and Boundary

- The repository now contains an initial local-model helper module at
  `src/dynamic_agent_runner/local_models.py`, added in commit `6d269ad`
  (`feat(local-models): add local openai endpoint helpers`).
- Fresh test-first execution has progressed through T2.6 GREEN: T1.1 RED
  helper-contract tests landed in commit `a5798cc`
  (`test(local-models): add RED tests for local endpoint helpers`), T1.2 RED
  executor-routing tests landed in commit `b79f124`
  (`test(local-models): add RED executor routing coverage`), the T1.3 helper
  implementation landed in commit `6d269ad`, and the T1.4 provider-seam
  follow-up landed in commit `ee0bf33`, and the T1.5 package-root export
  follow-up landed in commit `dd37c62`, and the T2.1 model-resolution
  precedence RED tests landed in commit `f564caa`, and the T2.2 failure-
  taxonomy RED tests landed in commit `cdc1b00`, and the T2.3 model-reference
  resolution implementation landed in commit `7a11464`, and the T2.4
  endpoint-failure translation implementation landed in commit `f4bcb0e`, and
  the T2.5 default Hugging Face download wiring landed in commit `d5857dd`, and
  the T2.6 authoritative model-identity preservation implementation landed in
  commit `9b7078f`,
  keeping local helper construction on the repository-owned adapter/provider
  path while establishing the approved Slice 2 resolution surface in
  `local_models.py`, the minimal local-model error taxonomy it depends on, the
  local-endpoint-specific translation seam for connectivity and protocol
  failures, the default `huggingface_hub` wiring for explicit file and snapshot
  references, and runtime-owned mismatch reporting that preserves authoritative
  identity metadata across expected model IDs, explicit local paths, explicit
  Hub file references, and endpoint-observed model names.
- Any earlier prototype code or prior test results are historical context only
  and do not count as current implementation or validation evidence.
- This artifact is authoritative for feature intent and design boundaries;
  `plan.md`, `tasks.md`, and `validation.md` track execution state and evidence.
- This artifact is authoritative for **what** the feature must do and **why** it
  exists. Future implementation work must derive technical approach, execution
  order, and validation commands from companion SDD artifacts rather than coding
  directly from this spec alone.
- Implementation for this feature now proceeds from the approved `plan.md` and
  `tasks.md`; future validation evidence should be recorded in `validation.md`.

## Primary Implementation Path

- Slices 1-2 already delivered caller-owned OpenAI-compatible endpoint helpers
  and local model asset resolution. That path remains available when the caller
  already provides a llama.cpp server or another OpenAI-compatible wrapper.
- The next implementation path should add a direct in-process llama.cpp chat
  adapter backed by documented `llama_cpp.Llama` APIs. Direct local execution
  must not require the `llama_cpp.server` package extra, a reachable local
  server, or runtime-managed server lifecycle.
- The expected runtime surface is still the normal model adapter contract:
  advertised model names, `is_local=True`, `create_response(...)` /
  async-wrapper behavior, package-owned request/response normalization, and
  strict adapter coverage for local-only client intent.
- A caller-owned OpenAI-compatible llama.cpp server is an alternate wrapper path,
  not a prerequisite for llama.cpp local execution.

## Functional Requirements

### FR-1: Support llama.cpp through the existing adapter contract

The runtime must support caller-provided llama.cpp-backed adapters as normal
model adapters rather than as a separate model-runtime family.

Acceptance criteria:

- Given a caller provides a llama.cpp-backed adapter that advertises model
  names, when an `llm_step` requests one of those models, then the runtime may
  select that adapter through the existing model-selection flow.
- Given a llama.cpp-backed adapter is intended for local execution, when the
  adapter is constructed, then it reports `is_local=True` by default unless the
  caller explicitly overrides that behavior for a nonstandard deployment.
- Given local-only client intent, when an eligible llama.cpp-backed adapter is
  available and `model_adapter_coverage="strict"` is used, then executor routing
  may satisfy the request without requiring a remote provider.
- Given local-model support is added, when callers use the runtime, then they
  still use the existing adapter-facing execution seams rather than a new
  top-level execution API.

### FR-2: Support documented upstream integration paths

The feature must align with documented `llama-cpp-python` integration surfaces
rather than relying on undocumented local-runtime hooks.

Acceptance criteria:

- Given in-process local execution is selected, when the feature is
  implemented, then the runtime uses documented high-level Python API surfaces
  such as `llama_cpp.Llama.create_chat_completion` or
  `create_chat_completion_openai_v1`.
- Given server-based local execution is selected, when the feature is
  implemented, then the runtime may target the documented OpenAI-compatible
  `llama_cpp.server` surface through the repository's existing provider-wrapper
  seam.
- Given direct local execution is selected, when the feature is implemented,
  then the runtime must not require a local server process or the
  `llama-cpp-python[server]` extra.
- Given async runtime execution is needed for direct local execution, when the
  adapter wraps synchronous `llama_cpp.Llama` calls, then it should use the
  repository's existing async-adapter pattern for blocking local backends rather
  than requiring an undocumented native async in-process `llama_cpp` client
  surface.
- Given a caller or deployer already provides an OpenAI-compatible wrapper or
  endpoint for a local llama.cpp server, when local execution is requested,
  then the runtime should consume that endpoint through the existing provider
  seam rather than owning server launch behavior itself.

### FR-3: Support local chat, aliases, and optional local embedding configuration

The feature must allow local chat-model configuration plus optional separate
embedding-capable local configuration for internal runtime behavior.

Direct in-process local chat may ship without simultaneously shipping separate
local embedding execution, as long as later implementation planning preserves
the embedding configuration contract defined here.

Acceptance criteria:

- Given a caller configures a primary local chat model, when a llama.cpp-backed
  adapter is constructed, then the adapter can expose one or more model aliases
  through the existing adapter metadata seam.
- Given direct in-process deployment uses one local model artifact, when
  requests are routed by model name, then alias-based routing should use
  adapter-declared aliases rather than requiring portable workflow packages to
  know concrete GGUF file paths.
- Given server-based deployment uses documented multi-model configuration, when
  requests are routed by model name, then alias-based routing may use the
  server's `model_alias` behavior.
- Given a caller provides separate local embedding model configuration, when
  internal runtime logic requires embeddings, then the runtime can use that
  local configuration without requiring a remote embedding API.
- Given the feature is implemented against the documented in-process API, when
  embeddings are enabled, then the runtime must account for the upstream
  requirement to construct the model with `embedding=True`.
- Given chat and embedding capabilities are backed by different local model
  artifacts, when the implementation is configured, then the runtime may treat
  them as related but distinct local resources.
- Given embeddings are needed, when the feature is implemented against the
  documented in-process API, then the design may rely on the upstream
  `create_embedding` or `embed` surfaces rather than inventing a repository-
  specific embedding primitive first.
- Given graph-mutation or context-pruning work later needs local embeddings,
  when that work is planned, then embedding support may be implemented as a
  later slice of this feature rather than expanding the first endpoint-backed
  chat slice into graph-mutation delivery.

### FR-4: Preserve repository-owned response normalization

The runtime must preserve its repository-owned request and response ownership
boundaries when local llama.cpp execution is introduced.

Acceptance criteria:

- Given a llama.cpp-backed chat provider returns an OpenAI-compatible response
  shape, when the runtime consumes that response, then it is normalized into the
  existing internal `ModelResponse` and `ModelToolCall` structures.
- Given a local response includes OpenAI-style tool-call data, when the response
  is normalized, then tool calls are preserved in the runtime's current
  internal shape rather than being dropped or exposed as raw provider-specific
  objects.
- Given in-process chat completion is used, when prompt formatting is prepared,
  then the runtime should respect the documented upstream precedence order of
  `chat_handler`, explicit `chat_format`, GGUF tokenizer chat-template
  metadata, and fallback behavior rather than assuming one universal prompt
  format.
- Given in-process chat completion returns a dict, pydantic/OpenAI-v1 response,
  or provider-specific object shape, when the runtime consumes that response,
  then it must normalize final text and supported tool-call data into the
  package-owned `ModelResponse` boundary.
- Given a local server deployment is configured with a function-calling-capable
  model and documented chat-format requirements, when tool calling is used,
  then the runtime may rely on the documented OpenAI-compatible JSON-schema
  function-calling surface rather than inventing a custom local tool-call
  transport.
- Given upstream function-calling support uses either Functionary models or the
  generic `chatml-function-calling` path, when this feature later enables
  in-process tool calling, then the runtime must preserve those documented
  prerequisites instead of treating tool calling as universally available.
- Given future local providers vary in small wire details, when compatibility
  fixes are needed, then those fixes belong in repository-owned adapter or
  normalization logic rather than executor-specific branches.

### FR-5: Keep low-level local model settings out of portable workflow packages

Portable workflow artifacts must not become the canonical place for low-level
llama.cpp deployment configuration.

Acceptance criteria:

- Given a caller configures a local llama.cpp adapter, when deployment-specific
  details such as filesystem paths or backend tuning are provided, then those
  values remain runtime-owned configuration rather than required portable
  workflow manifest fields.
- Given a caller configures the adapter, when no explicit model-cache folder is
  provided, then the adapter defaults its model-cache path to
  `~/.ollama/models`.
- Given local-model support is implemented, when workflow packages are moved
  across environments, then the package does not require baked-in local
  filesystem paths to remain valid as a portable artifact.

### FR-5b: Download referenced model assets when they are not available locally

The adapter should support downloading referenced llama.cpp model assets from
the Hugging Face Hub when they are not already available on local disk.

Supported runtime-owned model reference shapes:

- explicit local file path
- explicit Hugging Face file reference: `repo_id` + `filename`
- explicit Hugging Face snapshot reference: `repo_id` with optional `revision`

Acceptance criteria:

- Given adapter configuration references a Hugging Face model artifact rather
  than an already-present local file, when the required asset is missing
  locally, then the runtime may download it using `huggingface_hub` rather than
  requiring a separate manual prefetch step.
- Given the adapter knows an exact remote file to fetch, when download is
  needed, then the implementation may use `hf_hub_download(...)` with runtime-
  owned parameters such as `repo_id`, `filename`, optional `revision`, and
  optional `cache_dir`.
- Given the adapter needs a repository snapshot or multiple related assets,
  when download is needed, then the implementation may use
  `snapshot_download(...)` rather than inventing a custom repository-fetch
  workflow.
- Given model resolution runs, when multiple resolution sources are available,
  then the adapter should apply this precedence order:
  1. explicit local file path
  2. explicit cache-folder lookup
  3. default cache-folder lookup at `~/.ollama/models`
  4. Hugging Face download from an explicit remote reference
- Given no explicit model-cache folder is provided, when Hub-backed download or
  cache resolution occurs, then the adapter should use `~/.ollama/models` as
  the default cache root.
- Given the requested asset is already present in the Hugging Face local cache,
  when the adapter resolves the model path, then cached files should be reused
  instead of being redundantly downloaded.
- Given an explicit remote Hugging Face reference is configured and no offline
  or no-network policy blocks access, when the referenced asset is missing
  locally, then automatic download is the default resolution behavior rather
  than an optional manual prefetch-only path.
- Given offline or no-network behavior must be enforced, when that policy is
  applied during model resolution, then it comes from caller-owned or
  deployment-owned runtime configuration above the portable workflow package
  rather than from implicit workflow metadata.
- Given download is requested but the Hub reference is invalid, credentials are
  unavailable, offline or local-only policy forbids network access, or the
  remote asset cannot be resolved, when the adapter prepares local execution,
  then the runtime fails clearly with a model-resolution error instead of
  silently falling back to another model.

### FR-5c: Distinguish model-resolution failures from endpoint failures

The runtime must report local model-resolution failures separately from
in-process backend execution failures and OpenAI-compatible endpoint
connectivity or protocol failures.

Acceptance criteria:

- Given a local path, cache lookup, or Hub fetch cannot resolve the requested
  model asset, when preparation runs, then the runtime reports a
  model-resolution error.
- Given an OpenAI-compatible local endpoint is unreachable, unauthorized, not
  ready, or wire-incompatible, when model execution runs, then the runtime
  reports an endpoint connectivity or endpoint protocol error rather than a
  model-resolution error.
- Given direct in-process llama.cpp model loading or generation fails after the
  model asset resolves, when model execution runs, then the runtime reports a
  model execution error rather than an endpoint connectivity/protocol error.
- Given the caller supplies a provider or endpoint that is reachable but serves
  a different model than intended, when the adapter detects a mismatch through
  configured model metadata or request failure, then the runtime reports the
  mismatch clearly instead of silently rerouting to another model.
- Given mismatch detection is needed, when the runtime decides what model was
  intended, then the authoritative identity comes from runtime-owned adapter
  configuration such as the declared model alias, explicit local path, or
  explicit Hugging Face reference rather than from guessed workflow-package
  semantics.

### FR-6: Keep server ownership outside the runtime library

Direct llama.cpp execution must not require a server. If llama.cpp is exposed
through an OpenAI-compatible local server, that server's installation, launch,
lifecycle, and endpoint ownership must remain outside the core
`dynamic-agent-runner` library contract.

Acceptance criteria:

- Given a workflow package is loaded, when local server-based execution is used,
  then the package itself does not contain or require server binaries, Python
  environments, model weights, port numbers, or launch scripts as portable
  workflow metadata.
- Given a caller or deployer provides an OpenAI-compatible local endpoint, when
  the runtime connects to it, then connection details such as base URL,
  credentials, readiness, and lifecycle remain caller-owned or deployment-owned
  concerns above the base workflow package.
- Given the repository's current direction remains a Python library with
  package-directory-first workflow inputs, when this feature is implemented,
  then direct in-process execution uses `llama_cpp.Llama`, while server-backed
  execution consumes a provided OpenAI-compatible wrapper or endpoint rather
  than launching and supervising a local server itself.

## Non-Functional Requirements

### NFR-1: Preserve architecture continuity

The feature must preserve the repository's existing adapter/provider architecture
instead of introducing a second top-level local-runtime API or bypass path.

### NFR-2: Preserve workflow-package portability

Portable workflow packages must remain environment-agnostic and must not become
the canonical storage location for machine-specific local-model deployment
details.

### NFR-3: Preserve clear failure taxonomy

The runtime must keep local model-resolution failures, endpoint connectivity
failures, endpoint protocol failures, and model-identity mismatch failures
distinguishable enough for callers and maintainers to debug the correct layer.

### NFR-4: Preserve testability without live infrastructure

Direct in-process work must remain testable with fake backends, fake resolution
helpers, and repository-owned fixtures, without requiring live network access,
live Hugging Face access, or a live llama.cpp server for core unit validation.

### NFR-5: Preserve spec-first drift control

If future implementation planning changes the direct-execution boundary, server
ownership boundary, model-resolution precedence, or embedding scope, the SDD
artifacts must be updated explicitly rather than letting code drift silently from
this specification.

## Edge and Error Cases

- If the configured local endpoint is reachable but serves a different model than
  the runtime-owned adapter configuration intended, the runtime must fail with a
  clear mismatch error instead of silently accepting the wrong model.
- If an explicit Hugging Face reference is invalid, unauthorized, or blocked by
  runtime-owned offline policy, the runtime must fail as a model-resolution
  failure instead of falling back to another model source.
- If the default cache root or explicit cache root exists but does not contain a
  usable asset for the requested configuration, the runtime must continue the
  documented resolution order or fail clearly rather than claiming success
  from a partial cache hit.
- If a later slice enables in-process embeddings or tool calling, the runtime
  must honor upstream prerequisites such as `embedding=True` and
  function-calling-compatible model or chat-format requirements.
- If local chat support ships before separate local embedding execution, later
  embedding work must extend the approved contract rather than retroactively
  redefining the first chat slice.
- If a caller configures direct in-process llama.cpp execution but the installed
  `llama-cpp-python` package is missing or cannot load the configured model,
  the runtime must fail through package-owned local model execution errors
  rather than trying to start or discover a server.

## Boundaries

### In Scope

- Reusing the existing adapter/provider seam for llama.cpp-backed local chat.
- Supporting direct in-process llama.cpp-backed local chat without requiring a
  local server.
- Supporting caller-owned or deployer-owned OpenAI-compatible local endpoints as
  an alternate wrapper path when the caller already has one.
- Defining the runtime-owned local model-resolution contract, including explicit
  local paths, cache lookup, default cache lookup at `~/.ollama/models`, and
  explicit Hugging Face references.
- Preserving repository-owned response normalization and tool-call shaping.
- Defining the future contract for optional local embedding-capable
  configuration without requiring it to ship in the first chat slice.

### Out of Scope

- Graph-mutation protocol design or context-pruning delivery in this feature.
- Runtime-managed installation, launch, supervision, readiness, or shutdown of a
  local llama.cpp server.
- A new public top-level execution API dedicated to local models.
- Provider auto-discovery from `/v1/models` or similar remote endpoint scans.
- Portable workflow-package fields for low-level deployment details such as local
  filesystem paths, server ports, credentials, launch scripts, or backend build
  flags.

### Always Do

- Reuse the existing adapter/provider seam unless a later approved spec revision
  changes that boundary.
- Keep runtime-owned local-model settings above the portable workflow package.
- Preserve repository-owned response normalization and existing executor routing
  semantics.
- Keep local-model support separable from graph-mutation work even if later
  pruning features use local embeddings.

### Ask First

- Requiring a local server for direct llama.cpp execution.
- Expanding the direct llama.cpp chat slice to include graph mutation, context
  pruning, or runtime-managed server ownership.
- Introducing new portable workflow manifest fields for deployment-specific local
  model settings.
- Requiring live-network or live-server validation as the primary unit-test path.

### Never Do

- Require portable workflow packages to embed environment-specific local file
  paths, model weights, launch scripts, or server lifecycle metadata.
- Silently fall back to another model when model resolution or endpoint/model
  identity checks fail.
- Collapse endpoint connectivity/protocol failures into model-resolution errors.
- Treat graph-mutation delivery as part of the required first local chat slice.

## Non-Goals

- No graph-mutation protocol design in this feature.
- No requirement that the first implementation slice deliver graph-mutation or
  context-pruning integration just because later pruning work may use local
  embeddings.
- No requirement to introduce a public top-level embedding API.
- No requirement to auto-discover local providers or models.
- No requirement to make local filesystem paths part of the portable workflow
  contract.
- No requirement that `dynamic-agent-runner` launch or supervise a local
  llama.cpp server as part of its core library behavior.
- No requirement that direct llama.cpp local execution use an OpenAI-compatible
  server wrapper.

## Dependencies and Assumptions

### Dependencies

- `specs/openai-compatible-provider-wrapper/spec.md` remains the authoritative
  seam for OpenAI-compatible provider integration when callers provide local
  server wrappers.
- `specs/internal-graph-mutation/spec.md` remains the authoritative future spec
  for graph mutation and context pruning rather than this feature.
- Future implementation planning may depend on accepted runtime integration with
  `llama-cpp-python` and the optional `huggingface` extra, but this spec does
  not by itself authorize additional dependency changes or packaging decisions.

### Assumptions

- The repository now has an initial local endpoint helper implementation, but
  broader llama.cpp follow-up work still requires fresh validation as each slice
  lands.
- Direct llama.cpp execution should use the installed `llama-cpp-python`
  dependency without the `server` extra.
- The caller or deployer can own endpoint provisioning, credentials, readiness,
  and lifecycle when choosing the server-backed wrapper path.
- Local embedding support may be deferred, but the contract defined in this spec
  must remain stable enough for later planning and implementation to build on it.

## Open Questions and Next Planning Decisions

- No blocking `NEEDS CLARIFICATION` items remain for this spec-level approval.
- The next SDD gate may begin Slice 3 planning with direct in-process
  `llama_cpp.Llama` chat adapter tests.
- `tasks.md` should decompose direct in-process local chat separately from later
  optional embedding work.

## Design Constraints

- Preserve the existing adapter/provider direction instead of creating a
  separate local-model interface family.
- Prefer documented integration seams from upstream docs, especially
  `llama_cpp.Llama` for direct execution and the OpenAI-compatible server path
  only when the caller provides a server wrapper.
- Keep local configuration runtime-owned and environment-specific.
- Treat server deployment settings such as `chat_format`,
  `chat_template_kwargs`, `model_alias`, GPU offload options, Metal build
  flags, tokenizer paths, and config-file wiring as deployment concerns rather
  than portable workflow metadata.
- Treat installation-channel concerns such as source builds, pre-built wheels,
  Metal/CUDA/backend flags, and Hugging Face GGUF fetching/caching as runtime or
  deployment concerns rather than workflow-package semantics.
- Treat Hugging Face model identifiers, revisions, cache locations, offline
  policy, and authentication as runtime or deployment concerns rather than
  portable workflow-package semantics.
- Default cache-path behavior should remain runtime-owned: callers may provide a
  model-cache folder explicitly, but when omitted the adapter uses
  `~/.ollama/models`.
- Keep any local server process ownership, launch scripts, packaged runtimes,
  endpoint readiness, and shutdown behavior outside the library's core portable-
  workflow contract.
- If function-calling support is implemented, require compatible upstream model
  and chat-format prerequisites instead of assuming that all GGUF models expose
  uniform tool-calling behavior.
- Preserve fake-client-friendly testing and avoid live network requirements.
- Keep this feature separable from graph mutation even when local embeddings are
  used by later context-pruning work.

## Validation Status

- This spec is authoritative for intended future behavior and boundaries.
- Fresh validation evidence now includes T1.1, T1.2, T2.1, and T2.2 RED
  checkpoints plus the targeted T1.3, T1.4, T1.5, T2.3, T2.4, T2.5, and T2.6
  GREEN implementation checks, recorded in commits `a5798cc`, `b79f124`,
  `6d269ad`, `ee0bf33`, `dd37c62`, `f564caa`, `cdc1b00`, `7a11464`, `f4bcb0e`,
  `d5857dd`, `9b7078f`, and
  `specs/llama-cpp-local-model/validation.md`.
  - Command: `poetry run pytest tests/test_openai_client.py -q 2>&1`
  - Observed outcome: `3 failed, 24 passed`
  - Expected RED reason: `ModuleNotFoundError: No module named
    'dynamic_agent_runner.local_models'`
  - Command: `poetry run pytest tests/test_executor.py -q 2>&1`
  - Observed outcome: `1 failed, 49 passed`
  - Expected RED reason: `ModuleNotFoundError: No module named
    'dynamic_agent_runner.local_models'`
  - Command: `poetry run pytest tests/test_openai_client.py -q 2>&1`
  - Observed outcome: `27 passed in 0.17s`
  - Command: `poetry run pytest tests/test_executor.py -q 2>&1`
  - Observed outcome: `50 passed in 0.41s`
  - Command: `poetry run pytest tests/test_openai_client.py -q 2>&1`
  - Observed outcome: `29 passed in 0.15s`
  - Command: `poetry run pytest tests/test_executor.py -q 2>&1`
  - Observed outcome: `50 passed in 0.38s`
  - Command: `poetry run pytest tests/test_import.py -q 2>&1`
  - Observed outcome: `1 passed in 0.19s`
  - Command: `poetry run pytest tests/test_openai_client.py`
    `tests/test_executor.py tests/test_import.py -q 2>&1`
  - Observed outcome: `80 passed in 0.47s`
  - Command: `poetry run pytest tests/test_local_models.py -q 2>&1`
  - Observed outcome: `4 failed in 0.20s`
  - Expected RED reason: `ImportError: cannot import name
    'HuggingFaceModelFileReference' from 'dynamic_agent_runner.local_models'`
  - Command: `poetry run pytest tests/test_local_models.py -q 2>&1`
  - Observed outcome: `8 failed in 0.17s`
  - Expected RED reason: missing Slice 2 model-reference and failure-taxonomy
    surfaces, including `HuggingFaceModelFileReference` in
    `dynamic_agent_runner.local_models` plus
    `LocalModelOfflinePolicyError`, `LocalModelResolutionError`, and
    `LocalModelIdentityMismatchError` in `dynamic_agent_runner.errors`
  - Command: `poetry run pytest tests/test_local_models.py -q 2>&1`
  - Observed outcome: `8 passed in 0.16s`
  - Command: `poetry run pre-commit run --files
    src/dynamic_agent_runner/local_models.py src/dynamic_agent_runner/errors.py`
    `tests/test_local_models.py 2>&1`
  - Observed outcome: Ruff Check passed; Ruff Format passed
  - Command: `poetry run pytest tests/test_local_models.py -q 2>&1`
  - Observed outcome: `10 passed in 0.12s`
  - Command: `poetry run pre-commit run --files
    src/dynamic_agent_runner/errors.py src/dynamic_agent_runner/openai_client.py`
    `src/dynamic_agent_runner/local_models.py tests/test_local_models.py 2>&1`
  - Observed outcome: Ruff Check passed; Ruff Format passed
  - Command: `poetry run pytest tests/test_local_models.py -q 2>&1`
  - Observed outcome: `12 passed in 0.19s`
  - Command: `poetry run pre-commit run --files
    src/dynamic_agent_runner/local_models.py tests/test_local_models.py`
    `pyproject.toml poetry.lock 2>&1`
  - Observed outcome: Ruff Check passed; Ruff Format passed
  - Command: `poetry run pytest tests/test_local_models.py -q 2>&1`
  - Observed outcome: `15 passed in 0.14s`
  - Command: `poetry run pytest tests/test_local_models.py`
    `tests/test_openai_client.py -q 2>&1`
  - Observed outcome: `44 passed in 0.18s`
  - Command: `poetry run pre-commit run --files
    src/dynamic_agent_runner/local_models.py
    src/dynamic_agent_runner/openai_client.py tests/test_local_models.py 2>&1`
  - Observed outcome: Ruff Check passed; Ruff Format passed
- Future implementation work must continue generating fresh validation evidence
  rather than relying on any reverted prototype results.
- The current authoritative companion SDD artifacts for this feature are
  `plan.md`, `tasks.md`, and `validation.md`.
