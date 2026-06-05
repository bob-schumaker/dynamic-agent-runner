# llama.cpp local-model adapter specification

## Metadata

- Feature slug: `llama-cpp-local-model`
- Mode: `light`
- Artifact type: feature specification
- Status: authoritative future-feature spec
  - no active implementation is present in the repository
  - any earlier prototype work is non-authoritative historical context only
- Related artifacts:
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/openai-compatible-provider-wrapper/spec.md`
  - `specs/internal-graph-mutation/spec.md`
  - `src/dynamic_agent_runner/openai_client.py`
  - `src/dynamic_agent_runner/executor.py`
  - local llama-cpp Python source checkout:
    `/Users/roschuma/Repos/github/llama-cpp-python/`
  - local `huggingface_hub` source checkout:
    `/Users/roschuma/Repos/github/huggingface_hub/`

## Objective

Define the authoritative repository direction for caller-provided local
llama.cpp-backed model adapters that fit the runtime's existing adapter and
provider seams instead of introducing a parallel local-model execution family.

## Problem Statement

`dynamic-agent-runner` already has a useful model execution boundary:

- model adapters advertise `models`
- adapters expose `is_local` for local-only selection
- executor routing already depends on those adapter-level semantics
- the provider-wrapper direction preserves repository-owned request and response
  boundaries around OpenAI-compatible transports

The repository does not yet have an authoritative feature-level source of truth
for how llama.cpp local execution should fit those seams. Earlier prototype work
was intentionally reverted, so future work must not reintroduce an ad hoc local
execution path that bypasses the established adapter/provider direction.

## Users

- Runtime maintainers defining the next local-model execution seam.
- Internal callers or downstream hosts that need local-only model execution.
- Future implementers of local embedding-backed runtime features.

## Existing Runtime Context

- The canonical executable input remains the immutable runtime package directory
  defined in `specs/dynamic-agent-runner/spec.md`.
- The runtime already supports model-adapter selection through advertised model
  metadata and `is_local` routing semantics.
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
3. repository-owned normalization of llama.cpp OpenAI-compatible chat responses
4. configuration boundaries between portable workflow metadata and runtime-owned
   local model settings
5. support for caller-owned or deployer-owned OpenAI-compatible llama.cpp
   endpoints through the existing provider seam
6. runtime-owned download of referenced model assets when they are missing
   locally

## Current Status and Boundary

- No active llama.cpp adapter implementation is currently present in the
  repository.
- Any earlier prototype code or prior test results are historical context only
  and do not count as current implementation or validation evidence.
- This artifact is authoritative for feature intent, scope, and design
  boundaries until a future implementation plan and task list are created.

## Primary Implementation Path

- The first implementation should prefer **caller-owned or deployer-owned
  OpenAI-compatible local endpoints** consumed through the existing
  provider-wrapper seam.
- Documented in-process `llama_cpp.Llama` integration remains an allowed future
  path, but it is not the default first implementation target unless later work
  explicitly reprioritizes it.

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
- Given `local_only` execution requirements, when an eligible llama.cpp-backed
  adapter is available, then executor routing may satisfy the request without
  requiring a remote provider.
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
- Given both endpoint-backed and in-process integration remain possible, when
  the first implementation path is chosen, then the runtime should prefer the
  caller/deployer-provided OpenAI-compatible endpoint path through the existing
  provider seam.
- Given async runtime execution is needed, when the first implementation is
  chosen, then server-based OpenAI-compatible integration is an acceptable path
  and the spec does not require an undocumented native async in-process
  `llama_cpp` client surface.
- Given a caller or deployer already provides an OpenAI-compatible wrapper or
  endpoint for a local llama.cpp server, when local execution is requested,
  then the runtime should consume that endpoint through the existing provider
  seam rather than owning server launch behavior itself.

### FR-3: Support local chat, aliases, and optional local embedding configuration

The feature must allow local chat-model configuration plus optional separate
embedding-capable local configuration for internal runtime behavior.

Acceptance criteria:

- Given a caller configures a primary local chat model, when a llama.cpp-backed
  adapter is constructed, then the adapter can expose one or more model aliases
  through the existing adapter metadata seam.
- Given server-based deployment uses documented multi-model configuration, when
  requests are routed by model name, then alias-based routing may use the
  server's `model_alias` behavior rather than requiring portable workflow
  packages to know concrete GGUF file paths.
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
- Given download is requested but the Hub reference is invalid, credentials are
  unavailable, offline or local-only policy forbids network access, or the
  remote asset cannot be resolved, when the adapter prepares local execution,
  then the runtime fails clearly with a model-resolution error instead of
  silently falling back to another model.

### FR-5c: Distinguish model-resolution failures from endpoint failures

The runtime must report local model-resolution failures separately from
OpenAI-compatible endpoint connectivity or protocol failures.

Acceptance criteria:

- Given a local path, cache lookup, or Hub fetch cannot resolve the requested
  model asset, when preparation runs, then the runtime reports a
  model-resolution error.
- Given an OpenAI-compatible local endpoint is unreachable, unauthorized, not
  ready, or wire-incompatible, when model execution runs, then the runtime
  reports an endpoint connectivity or endpoint protocol error rather than a
  model-resolution error.
- Given the caller supplies a provider or endpoint that is reachable but serves
  a different model than intended, when the adapter detects a mismatch through
  configured model metadata or request failure, then the runtime reports the
  mismatch clearly instead of silently rerouting to another model.

### FR-6: Keep server ownership outside the runtime library

If llama.cpp is exposed through an OpenAI-compatible local server, that server's
installation, launch, lifecycle, and endpoint ownership must remain outside the
core `dynamic-agent-runner` library contract.

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
  then the library consumes a provided OpenAI-compatible wrapper or endpoint
  rather than launching and supervising a local server itself.

## Non-Goals

- No graph-mutation protocol design in this feature.
- No requirement to introduce a public top-level embedding API.
- No requirement to auto-discover local providers or models.
- No requirement to make local filesystem paths part of the portable workflow
  contract.
- No requirement that `dynamic-agent-runner` launch or supervise a local
  llama.cpp server as part of its core library behavior.

## Design Constraints

- Preserve the existing adapter/provider direction instead of creating a
  separate local-model interface family.
- Prefer documented integration seams from upstream docs, especially the
  OpenAI-compatible server path, over inferred or undocumented internal hooks.
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
- There is no current implementation validation for this feature in the present
  repository state.
- Future implementation work must create fresh validation evidence rather than
  relying on any reverted prototype results.
